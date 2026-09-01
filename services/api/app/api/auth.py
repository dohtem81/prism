from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import create_access_token
from services.api.app.infra.db import get_db
from shared.db.models import RegisteredAccount
from shared.schemas.auth import LoginRequest, LoginResponse
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

    return LoginResponse(access_token=create_access_token(account.id), user_id=account.id)
