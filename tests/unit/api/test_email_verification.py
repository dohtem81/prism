from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException, Response

from services.api.app.api import auth as auth_module
from services.api.app.api.auth import login, resend_verification, verify_email
from shared import email_verification
from shared.db.models import EmailVerificationToken, RegisteredAccount
from shared.schemas.auth import LoginRequest, ResendVerificationRequest, VerifyEmailRequest
from shared.security import hash_password
from tests.support.fake_redis import FakeRedis
from tests.support.requests import REQUEST


def _account(verified: bool) -> RegisteredAccount:
    return RegisteredAccount(
        id="u1",
        email="ada@example.com",
        username="ada",
        password_hash=hash_password("supersecret1"),
        must_change_password=False,
        email_verified_at=datetime.now(timezone.utc) if verified else None,
    )


def test_login_returns_403_until_email_is_verified(isolated_login_guard: FakeRedis) -> None:
    db = MagicMock()
    db.scalar.return_value = _account(verified=False)

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username_or_email="ada", password="supersecret1"), request=REQUEST, response=Response(), db=db)

    assert exc.value.status_code == 403
    assert "Verify your email" in exc.value.detail


def test_wrong_password_for_unverified_account_still_returns_401(isolated_login_guard: FakeRedis) -> None:
    db = MagicMock()
    db.scalar.return_value = _account(verified=False)

    with pytest.raises(HTTPException) as exc:
        login(LoginRequest(username_or_email="ada", password="nope-nope1"), request=REQUEST, response=Response(), db=db)

    assert exc.value.status_code == 401


def _token_record(**overrides) -> EmailVerificationToken:
    data = {
        "account_id": "u1",
        "token_hash": email_verification._hash("raw-token"),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "used_at": None,
    }
    data.update(overrides)
    return EmailVerificationToken(**data)


def test_verify_email_marks_account_verified_and_token_used(isolated_login_guard: FakeRedis) -> None:
    db = MagicMock()
    record = _token_record()
    account = _account(verified=False)
    db.scalar.return_value = record
    db.get.return_value = account

    result = verify_email(VerifyEmailRequest(token="raw-token"), REQUEST, db=db)

    assert result == {"status": "verified"}
    assert account.email_verified_at is not None
    assert record.used_at is not None
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    "record",
    [
        None,
        _token_record(used_at=datetime.now(timezone.utc)),
        _token_record(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)),
    ],
)
def test_verify_email_rejects_unknown_used_or_expired_token(record, isolated_login_guard: FakeRedis) -> None:
    db = MagicMock()
    db.scalar.return_value = record

    with pytest.raises(HTTPException) as exc:
        verify_email(VerifyEmailRequest(token="raw-token"), REQUEST, db=db)

    assert exc.value.status_code == 400
    db.commit.assert_not_called()


def test_resend_queues_email_only_for_unverified_account(isolated_login_guard: FakeRedis, monkeypatch) -> None:
    sent: list[tuple] = []
    monkeypatch.setattr(auth_module, "send_verification_email", lambda *args: sent.append(args))
    db = MagicMock()
    db.scalar.return_value = _account(verified=False)
    tasks = BackgroundTasks()

    result = resend_verification(ResendVerificationRequest(username_or_email="ada"), REQUEST, tasks, db=db)
    assert result == {"status": "accepted"}
    assert len(tasks.tasks) == 1

    db.scalar.return_value = _account(verified=True)
    other_tasks = BackgroundTasks()
    assert resend_verification(ResendVerificationRequest(username_or_email="ada"), REQUEST, other_tasks, db=db) == {
        "status": "accepted"
    }
    assert other_tasks.tasks == []

    db.scalar.return_value = None
    unknown_tasks = BackgroundTasks()
    assert resend_verification(ResendVerificationRequest(username_or_email="ghost"), REQUEST, unknown_tasks, db=db) == {
        "status": "accepted"
    }
    assert unknown_tasks.tasks == []


def test_resend_is_rate_limited_per_identifier(isolated_login_guard: FakeRedis) -> None:
    db = MagicMock()
    db.scalar.return_value = None
    for _ in range(5):
        resend_verification(ResendVerificationRequest(username_or_email="ada"), REQUEST, BackgroundTasks(), db=db)

    with pytest.raises(HTTPException) as exc:
        resend_verification(ResendVerificationRequest(username_or_email="ada"), REQUEST, BackgroundTasks(), db=db)
    assert exc.value.status_code == 429


def test_issue_token_flushes_pending_account_before_inserting_token() -> None:
    db = MagicMock()
    email_verification.issue_token(db, "u1")

    names = [call[0] for call in db.method_calls]
    assert names.index("flush") < names.index("add")


def test_verification_link_uses_fragment_for_token() -> None:
    settings = email_verification.VerificationSettings(public_base_url="https://chat.example.com/")
    assert email_verification.verification_link("abc", settings) == "https://chat.example.com/ui/verify#token=abc"
