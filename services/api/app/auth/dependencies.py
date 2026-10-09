from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Query, status
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from services.api.app.auth import security_events as events
from services.api.app.auth.security_events import security_events
from services.api.app.auth.token_store import RefreshState, TokenStoreUnavailable, token_store
from services.api.app.infra.db import get_db
from services.api.app.infra.settings import settings
from shared.logging_utils import get_logger

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"

logger = get_logger("prism.api.auth")


def _unauthorized(detail: str = "Invalid token") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _reject(reason: str, *, user_id: str | None = None, detail: str = "Invalid token") -> HTTPException:
    security_events.record(events.AUTH_REJECTED, reason=reason, user_id=user_id)
    return _unauthorized(detail)


def _encode_token(subject: str, token_type: str, ttl: timedelta) -> tuple[str, str, int]:
    now = datetime.now(timezone.utc)
    jti = uuid4().hex
    expires_at = now + ttl
    payload = {
        "sub": subject,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), jti, int(ttl.total_seconds())


def create_access_token(subject: str) -> str:
    token, _, _ = _encode_token(subject, ACCESS, timedelta(minutes=settings.access_token_ttl_minutes))
    return token


def create_refresh_token(subject: str) -> str:
    token, jti, ttl_seconds = _encode_token(subject, REFRESH, timedelta(days=settings.refresh_token_ttl_days))
    try:
        token_store.store_refresh(jti, subject, ttl_seconds)
    except TokenStoreUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token service unavailable") from exc
    return token


def decode_token(token: str, expected_type: str, *, verify_exp: bool = True) -> dict:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[ALGORITHM], options={"verify_exp": verify_exp}
        )
    except ExpiredSignatureError as exc:
        raise _reject("expired") from exc
    except JWTError as exc:
        raise _reject("invalid_token") from exc

    subject = payload.get("sub")
    if payload.get("type") != expected_type:
        raise _reject("wrong_type", user_id=subject)
    if not subject or not payload.get("jti"):
        raise _reject("missing_claims", user_id=subject)
    return payload


def _remaining_seconds(payload: dict) -> int:
    return int(payload.get("exp", 0)) - int(datetime.now(timezone.utc).timestamp())


def resolve_authenticated_user_id(token: str) -> str:
    if token == "dev-token" and settings.app_env == "dev":
        return "dev-user"

    payload = decode_token(token, ACCESS)

    try:
        revoked = token_store.is_revoked(payload["jti"])
    except TokenStoreUnavailable as exc:
        raise _reject("token_store_unavailable", user_id=payload["sub"], detail="Unable to verify token") from exc
    if revoked:
        raise _reject("revoked", user_id=payload["sub"], detail="Token revoked")

    return str(payload["sub"])


def rotate_refresh_token(refresh_token: str) -> tuple[str, str, str]:
    """Consume a refresh token and return (access_token, new_refresh_token, user_id)."""
    payload = decode_token(refresh_token, REFRESH)

    try:
        state, stored_user_id = token_store.consume_refresh(payload["jti"])
    except TokenStoreUnavailable as exc:
        raise _reject("token_store_unavailable", user_id=payload["sub"], detail="Unable to verify token") from exc

    if state == RefreshState.REUSED:
        security_events.record(events.TOKEN_REUSED, reason="refresh_token_reused", user_id=payload["sub"])
        raise _unauthorized("Token revoked")
    if state != RefreshState.OK or stored_user_id != payload["sub"]:
        raise _reject("refresh_not_registered", user_id=payload["sub"])

    user_id = str(payload["sub"])
    return create_access_token(user_id), create_refresh_token(user_id), user_id


def revoke_session_tokens(access_token: str | None, refresh_token: str | None) -> None:
    """Revoke whichever of the two tokens are valid (signature checked, expiry ignored)."""
    revoked_any = False
    user_id: str | None = None
    try:
        if access_token:
            payload = decode_token(access_token, ACCESS, verify_exp=False)
            user_id = payload["sub"]
            remaining = _remaining_seconds(payload)
            if remaining > 0:
                token_store.revoke(payload["jti"], remaining)
            revoked_any = True
        if refresh_token:
            payload = decode_token(refresh_token, REFRESH, verify_exp=False)
            user_id = payload["sub"]
            token_store.invalidate_refresh(payload["jti"])
            revoked_any = True
    except TokenStoreUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token service unavailable") from exc

    if not revoked_any:
        raise _reject("logout_without_token")
    security_events.record(events.LOGOUT, reason="user_logout", user_id=user_id)


def get_current_user_id(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    token: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> str:
    if not authorization and not token:
        raise _reject("missing_credentials", detail="Missing Authorization header")

    resolved_token = token
    if authorization:
        scheme, _, bearer_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not bearer_token:
            raise _reject("malformed_authorization_header", detail="Invalid Authorization header")
        resolved_token = bearer_token

    return resolve_authenticated_user_id(resolved_token)
