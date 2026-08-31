from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from shared.logging_utils import get_correlation_id, get_logger
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.celery_client import celery_client
from services.api.app.infra.db import get_db
from services.api.app.infra.rate_limit import rate_limiter
from services.api.app.infra.settings import settings
from services.api.app.realtime.websocket_gateway import manager
from shared.db.models import Message, OutboxEvent, Room, RoomEvent, RoomMember
from shared.schemas.message_events import SendMessage, SendMessageResponse
from shared.tracing import get_trace_id, start_span

router = APIRouter(prefix="/v1/messages", tags=["messages"])
logger = get_logger("prism.api.messages")


@router.post("", response_model=SendMessageResponse)
def send_message(
    payload: SendMessage,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> SendMessageResponse:
    if payload.author_user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Authenticated user does not match author_user_id")

    room = db.scalar(select(Room).where(Room.id == payload.room_id))
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    membership = db.scalar(
        select(RoomMember).where(
            RoomMember.room_id == payload.room_id,
            RoomMember.user_id == current_user_id,
        )
    )
    if not membership:
        raise HTTPException(status_code=403, detail="User is not a room member")

    rate_limiter.enforce(
        f"rl:user:{current_user_id}:messages",
        settings.rate_limit_messages_per_user_per_minute,
        60,
        scope="messages_per_user",
        user_id=current_user_id,
    )
    rate_limiter.enforce(
        f"rl:room:{payload.room_id}:messages",
        settings.rate_limit_messages_per_room_per_minute,
        60,
        scope="messages_per_room",
        room_id=payload.room_id,
    )
    rate_limiter.enforce(
        f"rl:user:{current_user_id}:messages:daily",
        settings.rate_limit_messages_per_user_per_day,
        86400,
        scope="messages_per_user_daily_quota",
        user_id=current_user_id,
    )
    rate_limiter.enforce(
        f"rl:room:{payload.room_id}:messages:daily",
        settings.rate_limit_messages_per_room_per_day,
        86400,
        scope="messages_per_room_daily_quota",
        room_id=payload.room_id,
    )
    rate_limiter.enforce(
        f"rl:user:{current_user_id}:translation_jobs:daily",
        settings.rate_limit_translation_jobs_per_user_per_day,
        86400,
        scope="translation_jobs_per_user_daily_quota",
        user_id=current_user_id,
    )

    with start_span("api.message.create", room_id=payload.room_id, user_id=current_user_id):
        return _create_message(payload, db, current_user_id)


def _create_message(payload: SendMessage, db: Session, current_user_id: str) -> SendMessageResponse:
    message_id = f"msg_{uuid4().hex[:24]}"
    created_at = datetime.now(timezone.utc)
    should_enqueue_translation = True
    room_sequence = (db.scalar(select(func.max(RoomEvent.room_sequence)).where(RoomEvent.room_id == payload.room_id)) or 0) + 1
    event_id = f"evt_{uuid4().hex[:24]}"

    message = Message(
        id=message_id,
        room_id=payload.room_id,
        author_user_id=payload.author_user_id,
        client_message_id=payload.client_message_id,
        source_lang=payload.source_lang,
        content_original=payload.content_original,
        status="original_only",
        version=1,
        created_at=created_at,
    )

    message_created_payload = {
        "event_id": event_id,
        "event_type": "MessageCreated",
        "event_version": 1,
        "occurred_at": created_at.isoformat(),
        "type": "MessageCreated",
        "room_id": payload.room_id,
        "room_sequence": room_sequence,
        "message": {
            "message_id": message.id,
            "version": message.version,
            "author_user_id": message.author_user_id,
            "source_lang": message.source_lang,
            "content_original": message.content_original,
            "translations": {},
            "status": message.status,
            "created_at": created_at.isoformat(),
        },
    }

    room_event = RoomEvent(
        room_id=payload.room_id,
        room_sequence=room_sequence,
        event_id=event_id,
        event_type="MessageCreated",
        payload=message_created_payload,
        occurred_at=created_at,
    )

    outbox_event = OutboxEvent(
        aggregate_type="message",
        aggregate_id=message.id,
        event_type="MessageCreated",
        payload=message_created_payload,
        status="pending",
        created_at=created_at,
    )

    try:
        db.add(message)
        db.add(room_event)
        db.add(outbox_event)
        outbox_event.status = "processed"
        outbox_event.processed_at = created_at
        db.commit()
        db.refresh(message)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Message).where(
                Message.room_id == payload.room_id,
                Message.author_user_id == payload.author_user_id,
                Message.client_message_id == payload.client_message_id,
            )
        )
        if not existing:
            raise HTTPException(status_code=500, detail="Failed to persist message")
        message = existing
        should_enqueue_translation = False

    if should_enqueue_translation:
        celery_client.send_task(
            "services.worker.app.tasks.translation.translate_message",
            kwargs={
                "message_id": message.id,
                "room_id": message.room_id,
                "source_lang": message.source_lang,
                "content_original": message.content_original,
                "correlation_id": get_correlation_id(),
                "trace_id": get_trace_id(),
            },
            queue="translation.requested.q",
        )
        logger.info(
            "message_queued_for_translation",
            extra={
                "message_id": message.id,
                "room_id": message.room_id,
                "correlation_id": get_correlation_id(),
            },
        )

    manager.publish_room_event(message.room_id, message_created_payload)
    logger.info(
        "message_created",
        extra={
            "message_id": message.id,
            "room_id": message.room_id,
            "correlation_id": get_correlation_id(),
        },
    )

    return SendMessageResponse(
        message_id=message.id,
        room_id=message.room_id,
        status=message.status,
        version=message.version,
        translation_job_enqueued=should_enqueue_translation,
        created_at=message.created_at,
    )
