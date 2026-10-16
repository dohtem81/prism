from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import OutboxEvent
from shared.logging_utils import get_logger

logger = get_logger("prism.outbox")


def _dispatch(
    event: OutboxEvent,
    *,
    send_task: Callable[..., Any],
    publish_room_event: Callable[[str, dict[str, Any]], Any],
    publish_user_event: Callable[[str, dict[str, Any]], Any],
) -> None:
    if event.event_type == "TranslationRequested":
        task = event.payload
        send_task(
            task["task_name"],
            kwargs=task["kwargs"],
            queue=task["queue"],
            task_id=f"outbox-{event.id}",
        )
        return

    envelope = event.payload
    room_payload = envelope.get("room_event", envelope)
    room_id = room_payload["room_id"]
    publish_room_event(room_id, room_payload)

    user_ids = envelope.get("user_hints")
    if user_ids is None and event.event_type == "MessageCreated":
        user_ids = [
            entry["user_id"]
            for entry in room_payload.get("message", {}).get("receipts", {}).get("unseen", [])
        ]
    for user_id in user_ids or []:
        publish_user_event(user_id, {"type": "RoomUnreadHint", "room_id": room_id})


def dispatch_pending_outbox(
    session_factory: Callable[[], Session],
    *,
    send_task: Callable[..., Any],
    publish_room_event: Callable[[str, dict[str, Any]], Any],
    publish_user_event: Callable[[str, dict[str, Any]], Any],
    outbox_ids: Sequence[int] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    if outbox_ids is None:
        with session_factory() as db:
            outbox_ids = db.scalars(
                select(OutboxEvent.id)
                .where(OutboxEvent.status == "pending")
                .order_by(OutboxEvent.id)
                .limit(limit)
            ).all()

    processed_ids: list[int] = []
    failed = 0
    for outbox_id in outbox_ids:
        with session_factory() as db:
            result = dispatch_outbox_ids(
                db,
                [outbox_id],
                send_task=send_task,
                publish_room_event=publish_room_event,
                publish_user_event=publish_user_event,
            )
        processed_ids.extend(result["processed_ids"])
        failed += result["failed"]

    return {"processed": len(processed_ids), "processed_ids": processed_ids, "failed": failed}


def dispatch_outbox_ids(
    db: Session,
    outbox_ids: Sequence[int],
    *,
    send_task: Callable[..., Any],
    publish_room_event: Callable[[str, dict[str, Any]], Any],
    publish_user_event: Callable[[str, dict[str, Any]], Any],
) -> dict[str, Any]:
    processed_ids: list[int] = []
    failed = 0
    for outbox_id in outbox_ids:
        event_type = "unknown"
        try:
            event = db.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == outbox_id, OutboxEvent.status == "pending")
                .with_for_update(skip_locked=True)
            )
            if event is None:
                db.rollback()
                continue

            event_type = event.event_type
            _dispatch(
                event,
                send_task=send_task,
                publish_room_event=publish_room_event,
                publish_user_event=publish_user_event,
            )
            event.status = "processed"
            event.processed_at = datetime.now(timezone.utc)
            db.commit()
            processed_ids.append(outbox_id)
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("outbox_dispatch_failed", extra={"outbox_id": outbox_id, "event_type": event_type})

    return {"processed": len(processed_ids), "processed_ids": processed_ids, "failed": failed}