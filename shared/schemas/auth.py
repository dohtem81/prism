from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=4096)
