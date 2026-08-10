from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_translation_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="balanced")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_room_members_room_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(64), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    preferred_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("room_id", "author_user_id", "client_message_id", name="uq_messages_room_author_client"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    author_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    content_original: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="original_only")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class MessageTranslation(Base):
    __tablename__ = "message_translations"
    __table_args__ = (UniqueConstraint("message_id", "target_lang", name="uq_message_translations_msg_lang"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    translated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RoomEvent(Base):
    __tablename__ = "room_events"
    __table_args__ = (
        UniqueConstraint("room_id", "room_sequence", name="uq_room_events_room_sequence"),
        UniqueConstraint("event_id", name="uq_room_events_event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(64), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    room_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TranslationTelemetry(Base):
    __tablename__ = "translation_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(64), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    queue_delay_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_to_end_delay_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RoomMetricsHourly(Base):
    __tablename__ = "room_metrics_hourly"
    __table_args__ = (UniqueConstraint("room_id", "bucket_start", name="uq_room_metrics_room_bucket"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(64), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_translations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(14, 6), nullable=False, default=0)
    queue_delay_p50_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queue_delay_p95_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_latency_p50_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_latency_p95_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_to_end_p50_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_to_end_p95_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
