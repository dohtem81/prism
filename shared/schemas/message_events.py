from datetime import datetime

from pydantic import BaseModel, Field


MESSAGE_CONTENT_MAX_LENGTH = 4000


class SendMessage(BaseModel):
    author_user_id: str = Field(min_length=1, max_length=64)
    room_id: str = Field(min_length=1, max_length=64)
    client_message_id: str = Field(min_length=1, max_length=128)
    source_lang: str = Field(min_length=2, max_length=2, pattern=r"^[a-z]{2}$")
    content_original: str = Field(min_length=1, max_length=MESSAGE_CONTENT_MAX_LENGTH)


class SendMessageResponse(BaseModel):
    message_id: str
    room_id: str
    status: str
    version: int
    translation_job_enqueued: bool
    created_at: datetime
