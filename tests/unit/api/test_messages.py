from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from services.api.app.api.messages import send_message
from shared.db.models import Message
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


@patch("services.api.app.api.messages.celery_client")
def test_send_message_persists_and_enqueues(celery_client_mock: MagicMock) -> None:
    db = MagicMock()
    room = MagicMock()
    member = MagicMock()
    db.scalar.side_effect = [room, member, 7]

    created_at = datetime.now(timezone.utc)

    def _refresh(msg: Message) -> None:
        msg.created_at = created_at

    db.refresh.side_effect = _refresh

    response = send_message(_payload(), db=db, current_user_id="user_1")

    assert response.translation_job_enqueued is True
    assert response.room_id == "room_1"
    assert response.status == "original_only"
    assert response.version == 1
    assert response.message_id.startswith("msg_")

    assert db.add.call_count == 3
    db.commit.assert_called_once()
    celery_client_mock.send_task.assert_called_once()


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
