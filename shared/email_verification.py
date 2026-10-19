import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.db.models import EmailVerificationToken, RegisteredAccount
from shared.mailer import send_email

TOKEN_TTL = timedelta(hours=24)


class VerificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Origin used to build the link in the email; must be reachable by the user's browser.
    public_base_url: str = "https://localhost"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db: Session, account_id: str) -> str:
    """Create a fresh token (replacing unused ones) and return the raw value; caller commits."""
    # Sessions here run with autoflush off; the account row must exist before its token is inserted.
    db.flush()
    db.execute(
        delete(EmailVerificationToken).where(
            EmailVerificationToken.account_id == account_id, EmailVerificationToken.used_at.is_(None)
        )
    )
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        EmailVerificationToken(
            account_id=account_id, token_hash=_hash(raw), expires_at=now + TOKEN_TTL, created_at=now
        )
    )
    return raw


def verification_link(token: str, settings: VerificationSettings | None = None) -> str:
    base = (settings or VerificationSettings()).public_base_url.rstrip("/")
    # Fragment keeps the token out of server logs and Referer headers.
    return f"{base}/ui/verify#token={token}"


def send_verification_email(email: str, username: str, token: str) -> None:
    link = verification_link(token)
    send_email(
        email,
        "Verify your Prism email",
        f"Hi {username},\n\nConfirm your email to activate your Prism account:\n\n{link}\n\n"
        "The link is valid for 24 hours. If you did not register, ignore this message.\n",
    )


def consume_token(db: Session, raw_token: str) -> RegisteredAccount | None:
    """Mark the token used and the account verified; returns None for unknown, used or expired tokens."""
    record = db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == _hash(raw_token)))
    now = datetime.now(timezone.utc)
    if record is None or record.used_at is not None or record.expires_at <= now:
        return None
    account = db.get(RegisteredAccount, record.account_id)
    if account is None:
        return None
    record.used_at = now
    if account.email_verified_at is None:
        account.email_verified_at = now
    return account
