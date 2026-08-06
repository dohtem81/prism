from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.celery_client import celery_client
from services.api.app.infra.db import get_db
from shared.db.models import Message, OutboxEvent, Room, RoomEvent, RoomMember
from shared.schemas.message_events import SendMessage, SendMessageResponse

router = APIRouter(prefix="/v1/messages", tags=["messages"])


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

    message_id = f"msg_{uuid4().hex[:24]}"
    created_at = datetime.now(timezone.utc)
    should_enqueue_translation = True
    room_sequence = (db.scalar(select(func.max(RoomEvent.room_sequence)).where(RoomEvent.room_id == payload.room_id)) or 0) + 1

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
        "type": "MessageCreated",
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
        event_id=f"evt_{uuid4().hex[:24]}",
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
            },
            queue="translation.requested.q",
        )

    return SendMessageResponse(
        message_id=message.id,
        room_id=message.room_id,
        status=message.status,
        version=message.version,
        translation_job_enqueued=should_enqueue_translation,
        created_at=message.created_at,
    )
