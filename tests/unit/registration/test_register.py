from datetime import datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.responses import JSONResponse

from services.registration.app.api import register as register_module
from services.registration.app.api.register import register_account
from shared.db.models import RegisteredAccount
from shared.schemas.registration import RegisterAccountRequest
from tests.support.requests import REQUEST


def _payload(**overrides) -> RegisterAccountRequest:
    data = {
        "email": "ada@example.com",
        "username": "ada",
        "password": "supersecret1",
        "turnstile_token": "valid-token",
    }
    data.update(overrides)
    return RegisterAccountRequest(**data)


@pytest.fixture
def allow_turnstile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(register_module, "_verify_turnstile", lambda token: True)


def test_register_account_creates_new_account_when_email_and_username_are_free(allow_turnstile: None) -> None:
    db = MagicMock()
    db.scalar.return_value = None
    cache = MagicMock()
    cache.exists.return_value = 0

    response = register_account(_payload(), request=REQUEST, db=db, cache=cache)

    assert not isinstance(response, JSONResponse)
    assert response.email == "ada@example.com"
    assert response.username == "ada"
    assert db.add.call_count == 3  # user, account, verification token
    db.commit.assert_called_once()
    assert cache.set.call_count == 2


def test_register_account_returns_conflict_when_email_already_cached(allow_turnstile: None) -> None:
    db = MagicMock()
    cache = MagicMock()
    cache.exists.side_effect = [1, 0]

    response = register_account(_payload(), request=REQUEST, db=db, cache=cache)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert db.add.call_count == 0


def test_register_account_reserves_admin_username_case_insensitively(allow_turnstile: None) -> None:
    db = MagicMock()
    cache = MagicMock()

    response = register_account(_payload(username="Admin"), request=REQUEST, db=db, cache=cache)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert db.add.call_count == 0


def test_register_account_returns_conflict_when_email_already_in_db(allow_turnstile: None) -> None:
    db = MagicMock()
    cache = MagicMock()
    cache.exists.return_value = 0
    db.scalar.return_value = RegisteredAccount(
        id="user_1",
        email="ada@example.com",
        username="ada",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )

    response = register_account(_payload(), request=REQUEST, db=db, cache=cache)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert db.add.call_count == 0


def test_register_account_rejects_invalid_turnstile_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(register_module, "_verify_turnstile", lambda token: False)
    db = MagicMock()
    cache = MagicMock()

    response = register_account(_payload(), request=REQUEST, db=db, cache=cache)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 403
    assert db.add.call_count == 0


def test_verify_turnstile_requires_success_action_and_allowed_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = register_module.settings
    monkeypatch.setattr(settings, "turnstile_secret", "test-secret")
    monkeypatch.setattr(settings, "turnstile_hostnames", "localhost,127.0.0.1")
    monkeypatch.setattr(
        register_module.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", register_module._TURNSTILE_VERIFY_URL),
            json={"success": True, "action": "signup", "hostname": "localhost"},
        ),
    )

    assert register_module._verify_turnstile("valid-token") is True

    monkeypatch.setattr(
        register_module.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", register_module._TURNSTILE_VERIFY_URL),
            json={"success": True, "action": "login", "hostname": "localhost"},
        ),
    )
    assert register_module._verify_turnstile("valid-token") is False

    monkeypatch.setattr(
        register_module.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("POST", register_module._TURNSTILE_VERIFY_URL),
            json={"success": True, "action": "signup", "hostname": "example.com"},
        ),
    )
    assert register_module._verify_turnstile("valid-token") is False
