from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Query, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from services.api.app.auth.token_store import RefreshState, TokenStoreUnavailable, token_store
from services.api.app.infra.db import get_db
from services.api.app.infra.settings import settings
from shared.logging_utils import get_correlation_id, get_logger

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"

logger = get_logger("prism.api.auth")


def _unauthorized(detail: str = "Invalid token") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


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
    except JWTError as exc:
        raise _unauthorized() from exc

    if payload.get("type") != expected_type or not payload.get("sub") or not payload.get("jti"):
        raise _unauthorized()
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
        raise _unauthorized("Unable to verify token") from exc
    if revoked:
        raise _unauthorized("Token revoked")

    return str(payload["sub"])


def rotate_refresh_token(refresh_token: str) -> tuple[str, str, str]:
    """Consume a refresh token and return (access_token, new_refresh_token, user_id)."""
    payload = decode_token(refresh_token, REFRESH)

    try:
        state, stored_user_id = token_store.consume_refresh(payload["jti"])
    except TokenStoreUnavailable as exc:
        raise _unauthorized("Unable to verify token") from exc

    if state == RefreshState.REUSED:
        logger.warning(
            "refresh_token_reuse_detected",
            extra={"user_id": payload["sub"], "correlation_id": get_correlation_id()},
        )
        raise _unauthorized("Token revoked")
    if state != RefreshState.OK or stored_user_id != payload["sub"]:
        raise _unauthorized()

    user_id = str(payload["sub"])
    return create_access_token(user_id), create_refresh_token(user_id), user_id


def revoke_session_tokens(access_token: str | None, refresh_token: str | None) -> None:
    """Revoke whichever of the two tokens are valid (signature checked, expiry ignored)."""
    revoked_any = False
    try:
        if access_token:
            payload = decode_token(access_token, ACCESS, verify_exp=False)
            remaining = _remaining_seconds(payload)
            if remaining > 0:
                token_store.revoke(payload["jti"], remaining)
            revoked_any = True
        if refresh_token:
            payload = decode_token(refresh_token, REFRESH, verify_exp=False)
            token_store.invalidate_refresh(payload["jti"])
            revoked_any = True
    except TokenStoreUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token service unavailable") from exc

    if not revoked_any:
        raise _unauthorized()


def get_current_user_id(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    token: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> str:
    if not authorization and not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")

    resolved_token = token
    if authorization:
        scheme, _, bearer_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not bearer_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
        resolved_token = bearer_token

    return resolve_authenticated_user_id(resolved_token)
