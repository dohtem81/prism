from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import (
    create_access_token,
    create_refresh_token,
    revoke_session_tokens,
    rotate_refresh_token,
)
from services.api.app.infra.db import get_db
from shared.db.models import RegisteredAccount
from shared.schemas.auth import LoginRequest, LoginResponse, LogoutRequest, RefreshRequest, TokenPairResponse
from shared.security import verify_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    account = db.scalar(
        select(RegisteredAccount).where(
            (RegisteredAccount.email == payload.username_or_email)
            | (RegisteredAccount.username == payload.username_or_email)
        )
    )
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return LoginResponse(
        access_token=create_access_token(account.id),
        refresh_token=create_refresh_token(account.id),
        user_id=account.id,
    )


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(payload: RefreshRequest) -> TokenPairResponse:
    """Exchange a refresh token (JSON body) for a new access + refresh pair; the old refresh token becomes invalid."""
    access_token, refresh_token, user_id = rotate_refresh_token(payload.refresh_token)
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token, user_id=user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest | None = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Response:
    """Revoke the access token in the Authorization header and, if given, the refresh token in the body."""
    access_token = None
    if authorization:
        scheme, _, bearer_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not bearer_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
        access_token = bearer_token

    revoke_session_tokens(access_token, payload.refresh_token if payload else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
