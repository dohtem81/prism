from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from services.api.app.api.messages import send_message
from shared.db.models import Message, OutboxEvent
from shared.outbox_dispatcher import dispatch_outbox_ids, dispatch_pending_outbox
from shared.schemas.message_events import SendMessage


def _payload() -> SendMessage:
    return SendMessage(
        author_user_id="user_1",
        room_id="room_1",
        client_message_id="cmsg_1",
        source_lang="pl",
        content_original="Czesc",
    )


def test_send_message_rejects_user_mismatch() -> None:
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        send_message(_payload(), db=db, current_user_id="other_user")

    assert exc.value.status_code == 403
    assert "does not match" in exc.value.detail


def test_send_message_returns_404_when_room_missing() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc:
        send_message(_payload(), db=db, current_user_id="user_1")

    assert exc.value.status_code == 404


def test_send_message_returns_403_when_not_member() -> None:
    db = MagicMock()
    room = MagicMock()
    db.scalar.side_effect = [room, None]

    with pytest.raises(HTTPException) as exc:
        send_message(_payload(), db=db, current_user_id="user_1")

    assert exc.value.status_code == 403


@patch("services.api.app.api.messages.dispatch_outbox_ids")
@patch("services.api.app.api.messages.celery_client")
def test_send_message_persists_pending_outbox_before_dispatch(
    celery_client_mock: MagicMock,
    dispatch_mock: MagicMock,
) -> None:
    db = MagicMock()
    room = MagicMock()
    member = MagicMock()
    db.scalar.side_effect = [room, member, 7]

    created_at = datetime.now(timezone.utc)

    def _refresh(msg: Message) -> None:
        msg.created_at = created_at

    db.refresh.side_effect = _refresh
    outbox_events: list[OutboxEvent] = []

    def _add(instance) -> None:
        if isinstance(instance, OutboxEvent):
            instance.id = len(outbox_events) + 1
            outbox_events.append(instance)

    db.add.side_effect = _add
    dispatch_mock.side_effect = lambda db, ids, **kwargs: {
        "processed": len(ids), "processed_ids": ids, "failed": 0
    }

    response = send_message(_payload(), db=db, current_user_id="user_1")

    assert response.translation_job_enqueued is True
    assert response.room_id == "room_1"
    assert response.status == "original_only"
    assert response.version == 1
    assert response.message_id.startswith("msg_")

    assert db.add.call_count == 5
    db.commit.assert_called_once()
    assert [event.event_type for event in outbox_events] == ["MessageCreated", "TranslationRequested"]
    assert all(event.status == "pending" for event in outbox_events)
    dispatch_mock.assert_called_once()
    assert dispatch_mock.call_args.args[1] == [1, 2]
    assert dispatch_mock.call_args.kwargs["send_task"] is celery_client_mock.send_task
    assert response.translation_job_enqueued is True


@patch("services.api.app.api.messages.celery_client")
def test_send_message_idempotent_duplicate_does_not_reenqueue(celery_client_mock: MagicMock) -> None:
    db = MagicMock()
    room = MagicMock()
    member = MagicMock()

    existing = Message(
        id="msg_existing",
        room_id="room_1",
        author_user_id="user_1",
        client_message_id="cmsg_1",
        source_lang="pl",
        content_original="Czesc",
        status="original_only",
        version=1,
        created_at=datetime.now(timezone.utc),
    )

    db.scalar.side_effect = [room, member, 1, existing]
    db.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))

    response = send_message(_payload(), db=db, current_user_id="user_1")

    assert response.translation_job_enqueued is False
    assert response.message_id == "msg_existing"
    assert db.rollback.called
    celery_client_mock.send_task.assert_not_called()


def test_outbox_dispatch_marks_event_processed_after_publish() -> None:
    event = OutboxEvent(
        id=17,
        aggregate_type="message",
        aggregate_id="msg_1",
        event_type="MessageCreated",
        payload={"room_event": {"room_id": "room_1", "type": "MessageCreated"}},
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    db.scalar.return_value = event
    publish_room = MagicMock()

    result = dispatch_outbox_ids(
        db,
        [17],
        send_task=MagicMock(),
        publish_room_event=publish_room,
        publish_user_event=MagicMock(),
    )

    assert result == {"processed": 1, "processed_ids": [17], "failed": 0}
    assert event.status == "processed"
    assert event.processed_at is not None
    publish_room.assert_called_once_with("room_1", {"room_id": "room_1", "type": "MessageCreated"})
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


def test_outbox_dispatch_failure_leaves_event_pending() -> None:
    event = OutboxEvent(
        id=18,
        aggregate_type="message",
        aggregate_id="msg_1",
        event_type="TranslationRequested",
        payload={"task_name": "translate", "queue": "translation.requested.q", "kwargs": {}},
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    db.scalar.return_value = event
    send_task = MagicMock(side_effect=ConnectionError("broker unavailable"))

    result = dispatch_outbox_ids(
        db,
        [18],
        send_task=send_task,
        publish_room_event=MagicMock(),
        publish_user_event=MagicMock(),
    )

    assert result == {"processed": 0, "processed_ids": [], "failed": 1}
    assert event.status == "pending"
    assert event.processed_at is None
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_outbox_dispatch_marks_translation_processed_after_enqueue() -> None:
    event = OutboxEvent(
        id=20,
        aggregate_type="message",
        aggregate_id="msg_1",
        event_type="TranslationRequested",
        payload={
            "task_name": "translate",
            "queue": "translation.requested.q",
            "kwargs": {"message_id": "msg_1"},
        },
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    db.scalar.return_value = event
    send_task = MagicMock()

    result = dispatch_outbox_ids(
        db,
        [20],
        send_task=send_task,
        publish_room_event=MagicMock(),
        publish_user_event=MagicMock(),
    )

    assert result["processed_ids"] == [20]
    assert event.status == "processed"
    send_task.assert_called_once_with(
        "translate",
        kwargs={"message_id": "msg_1"},
        queue="translation.requested.q",
        task_id="outbox-20",
    )
    db.commit.assert_called_once()


def test_outbox_dispatch_database_lookup_error_remains_retryable() -> None:
    db = MagicMock()
    db.scalar.side_effect = ConnectionError("database unavailable")

    result = dispatch_outbox_ids(
        db,
        [21],
        send_task=MagicMock(),
        publish_room_event=MagicMock(),
        publish_user_event=MagicMock(),
    )

    assert result == {"processed": 0, "processed_ids": [], "failed": 1}
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_outbox_sweeper_retries_pending_rows() -> None:
    event = OutboxEvent(
        id=19,
        aggregate_type="message",
        aggregate_id="msg_1",
        event_type="MessageCreated",
        payload={"room_event": {"room_id": "room_1", "type": "MessageCreated"}},
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    db.__enter__.return_value = db
    db.scalars.return_value.all.return_value = [19]
    db.scalar.return_value = event
    session_factory = MagicMock(return_value=db)

    result = dispatch_pending_outbox(
        session_factory,
        send_task=MagicMock(),
        publish_room_event=MagicMock(),
        publish_user_event=MagicMock(),
    )

    assert result == {"processed": 1, "processed_ids": [19], "failed": 0}
    assert event.status == "processed"


def test_send_message_schema_rejects_invalid_source_language() -> None:
    with pytest.raises(ValidationError):
        SendMessage(
            author_user_id="user_1",
            room_id="room_1",
            client_message_id="cmsg_1",
            source_lang="pol",
            content_original="Czesc",
        )


def test_send_message_schema_rejects_oversized_content() -> None:
    with pytest.raises(ValidationError):
        SendMessage(
            author_user_id="user_1",
            room_id="room_1",
            client_message_id="cmsg_1",
            source_lang="pl",
            content_original="x" * 4001,
        )
