from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterAccountRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    # bcrypt silently ignores/rejects bytes beyond 72, so cap input length here.
    password: str = Field(min_length=8, max_length=72)


class RegisterAccountResponse(BaseModel):
    user_id: str
    email: EmailStr
    username: str
    created_at: datetime


class RegisterAccountError(BaseModel):
    error: str
    detail: str
    redirect_url: str
