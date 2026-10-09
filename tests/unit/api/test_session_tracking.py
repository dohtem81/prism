import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from services.api.app.api import admin as admin_module
from services.api.app.api.auth import login
from services.api.app.auth import dependencies
from services.api.app.auth import security_events as events
from services.api.app.auth.dependencies import (
    ALGORITHM,
    issue_token_pair,
    resolve_authenticated_user_id,
)
from services.api.app.auth.security_events import security_events
from services.api.app.auth.token_store import TokenStore, TokenStoreUnavailable
from services.api.app.infra.settings import settings
from services.api.app.main import app
from shared.schemas.auth import LoginRequest
from tests.support.fake_redis import FakeRedis


@pytest.fixture()
def store():
    fake = FakeRedis()
    token_store = TokenStore(fake)
    token_store.fake = fake  # type: ignore[attr-defined]
    with patch.object(dependencies, "token_store", token_store), patch.object(
        admin_module, "token_store", token_store
    ), patch.object(security_events, "_client", MagicMock()):
        yield token_store


@pytest.fixture()
def client(store):
    return TestClient(app)


def _claims(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _refresh(client: TestClient, refresh_token: str):
    return client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})


def test_login_creates_access_and_refresh_sessions(store) -> None:
    account = SimpleNamespace(id="user_1", password_hash="hash")
    db = MagicMock()
    db.scalar.return_value = account

    with patch("services.api.app.api.auth.verify_password", return_value=True):
        response = login(LoginRequest(username_or_email="user_1", password="pw"), db=db)

    sessions = {s["token_type"]: s for s in store.list_active_sessions("user_1")}
    assert set(sessions) == {"access", "refresh"}
    assert sessions["access"]["jti"] == _claims(response.access_token)["jti"]
    assert sessions["refresh"]["jti"] == _claims(response.refresh_token)["jti"]
    assert sessions["access"]["refresh_jti"] == sessions["refresh"]["jti"]
    for session in sessions.values():
        assert session["issued_at"] and session["last_used_at"]
    assert store.count_active_sessions("user_1") == 1


def test_validating_an_access_token_updates_last_used_at(store) -> None:
    access, _ = issue_token_pair("user_1")
    jti = _claims(access)["jti"]
    stale = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store.fake.hashes[f"auth:session:user_1:{jti}"]["last_used_at"] = stale

    assert resolve_authenticated_user_id(access) == "user_1"

    session = store.get_session("user_1", jti)
    assert session["last_used_at"] > stale
    assert session["issued_at"] <= session["last_used_at"]


def test_refresh_rotates_session_records(client, store) -> None:
    _, old_refresh = issue_token_pair("user_1")
    old_jti = _claims(old_refresh)["jti"]

    response = _refresh(client, old_refresh)

    assert response.status_code == 200
    new_refresh_jti = _claims(response.json()["refresh_token"])["jti"]
    assert store.get_session("user_1", old_jti) is None
    new_session = store.get_session("user_1", new_refresh_jti)
    assert new_session and new_session["token_type"] == "refresh"
    assert store.count_active_sessions("user_1") == 1


def test_logout_ends_session_and_denylists_token(client, store) -> None:
    access, refresh = issue_token_pair("user_1")
    claims = _claims(access)

    response = client.post("/v1/auth/logout", headers=_auth(access))

    assert response.status_code == 204
    assert store.get_session("user_1", claims["jti"]) is None
    assert store.is_revoked(claims["jti"]) is True
    assert store.count_active_sessions("user_1") == 0  # the linked refresh session ended too
    assert _refresh(client, refresh).status_code == 401
    with pytest.raises(HTTPException):
        resolve_authenticated_user_id(access)
    assert store.get_recent_revocations()[0]["reason"] == "logout"


def test_logout_only_ends_the_current_session(client, store) -> None:
    access_a, _ = issue_token_pair("user_1")
    access_b, refresh_b = issue_token_pair("user_1")

    client.post("/v1/auth/logout", headers=_auth(access_a))

    assert store.count_active_sessions("user_1") == 1
    assert resolve_authenticated_user_id(access_b) == "user_1"
    assert _refresh(client, refresh_b).status_code == 200


def test_refresh_reuse_revokes_all_sessions_for_the_user(client, store, caplog) -> None:
    _, refresh_a = issue_token_pair("user_1")
    access_b, refresh_b = issue_token_pair("user_1")
    access_other, refresh_other = issue_token_pair("user_2")
    assert _refresh(client, refresh_a).status_code == 200  # rotates A

    with caplog.at_level(logging.INFO):
        replay = _refresh(client, refresh_a)

    assert replay.status_code == 401
    assert store.count_active_sessions("user_1") == 0
    with pytest.raises(HTTPException):
        resolve_authenticated_user_id(access_b)
    assert _refresh(client, refresh_b).status_code == 401

    logged = {getattr(r, "security_event", None) for r in caplog.records}
    assert {events.TOKEN_REUSED, events.ALL_SESSIONS_REVOKED} <= logged
    revocation = store.get_recent_revocations()[0]
    assert (revocation["user_id"], revocation["reason"]) == ("user_1", "refresh_token_reuse")
    assert revocation["sessions_revoked"] >= 3

    # Other users are untouched.
    assert resolve_authenticated_user_id(access_other) == "user_2"
    assert _refresh(client, refresh_other).status_code == 200


def test_replaying_a_logged_out_refresh_token_does_not_revoke_other_sessions(client, store) -> None:
    access_a, refresh_a = issue_token_pair("user_1")
    access_b, _ = issue_token_pair("user_1")
    client.post("/v1/auth/logout", headers=_auth(access_a))

    assert _refresh(client, refresh_a).status_code == 401

    assert resolve_authenticated_user_id(access_b) == "user_1"


def test_admin_sessions_endpoint_reports_active_sessions_and_revocations(client, store) -> None:
    issue_token_pair("user_x")
    _, refresh_y = issue_token_pair("user_y")
    assert _refresh(client, refresh_y).status_code == 200
    assert _refresh(client, refresh_y).status_code == 401  # reuse -> user_y revoked
    operator_access, _ = issue_token_pair("operator")

    response = client.get("/v1/admin/auth/sessions", headers=_auth(operator_access))

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["active_sessions"] == 2  # user_x and the operator, one refresh token each
    assert body["users_with_sessions"] == 2
    assert {"key": "user_x", "count": 1} in body["top_users"]
    assert body["active_access_tokens"] >= 2
    revocation = body["recent_revocations"][0]
    assert (revocation["user_id"], revocation["reason"]) == ("user_y", "refresh_token_reuse")
    assert revocation["timestamp"]


def test_admin_sessions_endpoint_requires_authentication(client) -> None:
    assert client.get("/v1/admin/auth/sessions").status_code == 401


def test_issuance_fails_closed_when_session_cannot_be_recorded(store) -> None:
    with patch.object(store, "create_session", side_effect=TokenStoreUnavailable):
        with pytest.raises(HTTPException) as exc:
            issue_token_pair("user_1")

    assert exc.value.status_code == 503


def test_touching_a_session_fails_open(store) -> None:
    access, _ = issue_token_pair("user_1")
    with patch.object(store._client, "hset", side_effect=__import__("redis").exceptions.ConnectionError):
        assert resolve_authenticated_user_id(access) == "user_1"


def test_session_overview_reports_unavailable_when_redis_is_down(store) -> None:
    with patch.object(store._client, "scan_iter", side_effect=__import__("redis").exceptions.ConnectionError):
        overview = store.get_session_overview()

    assert overview["available"] is False
