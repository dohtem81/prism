from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.api.app.api.auth import login
from services.registration.app.api.limits import enforce_registration_limits
from shared.db.models import RegisteredAccount
from shared.schemas.auth import LoginRequest
from shared.security import hash_password
from tests.support.fake_redis import FakeRedis
from tests.support.requests import REQUEST
from fastapi import Response


def _db_with_account() -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = RegisteredAccount(
        id="u1", email="ada@example.com", username="ada", password_hash=hash_password("supersecret1"),
        must_change_password=False, email_verified_at=datetime.now(timezone.utc),
    )
    return db


def _login(password: str, db: MagicMock, username: str = "ada") -> None:
    login(LoginRequest(username_or_email=username, password=password), request=REQUEST, response=Response(), db=db)


def test_account_is_locked_after_repeated_failures(isolated_login_guard: FakeRedis) -> None:
    db = _db_with_account()
    for _ in range(5):
        with pytest.raises(HTTPException) as exc:
            _login("wrong-password", db)
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        _login("supersecret1", db)  # correct password is still refused while locked
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0


def test_successful_login_resets_failure_counter(isolated_login_guard: FakeRedis) -> None:
    db = _db_with_account()
    for _ in range(4):
        with pytest.raises(HTTPException):
            _login("wrong-password", db)
    _login("supersecret1", db)
    for _ in range(4):
        with pytest.raises(HTTPException) as exc:
            _login("wrong-password", db)
        assert exc.value.status_code == 401


def test_unknown_account_is_locked_the_same_way(isolated_login_guard: FakeRedis) -> None:
    db = MagicMock()
    db.scalar.return_value = None
    for _ in range(5):
        with pytest.raises(HTTPException):
            _login("whatever1", db, username="ghost")
    with pytest.raises(HTTPException) as exc:
        _login("whatever1", db, username="ghost")
    assert exc.value.status_code == 429


def test_login_ip_limit_applies_across_identifiers(isolated_login_guard: FakeRedis) -> None:
    db = MagicMock()
    db.scalar.return_value = None
    statuses = []
    for i in range(22):
        with pytest.raises(HTTPException) as exc:
            _login("whatever1", db, username=f"user{i}")
        statuses.append(exc.value.status_code)
    assert statuses[:20] == [401] * 20
    assert statuses[20:] == [429, 429]


def test_registration_ip_limit_blocks_sixth_attempt_per_hour() -> None:
    cache = FakeRedis()
    for i in range(5):
        enforce_registration_limits(REQUEST, cache, f"user{i}@example.com")
    with pytest.raises(HTTPException) as exc:
        enforce_registration_limits(REQUEST, cache, "another@example.com")
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers
