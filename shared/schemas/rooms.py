from datetime import datetime

from pydantic import BaseModel, Field


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    preferred_lang: str = Field(default="en", min_length=2, max_length=8)


class CreateRoomResponse(BaseModel):
    room_id: str
    name: str
    role: str
    preferred_lang: str
    default_translation_mode: str
    created_at: datetime


class JoinRoomRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    preferred_lang: str = Field(min_length=2, max_length=8)


class JoinRoomSelfRequest(BaseModel):
    preferred_lang: str = Field(min_length=2, max_length=8)


class RoomSummary(BaseModel):
    room_id: str
    name: str
    role: str
    preferred_lang: str
    default_translation_mode: str
    created_at: datetime


class RoomMembershipResponse(BaseModel):
    room_id: str
    user_id: str
    role: str
    preferred_lang: str
    created_at: datetime


class RoomMessageTranslation(BaseModel):
    content: str
    provider: str
    quality_mode: str | None = None
    translated_at: datetime | None = None


class RoomMessageResponse(BaseModel):
    message_id: str
    version: int
    author_user_id: str
    source_lang: str
    content_original: str
    status: str
    created_at: datetime
    translations: dict[str, RoomMessageTranslation] = {}
