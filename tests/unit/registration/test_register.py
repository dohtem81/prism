from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.responses import JSONResponse

from services.registration.app.api.register import register_account
from shared.db.models import RegisteredAccount
from shared.schemas.registration import RegisterAccountRequest


def _payload(**overrides) -> RegisterAccountRequest:
    data = {"email": "ada@example.com", "username": "ada", "password": "supersecret1"}
    data.update(overrides)
    return RegisterAccountRequest(**data)


def test_register_account_creates_new_account_when_email_and_username_are_free() -> None:
    db = MagicMock()
    db.scalar.return_value = None
    cache = MagicMock()
    cache.exists.return_value = 0

    response = register_account(_payload(), db=db, cache=cache)

    assert not isinstance(response, JSONResponse)
    assert response.email == "ada@example.com"
    assert response.username == "ada"
    assert db.add.call_count == 2
    db.commit.assert_called_once()
    assert cache.set.call_count == 2


def test_register_account_returns_conflict_when_email_already_cached() -> None:
    db = MagicMock()
    cache = MagicMock()
    cache.exists.side_effect = [1, 0]

    response = register_account(_payload(), db=db, cache=cache)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert db.add.call_count == 0


def test_register_account_returns_conflict_when_email_already_in_db() -> None:
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

    response = register_account(_payload(), db=db, cache=cache)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert db.add.call_count == 0
