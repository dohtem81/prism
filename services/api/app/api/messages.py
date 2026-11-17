from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from redis.exceptions import RedisError

from shared.logging_utils import get_correlation_id, get_logger
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.api.app.auth import security_events as events
from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.auth.security_events import security_events
from services.api.app.infra.celery_client import celery_client
from services.api.app.infra.db import get_db
from services.api.app.infra.rate_limit import rate_limiter
from services.api.app.infra.settings import settings
from services.api.app.realtime.websocket_gateway import manager, redis_client
from shared.db.models import DemoBotJob, Message, MessageReceipt, OutboxEvent, Room, RoomEvent, RoomMember, User
from shared.demo import DEMO_BOT_ID, DEMO_ROOM_ID, bot_client_message_id, bot_processing_key
from shared.receipts import compute_message_receipts
from shared.schemas.message_events import MessageProcessingProgress, MessageProgressResponse, SendMessage, SendMessageResponse
from shared.outbox_dispatcher import dispatch_outbox_ids
from shared.tracing import get_trace_id, start_span

router = APIRouter(prefix="/v1/messages", tags=["messages"])
logger = get_logger("prism.api.messages")


def _processing_progress(db: Session, message: Message) -> MessageProcessingProgress:
    events = dict(
        db.execute(
            select(OutboxEvent.event_type, OutboxEvent.status).where(
                OutboxEvent.aggregate_type == "message",
                OutboxEvent.aggregate_id == message.id,
                OutboxEvent.event_type.in_(["MessageCreated", "TranslationRequested", "MessageUpdated"]),
            ).order_by(OutboxEvent.id)
        ).all()
    )
    publication_states = {"pending": "pending", "processed": "published"}
    original_publication = publication_states.get(events.get("MessageCreated"), "unknown")
    if "MessageUpdated" in events:
        update_publication = publication_states.get(events["MessageUpdated"], "unknown")
    elif message.status in ("translated", "partially_translated", "translation_unavailable"):
        update_publication = "unknown"
    else:
        update_publication = "not_ready"
    if message.status == "translated":
        stage = "completed"
    elif message.status == "partially_translated":
        stage = "partial"
    elif message.status == "translation_unavailable" or message.translation_failed_at is not None:
        stage = "failed"
    elif message.status != "original_only":
        stage = "unknown"
    elif message.translation_started_at is not None:
        stage = "worker_started"
    else:
        outbox_status = events.get("TranslationRequested")
        stage = {"pending": "dispatch_pending", "processed": "queued"}.get(outbox_status, "unknown")
    return MessageProcessingProgress(
        stage=stage, original_publication=original_publication, update_publication=update_publication,
    )


@router.get("/{message_id}/progress", response_model=MessageProgressResponse)
def message_progress(
    message_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> MessageProgressResponse:
    message = db.scalar(
        select(Message)
        .join(RoomMember, (RoomMember.room_id == Message.room_id) & (RoomMember.user_id == current_user_id))
        .where(Message.id == message_id, Message.author_user_id == current_user_id)
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    progress = _processing_progress(db, message)
    other_readers = db.scalar(
        select(func.count(MessageReceipt.id)).where(
            MessageReceipt.message_id == message_id,
            MessageReceipt.user_id != current_user_id,
        )
    )
    bot_status = "not_applicable"
    bot_reply = None
    if message.room_id == DEMO_ROOM_ID:
        job = db.scalar(select(DemoBotJob).where(DemoBotJob.kind == "reply", DemoBotJob.source_id == message_id))
        if job is not None:
            reply = db.scalar(select(Message).where(
                Message.room_id == DEMO_ROOM_ID,
                Message.author_user_id == DEMO_BOT_ID,
                Message.client_message_id == bot_client_message_id("reply", message_id),
            ))
            if reply is not None:
                bot_reply = _processing_progress(db, reply)
            if job.status == "completed":
                bot_status = "completed"
            elif job.status == "pending":
                try:
                    if redis_client.exists(bot_processing_key(message_id)):
                        bot_status = "processing"
                    else:
                        bot_status = "retrying" if job.attempts else "queued"
                except RedisError:
                    logger.exception("demo_bot_progress_unavailable", extra={"message_id": message_id})
                    bot_status = "unknown"
            else:
                bot_status = "unknown"
    return MessageProgressResponse(
        message_id=message_id, **progress.model_dump(), other_readers=other_readers,
        bot_status=bot_status, bot_reply=bot_reply,
    )


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
        security_events.record(
            events.MEMBERSHIP_DENIED, reason="not_a_member", user_id=current_user_id, room_id=payload.room_id
        )
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
    receipts = compute_message_receipts(db, payload.room_id, [message]).get(message.id, {"seen": [], "unseen": []})
    author_display_name = next(
        (entry["display_name"] for entry in receipts["seen"] if entry["user_id"] == message.author_user_id),
        None,
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
            "author_display_name": author_display_name,
            "source_lang": message.source_lang,
            "content_original": message.content_original,
            "translations": {},
            "status": message.status,
            "created_at": created_at.isoformat(),
            "receipts": receipts,
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
        payload={"room_event": message_created_payload},
        status="pending",
        created_at=created_at,
    )
    translation_outbox_event = OutboxEvent(
        aggregate_type="message",
        aggregate_id=message.id,
        event_type="TranslationRequested",
        payload={
            "task_name": "services.worker.app.tasks.translation.translate_message",
            "queue": "translation.requested.q",
            "kwargs": {
                "message_id": message.id,
                "room_id": message.room_id,
                "source_lang": message.source_lang,
                "content_original": message.content_original,
                "correlation_id": get_correlation_id(),
                "trace_id": get_trace_id(),
            },
        },
        status="pending",
        created_at=created_at,
    )

    try:
        db.add(message)
        db.add(MessageReceipt(message_id=message.id, user_id=message.author_user_id, seen_at=created_at))
        db.add(room_event)
        db.add(outbox_event)
        db.add(translation_outbox_event)
        if payload.room_id == DEMO_ROOM_ID:
            author = db.get(User, current_user_id)
            if author is not None and author.is_demo is True:
                db.add(DemoBotJob(kind="reply", source_id=message.id, status="pending", attempts=0,
                                  next_attempt_at=created_at, created_at=created_at))
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

    translation_job_enqueued = False
    if should_enqueue_translation:
        dispatch_result = dispatch_outbox_ids(
            db,
            [outbox_event.id, translation_outbox_event.id],
            send_task=celery_client.send_task,
            publish_room_event=manager.publish_room_event,
            publish_user_event=manager.publish_user_event,
        )
        translation_job_enqueued = translation_outbox_event.id in dispatch_result["processed_ids"]
    if translation_job_enqueued:
        logger.info(
            "message_queued_for_translation",
            extra={
                "message_id": message.id,
                "room_id": message.room_id,
                "correlation_id": get_correlation_id(),
            },
        )

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
        translation_job_enqueued=translation_job_enqueued,
        created_at=message.created_at,
    )
