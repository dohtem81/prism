from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.api.app.api.rooms import create_room, list_rooms, upsert_membership
from services.api.app.auth.dependencies import create_access_token, get_current_user_id
from shared.db.models import Room, RoomMember
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
