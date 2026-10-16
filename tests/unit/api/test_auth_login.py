from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

from services.api.app.api.auth import change_password, login
from services.api.app.auth import bootstrap
from services.api.app.auth import dependencies
from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.db import get_db
from services.api.app.main import app
from shared.schemas.auth import LoginRequest, PasswordChangeRequest
from shared.db.models import RegisteredAccount
from shared.security import hash_password, verify_password


def _account(**overrides) -> RegisteredAccount:
    data = {
        "id": "user_1",
        "email": "ada@example.com",
        "username": "ada",
        "password_hash": hash_password("supersecret1"),
        "must_change_password": False,
        "created_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return RegisteredAccount(**data)


def test_login_succeeds_with_correct_username_and_password() -> None:
    db = MagicMock()
    db.scalar.return_value = _account()
    cookie_response = Response()

    response = login(LoginRequest(username_or_email="ada", password="supersecret1"), response=cookie_response, db=db)

    assert response.user_id == "user_1"
    cookie_headers = " ".join(cookie_response.headers.getlist("set-cookie"))
    assert "prism_access=" in cookie_headers
    assert "prism_refresh=" in cookie_headers
    assert "httponly" in cookie_headers.lower()
    assert "secure" in cookie_headers.lower()


def test_http_login_sets_cookies_without_returning_tokens() -> None:
    db = MagicMock()
    db.scalar.return_value = _account()
    app.dependency_overrides[get_db] = lambda: db

    try:
        with (
            patch("services.api.app.api.auth.verify_password", return_value=True),
            patch("services.api.app.api.auth.issue_token_pair", return_value=("access-secret", "refresh-secret")),
        ):
            response = TestClient(app).post(
                "/v1/auth/login",
                json={"username_or_email": "ada", "password": "supersecret1"},
                headers={"Origin": "http://localhost:8000"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"user_id": "user_1"}
    assert "access-secret" not in response.text
    assert "refresh-secret" not in response.text
    assert "prism_access=access-secret" in response.headers.get("set-cookie", "")


def test_cookie_auth_rejects_cross_origin_mutation() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"origin", b"https://attacker.example")],
            "scheme": "https",
            "server": ("prism.example", 443),
            "path": "/v1/rooms",
            "query_string": b"",
        }
    )

    with pytest.raises(HTTPException) as exc:
        dependencies.get_current_user_id(request=request, access_cookie="access-token")

    assert exc.value.status_code == 403


def test_dashboard_renders_server_authenticated_identity() -> None:
    app.dependency_overrides[get_current_user_id] = lambda: "user_1"

    try:
        response = TestClient(app).get("/ui")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'const activeUserId = "user_1";' in response.text
    assert "const accessTokenTtlSeconds = 1800;" in response.text
    assert "token=" not in response.text


def test_login_rejects_wrong_password() -> None:
    db = MagicMock()
    db.scalar.return_value = _account()

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username_or_email="ada", password="wrong-password"), response=Response(), db=db)

    assert exc.value.status_code == 401


def test_login_rejects_unknown_account() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username_or_email="nobody", password="supersecret1"), response=Response(), db=db)

    assert exc.value.status_code == 401


def test_login_requires_bootstrap_admin_password_change() -> None:
    db = MagicMock()
    db.scalar.return_value = _account(
        id="admin",
        username="admin",
        password_hash=hash_password("password123"),
        must_change_password=True,
    )

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username_or_email="admin", password="password123"), response=Response(), db=db)

    assert exc.value.status_code == 428


def test_password_change_updates_bootstrap_password_and_issues_tokens() -> None:
    from unittest.mock import patch

    account = _account(
        id="admin",
        username="admin",
        password_hash=hash_password("password123"),
        must_change_password=True,
    )
    db = MagicMock()
    db.scalar.return_value = account
    cookie_response = Response()

    with patch("services.api.app.api.auth.issue_token_pair", return_value=("access", "refresh")):
        response = change_password(
            PasswordChangeRequest(
                username_or_email="admin",
                current_password="password123",
                new_password="a-new-secure-password",
            ),
            response=cookie_response,
            db=db,
        )

    assert response.user_id == "admin"
    assert "prism_access=access" in " ".join(cookie_response.headers.getlist("set-cookie"))
    assert account.must_change_password is False
    assert verify_password("a-new-secure-password", account.password_hash)
    db.commit.assert_called_once()


def test_bootstrap_creates_admin_with_default_password_and_rotation_required() -> None:
    from unittest.mock import patch

    db = MagicMock()
    db.__enter__.return_value = db
    db.scalar.return_value = None
    db.get.return_value = None

    with patch.object(bootstrap, "SessionLocal", return_value=db):
        bootstrap.ensure_default_admin_account()

    seeded = db.add.call_args_list[1].args[0]
    assert seeded.id == "admin"
    assert seeded.username == "admin"
    assert seeded.must_change_password is True
    assert verify_password("password123", seeded.password_hash)
    db.commit.assert_called_once()
