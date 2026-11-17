from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient

from services.api.app.api.auth import demo_login
from services.api.app.api.rooms import create_room, join_room, upsert_membership
from services.api.app.api.users import create_user
from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.db import get_db
from services.api.app.main import app
from shared.db.models import DemoBotJob, Room, RoomMember, User
from shared.demo import DEMO_ROOM_ID
from shared.schemas.auth import DemoRequest
from shared.schemas.rooms import CreateRoomRequest, JoinRoomRequest, JoinRoomSelfRequest
from shared.schemas.users import CreateUserRequest


def test_demo_creates_identity_membership_and_session() -> None:
    db = MagicMock()
    db.get.return_value = Room(id=DEMO_ROOM_ID, name="General")
    request = MagicMock()
    request.headers.get.return_value = "http://localhost:8000"
    response = Response()
    with patch("services.api.app.api.auth.issue_token_pair", return_value=("access", "refresh")):
        result = demo_login(DemoRequest(display_name="  Ada  ", preferred_lang="fr"), request, response, db)

    user, member, job = [call.args[0] for call in db.add.call_args_list]
    assert isinstance(user, User) and user.is_demo and user.display_name == "Ada"
    assert user.preferred_lang == "fr"
    assert isinstance(member, RoomMember) and member.user_id == user.id == result.user_id
    assert member.room_id == DEMO_ROOM_ID and member.role == "member" and member.preferred_lang == "fr"
    assert isinstance(job, DemoBotJob) and job.kind == "greeting" and job.source_id == user.id
    assert "prism_access=access" in response.headers["set-cookie"]
    db.commit.assert_called_once()


def test_demo_http_rejects_bad_input_and_origin() -> None:
    client = TestClient(app)
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    try:
        for data in (
            {"display_name": "  ", "preferred_lang": "en"},
            {"display_name": "Ada", "preferred_lang": "english"},
            {"display_name": "Ada", "preferred_lang": "EN"},
        ):
            assert client.post("/v1/auth/demo", json=data, headers={"Origin": "http://localhost:8000"}).status_code == 422
        response = client.post(
            "/v1/auth/demo", json={"display_name": "Ada"}, headers={"Origin": "https://evil.example"}
        )
        assert response.status_code == 403
        db.add.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_demo_room_unavailable_does_not_create_identity() -> None:
    db = MagicMock()
    db.get.return_value = None
    request = MagicMock()
    request.headers.get.return_value = "http://localhost:8000"
    with pytest.raises(HTTPException) as exc:
        demo_login(DemoRequest(display_name="Ada"), request, Response(), db)
    assert exc.value.status_code == 503
    db.add.assert_not_called()


def test_demo_creation_is_rate_limited_per_ip() -> None:
    db = MagicMock()
    db.get.return_value = Room(id=DEMO_ROOM_ID, name="General")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("services.api.app.api.auth.issue_token_pair", return_value=("access", "refresh")):
            client = TestClient(app)
            for _ in range(10):
                response = client.post(
                    "/v1/auth/demo", json={"display_name": "Guest"}, headers={"Origin": "http://localhost:8000"}
                )
                assert response.status_code == 200
            response = client.post(
                "/v1/auth/demo", json={"display_name": "Guest"}, headers={"Origin": "http://localhost:8000"}
            )
            assert response.status_code == 429
            assert db.commit.call_count == 10
    finally:
        app.dependency_overrides.clear()


def test_demo_cannot_create_or_join_other_rooms() -> None:
    db = MagicMock()
    db.scalar.return_value = True
    with pytest.raises(HTTPException) as exc:
        create_room(CreateRoomRequest(name="Other"), db, "guest")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        join_room("other", JoinRoomSelfRequest(preferred_lang="en"), db, "guest")
    assert exc.value.status_code == 403
    db.add.assert_not_called()


def test_admin_cannot_add_demo_user_to_other_room() -> None:
    db = MagicMock()
    db.get.return_value = Room(id="other", name="Other")
    db.scalar.side_effect = [RoomMember(role="admin"), True]
    with pytest.raises(HTTPException) as exc:
        upsert_membership("other", JoinRoomRequest(user_id="guest", preferred_lang="en"), db, "owner")
    assert exc.value.status_code == 403
    db.add.assert_not_called()


def test_demo_language_change_updates_membership() -> None:
    db = MagicMock()
    user = User(id="guest", is_demo=True, display_name="Ada", preferred_lang="en", created_at=datetime.now(timezone.utc))
    member = RoomMember(room_id=DEMO_ROOM_ID, user_id="guest", role="member", preferred_lang="en")
    db.scalar.side_effect = [user, member]
    create_user(CreateUserRequest(display_name="Ada", preferred_lang="pl"), db, "guest")
    assert user.preferred_lang == member.preferred_lang == "pl"
    db.commit.assert_called_once()


def test_demo_room_page_hides_room_controls() -> None:
    db = MagicMock()
    db.scalar.side_effect = [Room(id=DEMO_ROOM_ID, name="General"), RoomMember(role="member", preferred_lang="en")]
    db.get.return_value = User(id="guest", is_demo=True, display_name="Ada", preferred_lang="en")
    app.dependency_overrides[get_current_user_id] = lambda: "guest"
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get(f"/ui/rooms/{DEMO_ROOM_ID}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert 'id="menuCreate" hidden' in response.text
    assert 'id="menuJoin" hidden' in response.text
    assert 'const isDemo = true;' in response.text
