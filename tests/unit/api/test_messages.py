from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from services.api.app.api.messages import message_progress, send_message
from shared.db.models import DemoBotJob, Message, OutboxEvent
from shared.demo import DEMO_ROOM_ID
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


@pytest.mark.parametrize(
    ("status", "started", "failed", "outbox", "expected"),
    [
        ("original_only", False, False, "pending", "dispatch_pending"),
        ("original_only", False, False, "processed", "queued"),
        ("original_only", False, False, None, "unknown"),
        ("original_only", True, False, "processed", "worker_started"),
        ("original_only", True, True, "processed", "failed"),
        ("translated", True, False, "processed", "completed"),
        ("partially_translated", True, False, "processed", "partial"),
        ("translation_unavailable", True, False, "processed", "failed"),
        ("unexpected", False, False, "processed", "unknown"),
    ],
)
def test_message_progress_reports_confirmed_stage(status, started, failed, outbox, expected) -> None:
    db = MagicMock()
    now = datetime.now(timezone.utc)
    message = Message(
        id="msg_1", status=status, translation_started_at=now if started else None,
        translation_failed_at=now if failed else None,
    )
    db.scalar.side_effect = [message, 0]
    db.execute.return_value.all.return_value = [("TranslationRequested", outbox)]
    assert message_progress("msg_1", db, "user_1").stage == expected


@pytest.mark.parametrize(
    ("events", "status", "expected_original", "expected_update"),
    [
        ([("MessageCreated", "pending")], "original_only", "pending", "not_ready"),
        ([("MessageCreated", "processed"), ("MessageUpdated", "pending")], "translated", "published", "pending"),
        ([("MessageCreated", "processed"), ("MessageUpdated", "processed")], "translated", "published", "published"),
        ([], "translated", "unknown", "unknown"),
        ([("MessageCreated", "unexpected"), ("MessageUpdated", "unexpected")], "translated", "unknown", "unknown"),
    ],
)
def test_message_progress_reports_independent_delivery_paths(events, status, expected_original, expected_update) -> None:
    db = MagicMock()
    db.scalar.side_effect = [Message(id="msg_1", status=status), 2]
    db.execute.return_value.all.return_value = events
    progress = message_progress("msg_1", db, "user_1")
    assert progress.original_publication == expected_original
    assert progress.update_publication == expected_update
    assert progress.other_readers == 2


def test_message_progress_rejects_missing_or_unauthorized_message() -> None:
    db = MagicMock()
    db.scalar.return_value = None
    with pytest.raises(HTTPException) as exc:
        message_progress("msg_1", db, "other")
    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    ("job_status", "attempts", "processing", "expected"),
    [("pending", 0, False, "queued"), ("pending", 0, True, "processing"),
     ("pending", 1, False, "retrying"), ("completed", 0, False, "completed"),
     ("other", 0, False, "unknown")],
)
def test_message_progress_reports_bot_state(job_status, attempts, processing, expected) -> None:
    db = MagicMock()
    db.scalar.side_effect = [
        Message(id="msg_1", room_id=DEMO_ROOM_ID, status="original_only"),
        0,
        DemoBotJob(kind="reply", source_id="msg_1", status=job_status, attempts=attempts), None,
    ]
    db.execute.return_value.all.return_value = []
    with patch("services.api.app.api.messages.redis_client.exists", return_value=processing):
        assert message_progress("msg_1", db, "user_1").bot_status == expected


def test_message_progress_reports_unknown_if_bot_progress_redis_fails() -> None:
    from redis.exceptions import ConnectionError
    db = MagicMock()
    db.scalar.side_effect = [
        Message(id="msg_1", room_id=DEMO_ROOM_ID, status="original_only"),
        0, DemoBotJob(kind="reply", source_id="msg_1", status="pending", attempts=0), None,
    ]
    db.execute.return_value.all.return_value = []
    with patch("services.api.app.api.messages.redis_client.exists", side_effect=ConnectionError("offline")):
        assert message_progress("msg_1", db, "user_1").bot_status == "unknown"


@pytest.mark.parametrize(
    ("status", "started", "failed", "event_status", "stage"),
    [
        ("original_only", False, False, "pending", "dispatch_pending"),
        ("original_only", False, False, "processed", "queued"),
        ("original_only", True, False, "processed", "worker_started"),
        ("translated", True, False, "processed", "completed"),
        ("partially_translated", True, False, "processed", "partial"),
        ("translation_unavailable", True, False, "processed", "failed"),
        ("original_only", True, True, "processed", "failed"),
    ],
)
def test_message_progress_includes_bot_reply_translation(status, started, failed, event_status, stage) -> None:
    now = datetime.now(timezone.utc)
    db = MagicMock()
    db.scalar.side_effect = [
        Message(id="msg_1", room_id=DEMO_ROOM_ID, status="translated"),
        0,
        DemoBotJob(kind="reply", source_id="msg_1", status="completed", attempts=0),
        Message(id="bot_reply", status=status, translation_started_at=now if started else None,
                translation_failed_at=now if failed else None),
    ]
    db.execute.return_value.all.side_effect = [
        [("MessageCreated", "processed")],
        [("MessageCreated", "processed"), ("TranslationRequested", event_status), ("MessageUpdated", "pending")],
    ]
    result = message_progress("msg_1", db, "user_1")
    assert result.bot_reply is not None
    assert result.bot_reply.stage == stage
    assert result.bot_reply.original_publication == "published"
    assert result.bot_reply.update_publication == "pending"


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
