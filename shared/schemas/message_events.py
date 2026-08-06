from datetime import datetime

from pydantic import BaseModel, Field


class SendMessage(BaseModel):
    author_user_id: str = Field(min_length=1, max_length=64)
    room_id: str
    client_message_id: str
    source_lang: str
    content_original: str


class SendMessageResponse(BaseModel):
    message_id: str
    room_id: str
    status: str
    version: int
    translation_job_enqueued: bool
    created_at: datetime
