from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.db import get_db
from shared.db.models import User
from shared.schemas.users import CreateUserRequest, CreateUserResponse

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.post("", response_model=CreateUserResponse)
def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> CreateUserResponse:
    user = db.scalar(select(User).where(User.id == current_user_id))
    if user is None:
        user = User(
            id=current_user_id,
            display_name=payload.display_name,
            preferred_lang=payload.preferred_lang,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if payload.display_name is not None:
            user.display_name = payload.display_name
        if payload.preferred_lang is not None:
            user.preferred_lang = payload.preferred_lang
        db.commit()
        db.refresh(user)

    return CreateUserResponse(
        user_id=user.id,
        display_name=user.display_name,
        preferred_lang=user.preferred_lang,
        created_at=user.created_at,
    )
