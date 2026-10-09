from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from services.api.app.api.rooms import mark_messages_seen
from shared.db.models import Message, MessageReceipt
from shared.receipts import compute_message_receipts
from shared.schemas.rooms import MarkSeenRequest

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def _message() -> Message:
    return Message(
        id="msg_1",
        room_id="room_1",
        author_user_id="alice",
        client_message_id="c1",
        source_lang="en",
        content_original="hi",
        status="original_only",
        version=1,
        created_at=NOW,
    )


def _member(user_id: str, lang: str, joined: datetime = NOW - timedelta(days=1)) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, preferred_lang=lang, created_at=joined, display_name=user_id.title())


def _db(members: list, receipts: list, translations: list) -> MagicMock:
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(all=MagicMock(return_value=members)),
        MagicMock(all=MagicMock(return_value=receipts)),
        MagicMock(all=MagicMock(return_value=translations)),
    ]
    return db


def test_author_is_seen_and_others_unseen_without_receipt() -> None:
    db = _db([_member("alice", "en"), _member("bob", "de")], [], [])

    result = compute_message_receipts(db, "room_1", [_message()])["msg_1"]

    assert [u["user_id"] for u in result["seen"]] == ["alice"]
    assert [u["user_id"] for u in result["unseen"]] == ["bob"]


def test_receipt_marks_member_seen() -> None:
    receipts = [SimpleNamespace(message_id="msg_1", user_id="bob", seen_at=NOW + timedelta(seconds=5))]
    db = _db([_member("alice", "en"), _member("bob", "de")], receipts, [])

    result = compute_message_receipts(db, "room_1", [_message()])["msg_1"]

    assert {u["user_id"] for u in result["seen"]} == {"alice", "bob"}
    assert result["unseen"] == []


def test_translation_in_own_language_after_seen_makes_member_unseen_again() -> None:
    receipts = [SimpleNamespace(message_id="msg_1", user_id="bob", seen_at=NOW + timedelta(seconds=5))]
    translations = [SimpleNamespace(message_id="msg_1", target_lang="de", translated_at=NOW + timedelta(seconds=9))]
    db = _db([_member("alice", "en"), _member("bob", "de")], receipts, translations)

    result = compute_message_receipts(db, "room_1", [_message()])["msg_1"]

    assert [u["user_id"] for u in result["unseen"]] == ["bob"]


def test_translation_in_other_language_does_not_reset_seen() -> None:
    receipts = [SimpleNamespace(message_id="msg_1", user_id="bob", seen_at=NOW + timedelta(seconds=5))]
    translations = [SimpleNamespace(message_id="msg_1", target_lang="fr", translated_at=NOW + timedelta(seconds=9))]
    db = _db([_member("alice", "en"), _member("bob", "de")], receipts, translations)

    result = compute_message_receipts(db, "room_1", [_message()])["msg_1"]

    assert result["unseen"] == []


def test_member_who_joined_after_message_is_not_listed() -> None:
    db = _db([_member("alice", "en"), _member("carol", "en", joined=NOW + timedelta(days=1))], [], [])

    result = compute_message_receipts(db, "room_1", [_message()])["msg_1"]

    assert result["unseen"] == []


def test_mark_seen_rejects_non_members() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc:
        mark_messages_seen("room_1", MarkSeenRequest(message_ids=["msg_1"]), db=db, current_user_id="bob")

    assert exc.value.status_code == 403


@patch("services.api.app.api.rooms.manager")
def test_mark_seen_creates_receipt_and_publishes(manager_mock: MagicMock) -> None:
    db = MagicMock()
    db.scalar.return_value = MagicMock()
    db.execute.return_value.all.return_value = [("msg_1",)]
    db.scalars.return_value.all.return_value = []
    db.get.return_value = SimpleNamespace(display_name="Bob")

    response = mark_messages_seen("room_1", MarkSeenRequest(message_ids=["msg_1", "msg_1"]), db=db, current_user_id="bob")

    assert response.marked == 1
    added = db.add.call_args.args[0]
    assert isinstance(added, MessageReceipt)
    assert added.user_id == "bob"
    db.commit.assert_called_once()
    manager_mock.publish_room_event.assert_called_once()
    assert manager_mock.publish_room_event.call_args.args[1]["type"] == "MessageSeen"
    manager_mock.publish_user_event.assert_called_once_with("bob", {"type": "RoomUnreadHint", "room_id": "room_1"})


@patch("services.api.app.api.rooms.manager")
def test_mark_seen_ignores_ids_that_are_not_markable(manager_mock: MagicMock) -> None:
    db = MagicMock()
    db.scalar.return_value = MagicMock()
    db.execute.return_value.all.return_value = []

    response = mark_messages_seen("room_1", MarkSeenRequest(message_ids=["own_msg"]), db=db, current_user_id="bob")

    assert response.marked == 0
    db.add.assert_not_called()
    manager_mock.publish_room_event.assert_not_called()
