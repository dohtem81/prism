from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.api.app.api.rooms import (
    _message_is_after_anchor,
    create_room,
    list_room_messages,
    list_rooms,
    upsert_membership,
)
from services.api.app.auth.dependencies import create_access_token, get_current_user_id
from shared.db.models import Message, MessageTranslation, Room, RoomMember
from shared.schemas.rooms import CreateRoomRequest, JoinRoomRequest


def test_get_current_user_id_uses_jwt_sub() -> None:
    db = MagicMock()

    token = create_access_token("user_42")
    current_user_id = get_current_user_id(db=db, authorization=f"Bearer {token}")

    assert current_user_id == "user_42"


def test_create_room_persists_room_and_admin_member() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    response = create_room(
        CreateRoomRequest(name="Alpha Room", preferred_lang="en"),
        db=db,
        current_user_id="user_1",
    )

    assert response.room_id.startswith("room_")
    assert response.role == "admin"
    assert response.preferred_lang == "en"
    assert db.add.call_count == 2
    db.commit.assert_called_once()


def test_list_rooms_returns_memberships_for_current_user() -> None:
    db = MagicMock()
    room = Room(id="room_1", name="Alpha", default_translation_mode="balanced", created_at=datetime.now(timezone.utc))
    membership = RoomMember(
        room_id="room_1",
        user_id="user_1",
        role="admin",
        preferred_lang="en",
        created_at=datetime.now(timezone.utc),
    )
    db.scalars.return_value.all.return_value = [membership]
    db.get.side_effect = [room]

    response = list_rooms(db=db, current_user_id="user_1")

    assert len(response) == 1
    assert response[0].room_id == "room_1"
    assert response[0].name == "Alpha"


def test_upsert_membership_rejects_non_admin() -> None:
    db = MagicMock()
    room = Room(id="room_1", name="Alpha", default_translation_mode="balanced", created_at=datetime.now(timezone.utc))
    db.get.side_effect = [room, None]

    with pytest.raises(HTTPException) as exc:
        upsert_membership(
            room_id="room_1",
            payload=JoinRoomRequest(user_id="user_2", preferred_lang="de"),
            db=db,
            current_user_id="user_1",
        )

    assert exc.value.status_code == 403


def test_list_room_messages_returns_messages_and_translations() -> None:
    db = MagicMock()
    room = Room(id="room_1", name="Alpha", default_translation_mode="balanced", created_at=datetime.now(timezone.utc))
    membership = RoomMember(
        room_id="room_1",
        user_id="user_1",
        role="member",
        preferred_lang="en",
        created_at=datetime.now(timezone.utc),
    )
    message = Message(
        id="msg_1",
        room_id="room_1",
        author_user_id="user_1",
        client_message_id="c1",
        source_lang="en",
        content_original="hello",
        status="original_only",
        version=1,
        created_at=datetime.now(timezone.utc),
    )
    translation = MessageTranslation(
        id=1,
        message_id="msg_1",
        target_lang="fr",
        content="bonjour",
        provider="openai",
        quality_mode="balanced",
        translated_at=datetime.now(timezone.utc),
    )

    db.get.side_effect = [room, None]
    db.scalar.side_effect = [membership]
    db.scalars.side_effect = [[message], [translation]]

    response = list_room_messages(room_id="room_1", db=db, current_user_id="user_1", limit=50)

    assert len(response) == 1
    assert response[0].message_id == "msg_1"
    assert response[0].content_original == "hello"
    assert response[0].translations["fr"].content == "bonjour"


def test_list_room_messages_rejects_non_members() -> None:
    db = MagicMock()
    room = Room(id="room_1", name="Alpha", default_translation_mode="balanced", created_at=datetime.now(timezone.utc))
    db.get.side_effect = [room]
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc:
        list_room_messages(room_id="room_1", db=db, current_user_id="user_2", limit=50)

    assert exc.value.status_code == 403


def test_list_room_messages_filters_by_since_message_id() -> None:
    db = MagicMock()
    room = Room(id="room_1", name="Alpha", default_translation_mode="balanced", created_at=datetime.now(timezone.utc))
    membership = RoomMember(
        room_id="room_1",
        user_id="user_1",
        role="member",
        preferred_lang="en",
        created_at=datetime.now(timezone.utc),
    )
    anchor = Message(
        id="msg_old",
        room_id="room_1",
        author_user_id="user_1",
        client_message_id="c_old",
        source_lang="en",
        content_original="old",
        status="original_only",
        version=1,
        created_at=datetime.now(timezone.utc),
    )
    message = Message(
        id="msg_new",
        room_id="room_1",
        author_user_id="user_2",
        client_message_id="c_new",
        source_lang="en",
        content_original="new",
        status="original_only",
        version=1,
        created_at=datetime.now(timezone.utc),
    )

    db.get.side_effect = [room]
    db.scalar.side_effect = [membership, anchor]
    db.scalars.return_value.all.return_value = [message]

    response = list_room_messages(room_id="room_1", db=db, current_user_id="user_1", limit=50, since_message_id="msg_old")

    assert len(response) == 1
    assert response[0].message_id == "msg_new"


def test_message_is_after_anchor_uses_id_tiebreaker_for_same_timestamp() -> None:
    shared_time = datetime(2026, 8, 11, 1, 2, 3, tzinfo=timezone.utc)
    anchor = Message(
        id="msg_old",
        room_id="room_1",
        author_user_id="user_1",
        client_message_id="c_old",
        source_lang="en",
        content_original="old",
        status="original_only",
        version=1,
        created_at=shared_time,
    )
    newer_message = Message(
        id="msg_new",
        room_id="room_1",
        author_user_id="user_2",
        client_message_id="c_new",
        source_lang="en",
        content_original="new",
        status="original_only",
        version=1,
        created_at=shared_time,
    )
    older_same_time_message = Message(
        id="msg_older",
        room_id="room_1",
        author_user_id="user_3",
        client_message_id="c_older",
        source_lang="en",
        content_original="older",
        status="original_only",
        version=1,
        created_at=shared_time,
    )

    assert _message_is_after_anchor(newer_message, anchor) is True
    assert _message_is_after_anchor(older_same_time_message, anchor) is False
