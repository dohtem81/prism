import logging
from unittest.mock import MagicMock, patch

import pytest
import redis
from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.api.app.api.rooms import mark_messages_seen
from services.api.app.auth import dependencies
from services.api.app.auth import security_events as events
from services.api.app.auth.dependencies import (
    create_access_token,
    create_refresh_token,
    resolve_authenticated_user_id,
)
from services.api.app.auth.security_events import SecurityEvents, security_events
from services.api.app.auth.token_store import RefreshState
from services.api.app.infra.settings import settings
from services.api.app.main import app
from shared.schemas.rooms import MarkSeenRequest


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    def hincrby(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = str(int(bucket.get(field, "0")) + amount)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))


@pytest.fixture()
def fake_redis():
    fake = FakeRedis()
    with patch.object(security_events, "_client", fake):
        yield fake


def _security_records(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "security_event", None) == event]


def test_invalid_token_emits_auth_rejected_and_counts(fake_redis, caplog) -> None:
    with caplog.at_level(logging.INFO):
        with pytest.raises(HTTPException) as exc:
            resolve_authenticated_user_id("not-a-real-token")

    assert exc.value.status_code == 401
    record = _security_records(caplog, events.AUTH_REJECTED)[0]
    assert record.levelno == logging.WARNING
    assert record.reason == "invalid_token"
    assert record.correlation_id
    assert hasattr(record, "trace_id") and hasattr(record, "span_id")
    assert record.timestamp
    assert "not-a-real-token" not in record.getMessage()
    assert fake_redis.hashes[events.BY_EVENT_KEY] == {events.AUTH_REJECTED: "1"}


def test_expired_token_is_reported_as_expired(fake_redis, caplog) -> None:
    with patch.object(settings, "access_token_ttl_minutes", -1):
        expired = create_access_token("user_1")

    with caplog.at_level(logging.INFO):
        with pytest.raises(HTTPException):
            resolve_authenticated_user_id(expired)

    record = _security_records(caplog, events.AUTH_REJECTED)[0]
    assert record.reason == "expired"
    assert expired not in str(record.__dict__)


def test_wrong_type_and_revoked_tokens_are_reported(fake_redis, caplog) -> None:
    with patch.object(dependencies.token_store, "store_refresh"):
        refresh = create_refresh_token("user_1")
    access = create_access_token("user_1")

    with caplog.at_level(logging.INFO):
        with pytest.raises(HTTPException):
            resolve_authenticated_user_id(refresh)
        with patch.object(dependencies.token_store, "is_revoked", return_value=True):
            with pytest.raises(HTTPException):
                resolve_authenticated_user_id(access)

    reasons = [r.reason for r in _security_records(caplog, events.AUTH_REJECTED)]
    assert reasons == ["wrong_type", "revoked"]
    assert fake_redis.hashes[events.BY_USER_KEY] == {"user_1": "2"}


def test_membership_denied_is_logged_and_counted(fake_redis, caplog) -> None:
    db = MagicMock()
    db.scalar.return_value = None

    with caplog.at_level(logging.INFO):
        with pytest.raises(HTTPException) as exc:
            mark_messages_seen("room_9", MarkSeenRequest(message_ids=["m1"]), db=db, current_user_id="intruder")

    assert exc.value.status_code == 403
    record = _security_records(caplog, events.MEMBERSHIP_DENIED)[0]
    assert (record.user_id, record.room_id, record.reason) == ("intruder", "room_9", "not_a_member")
    assert fake_redis.hashes[events.BY_EVENT_KEY][events.MEMBERSHIP_DENIED] == "1"
    assert fake_redis.hashes[events.BY_ROOM_KEY] == {"room_9": "1"}


def test_refresh_token_reuse_emits_token_reused_and_counts(fake_redis, caplog) -> None:
    with patch.object(dependencies.token_store, "store_refresh"):
        refresh = create_refresh_token("user_1")

    with patch.object(dependencies.token_store, "consume_refresh", return_value=(RefreshState.REUSED, "user_1")), patch.object(
        dependencies.token_store, "revoke_all_sessions", return_value=2
    ):
        with caplog.at_level(logging.INFO):
            response = TestClient(app).post("/v1/auth/refresh", json={"refresh_token": refresh})

    assert response.status_code == 401
    record = _security_records(caplog, events.TOKEN_REUSED)[0]
    assert (record.user_id, record.reason) == ("user_1", "refresh_token_reused")
    assert fake_redis.hashes[events.BY_EVENT_KEY][events.TOKEN_REUSED] == "1"


def test_logout_is_logged_but_not_counted(fake_redis, caplog) -> None:
    access = create_access_token("user_1")

    with patch.object(dependencies.token_store, "revoke"):
        with caplog.at_level(logging.INFO):
            response = TestClient(app).post("/v1/auth/logout", headers={"Authorization": f"Bearer {access}"})

    assert response.status_code == 204
    record = _security_records(caplog, events.LOGOUT)[0]
    assert record.levelno == logging.INFO and record.user_id == "user_1"
    assert fake_redis.hashes == {}


def test_admin_endpoint_returns_recorded_violation_counts(fake_redis) -> None:
    security_events.record(events.AUTH_REJECTED, reason="invalid_token", user_id="user_a")
    security_events.record(events.AUTH_REJECTED, reason="expired", user_id="user_a")
    security_events.record(events.MEMBERSHIP_DENIED, reason="not_a_member", user_id="user_b", room_id="room_1")
    security_events.record(events.TOKEN_REUSED, reason="refresh_token_reused", user_id="user_a")

    access = create_access_token("operator")
    with patch.object(dependencies.token_store, "is_revoked", return_value=False):
        response = TestClient(app).get(
            "/v1/admin/auth/violations", headers={"Authorization": f"Bearer {access}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["by_scope"][0] == {"key": events.AUTH_REJECTED, "count": 2}
    assert {"key": events.MEMBERSHIP_DENIED, "count": 1} in body["by_scope"]
    assert {"key": events.TOKEN_REUSED, "count": 1} in body["by_scope"]
    assert body["top_offenders"][0] == {"key": "user_a", "count": 3}
    assert body["top_rooms"] == [{"key": "room_1", "count": 1}]


def test_admin_endpoint_requires_authentication(fake_redis) -> None:
    response = TestClient(app).get("/v1/admin/auth/violations")

    assert response.status_code == 401
    assert fake_redis.hashes[events.BY_EVENT_KEY] == {events.AUTH_REJECTED: "1"}


def test_counters_fail_open_when_redis_is_unavailable() -> None:
    broken = MagicMock()
    broken.hincrby.side_effect = redis.exceptions.ConnectionError
    broken.hgetall.side_effect = redis.exceptions.ConnectionError
    store = SecurityEvents(broken)

    store.record(events.AUTH_REJECTED, reason="invalid_token", user_id="u")

    assert store.get_violation_summary()["available"] is False
