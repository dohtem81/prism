from datetime import datetime

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    preferred_lang: str | None = Field(default=None, min_length=2, max_length=8)


class CreateUserResponse(BaseModel):
    user_id: str
    display_name: str | None
    preferred_lang: str | None
    created_at: datetime
