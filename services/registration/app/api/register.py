import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.registration.app.api.limits import enforce_registration_limits
from shared.email_verification import issue_token, send_verification_email
from shared.logging_utils import get_logger

from services.registration.app.infra.db import get_db
from services.registration.app.infra.redis_client import get_redis
from services.registration.app.infra.settings import settings
from services.registration.app.security import hash_password
from shared.db.models import RegisteredAccount, User
from shared.schemas.registration import RegisterAccountError, RegisterAccountRequest, RegisterAccountResponse

router = APIRouter(prefix="/v1", tags=["registration"])
logger = get_logger("prism.registration.register")

_EMAIL_CACHE_PREFIX = "registration:email:"
_USERNAME_CACHE_PREFIX = "registration:username:"
_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _verify_turnstile(token: str) -> bool:
    expected_hostnames = {
        hostname.strip().lower()
        for hostname in settings.turnstile_hostnames.split(",")
        if hostname.strip()
    }
    if not settings.turnstile_secret or not expected_hostnames:
        return False

    try:
        response = httpx.post(
            _TURNSTILE_VERIFY_URL,
            data={"secret": settings.turnstile_secret, "response": token},
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError):
        return False

    return (
        isinstance(result, dict)
        and result.get("success") is True
        and result.get("action") == "signup"
        and isinstance(result.get("hostname"), str)
        and result["hostname"].lower() in expected_hostnames
    )


def _already_exists(db: Session, cache: Redis, email: str, username: str) -> bool:
    if cache.exists(_EMAIL_CACHE_PREFIX + email.lower()) or cache.exists(_USERNAME_CACHE_PREFIX + username.lower()):
        return True
    existing = db.scalar(
        select(RegisteredAccount).where(
            (RegisteredAccount.email == email) | (RegisteredAccount.username == username)
        )
    )
    return existing is not None


def _conflict_response(detail: str = "An account with this email or username already exists.") -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=RegisterAccountError(
            error="account_already_exists",
            detail=detail,
            redirect_url=settings.auth_service_url,
        ).model_dump(),
        headers={"Location": settings.auth_service_url},
    )


@router.post("/register", response_model=RegisterAccountResponse, responses={409: {"model": RegisterAccountError}})
def register_account(
    payload: RegisterAccountRequest,
    request: Request,
    db: Session = Depends(get_db),
    cache: Redis = Depends(get_redis),
) -> RegisterAccountResponse | JSONResponse:
    enforce_registration_limits(request, cache, payload.email)
    if not _verify_turnstile(payload.turnstile_token):
        return JSONResponse(status_code=403, content={"detail": "Turnstile verification failed."})
    if payload.username.casefold() == "admin":
        return _conflict_response("The username 'admin' is reserved.")
    if _already_exists(db, cache, payload.email, payload.username):
        return _conflict_response()

    user_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    account = RegisteredAccount(
        id=user_id,
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        created_at=now,
    )
    # Same id as the account: rooms/messages reference users.id regardless of auth storage.
    db.add(User(id=user_id, display_name=payload.username, created_at=now))
    db.flush()
    db.add(account)
    try:
        verification_token = issue_token(db, user_id)
        db.commit()
    except IntegrityError:
        # Concurrent registration slipped past the cache/pre-check race window.
        db.rollback()
        return _conflict_response()
    db.refresh(account)

    cache.set(_EMAIL_CACHE_PREFIX + account.email.lower(), account.id, ex=settings.redis_cache_ttl_seconds)
    cache.set(_USERNAME_CACHE_PREFIX + account.username.lower(), account.id, ex=settings.redis_cache_ttl_seconds)

    try:
        send_verification_email(account.email, account.username, verification_token)
    except Exception:
        # The account exists; the user can request another email from the login page.
        logger.exception("verification_email_failed")

    return RegisterAccountResponse(
        user_id=account.id,
        email=account.email,
        username=account.username,
        created_at=account.created_at,
    )
