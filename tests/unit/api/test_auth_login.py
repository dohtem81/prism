from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from services.api.app.api.auth import login
from shared.db.models import RegisteredAccount
from shared.schemas.auth import LoginRequest
from shared.security import hash_password


def _account(**overrides) -> RegisteredAccount:
    data = {
        "id": "user_1",
        "email": "ada@example.com",
        "username": "ada",
        "password_hash": hash_password("supersecret1"),
        "created_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return RegisteredAccount(**data)


def test_login_succeeds_with_correct_username_and_password() -> None:
    db = MagicMock()
    db.scalar.return_value = _account()

    response = login(LoginRequest(username_or_email="ada", password="supersecret1"), db=db)

    assert response.user_id == "user_1"
    assert response.token_type == "bearer"
    assert response.access_token


def test_login_rejects_wrong_password() -> None:
    db = MagicMock()
    db.scalar.return_value = _account()

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username_or_email="ada", password="wrong-password"), db=db)

    assert exc.value.status_code == 401


def test_login_rejects_unknown_account() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username_or_email="nobody", password="supersecret1"), db=db)

    assert exc.value.status_code == 401
