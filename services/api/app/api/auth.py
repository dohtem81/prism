from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    is_allowed_origin,
    issue_token_pair,
    revoke_session_tokens,
    rotate_refresh_token,
)
from services.api.app.infra.db import get_db
from services.api.app.infra.settings import settings
from shared.db.models import RegisteredAccount
from shared.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenPairResponse,
)
from shared.security import hash_password, verify_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        **common,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    account = db.scalar(
        select(RegisteredAccount).where(
            (RegisteredAccount.email == payload.username_or_email)
            | (RegisteredAccount.username == payload.username_or_email)
        )
    )
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if account.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Password change required before login",
        )

    access_token, refresh_token = issue_token_pair(account.id)
    _set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(user_id=account.id)


@router.post("/password/change", response_model=LoginResponse)
def change_password(payload: PasswordChangeRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    account = db.scalar(
        select(RegisteredAccount).where(
            (RegisteredAccount.email == payload.username_or_email)
            | (RegisteredAccount.username == payload.username_or_email)
        )
    )
    if account is None or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not account.must_change_password:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Password change is not required")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a different password")

    account.password_hash = hash_password(payload.new_password)
    account.must_change_password = False
    db.commit()

    access_token, refresh_token = issue_token_pair(account.id)
    _set_auth_cookies(response, access_token, refresh_token)
    return LoginResponse(user_id=account.id)


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> LoginResponse | TokenPairResponse:
    """Exchange a refresh token (JSON body) for a new access + refresh pair; the old refresh token becomes invalid."""
    is_browser = refresh_cookie is not None
    refresh_token_input = refresh_cookie or (payload.refresh_token if payload else None)
    if not refresh_token_input:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    if is_browser and not is_allowed_origin(request.headers.get("origin")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")
    access_token, refresh_token, user_id = rotate_refresh_token(refresh_token_input)
    if is_browser:
        _set_auth_cookies(response, access_token, refresh_token)
        return LoginResponse(user_id=user_id)
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token, user_id=user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    access_cookie: Annotated[str | None, Cookie(alias=ACCESS_COOKIE_NAME)] = None,
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> Response:
    """Revoke browser cookies or API bearer/body tokens and clear browser cookies."""
    access_token = access_cookie if not authorization else None
    if authorization:
        scheme, _, bearer_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not bearer_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
        access_token = bearer_token

    if not authorization and (access_cookie or refresh_cookie) and not is_allowed_origin(request.headers.get("origin")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin")
    refresh_token = refresh_cookie if not authorization else None
    if payload and payload.refresh_token:
        refresh_token = payload.refresh_token
    revoke_session_tokens(access_token, refresh_token)
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
