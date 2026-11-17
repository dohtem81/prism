from pydantic import BaseModel, Field, field_validator


class DemoRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    preferred_lang: str = Field(default="en", pattern=r"^[a-z]{2}$")

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_display_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class LoginRequest(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class PasswordChangeRequest(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=255)
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class LoginResponse(BaseModel):
    user_id: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class ResendVerificationRequest(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=255)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=4096)
