from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import hashlib
import json
import time
from uuid import uuid4

from openai import OpenAI
import redis
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


class TranslationProvider:
    def translate(self, content_original: str, source_lang: str, target_lang: str) -> tuple[str, int | None, int | None]:
        raise NotImplementedError


class OpenAITranslationProvider(TranslationProvider):
    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.translation_model or settings.openai_translation_model
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self._client = OpenAI(api_key=settings.openai_api_key)

    def translate(self, content_original: str, source_lang: str, target_lang: str) -> tuple[str, int | None, int | None]:
        response = self._client.responses.create(
            model=self.model,
            input=(
                "Translate the message while preserving intent and tone. "
                f"Translate from {source_lang} to {target_lang}. "
                "Return only translated text with no explanations.\n\n"
                f"Message: {content_original}"
            ),
        )

        input_tokens = getattr(response.usage, "input_tokens", None) if response.usage else None
        output_tokens = getattr(response.usage, "output_tokens", None) if response.usage else None
        return response.output_text.strip(), input_tokens, output_tokens


_TRANSLATION_PROVIDERS: dict[str, type[TranslationProvider]] = {
    "openai": OpenAITranslationProvider,
}


def _resolve_provider_and_model(
    provider_name: str | None = None,
    model_name: str | None = None,
    fallback_provider_name: str | None = None,
    fallback_model_name: str | None = None,
) -> tuple[str, str]:
    selected_provider = (provider_name or settings.translation_provider or "openai").lower()
    selected_model = model_name or settings.translation_model or settings.openai_translation_model

    if selected_provider in _TRANSLATION_PROVIDERS:
        return selected_provider, selected_model

    fallback_provider = (fallback_provider_name or settings.translation_fallback_provider or "").lower()
    fallback_model = fallback_model_name or settings.translation_fallback_model or selected_model

    if fallback_provider in _TRANSLATION_PROVIDERS:
        return fallback_provider, fallback_model

    raise ValueError(f"Unsupported translation provider: {selected_provider}")


def build_translation_provider(
    provider_name: str | None = None,
    model_name: str | None = None,
    fallback_provider_name: str | None = None,
    fallback_model_name: str | None = None,
) -> TranslationProvider:
    selected_provider_name, selected_model_name = _resolve_provider_and_model(
        provider_name=provider_name,
        model_name=model_name,
        fallback_provider_name=fallback_provider_name,
        fallback_model_name=fallback_model_name,
    )

    provider_cls = _TRANSLATION_PROVIDERS[selected_provider_name]
    return provider_cls(model=selected_model_name)

from services.worker.app.celery_app import celery_app
from services.worker.app.infra.settings import settings
from shared.db.models import Message, MessageTranslation, OutboxEvent, Room, RoomEvent, RoomMember, TranslationTelemetry
from services.api.app.realtime.websocket_gateway import manager

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

redis_client = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)


def _cache_key(content_original: str, source_lang: str, target_lang: str, mode: str) -> str:
    payload = f"{content_original}|{source_lang}|{target_lang}|{mode}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"translation:cache:{digest}"


def _estimate_cost_usd(input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    # Placeholder estimate for initial telemetry wiring.
    return round(((input_tokens * 0.20) + (output_tokens * 0.80)) / 1_000_000, 6)


def _broadcast_room_event(room_id: str, payload: dict) -> None:
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(manager.broadcast(room_id, payload))
        return

    running_loop.create_task(manager.broadcast(room_id, payload))


def _send_to_dead_letter(
    message_id: str,
    room_id: str,
    source_lang: str,
    content_original: str,
    error: Exception,
) -> None:
    celery_app.send_task(
        "services.worker.app.tasks.translation.dead_letter_translation",
        kwargs={
            "message_id": message_id,
            "room_id": room_id,
            "source_lang": source_lang,
            "content_original": content_original,
            "error_type": type(error).__name__,
            "error_message": str(error),
        },
        queue="translation.failed.q",
    )


def run_translation_task(message_id: str, room_id: str, source_lang: str, content_original: str) -> dict[str, str]:
    try:
        return _run_translation_task(message_id, room_id, source_lang, content_original)
    except Exception as exc:
        _send_to_dead_letter(message_id, room_id, source_lang, content_original, exc)
        return {
            "message_id": message_id,
            "room_id": room_id,
            "status": "dead_letter",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _run_translation_task(message_id: str, room_id: str, source_lang: str, content_original: str) -> dict[str, str]:
    with SessionLocal() as db:
        message = db.scalar(select(Message).where(Message.id == message_id))
        room = db.scalar(select(Room).where(Room.id == room_id))
        if not message or not room:
            return {"message_id": message_id, "status": "not_found"}

        members = db.scalars(select(RoomMember).where(RoomMember.room_id == room_id)).all()
        target_langs = sorted({m.preferred_lang for m in members if m.preferred_lang != source_lang})

        if not target_langs:
            message.status = "translated"
            message.version += 1
            db.commit()
            return {"message_id": message_id, "status": "no_target_languages"}

        translations_patch: dict[str, dict[str, str]] = {}
        success_count = 0
        failure_count = 0
        started_at = datetime.now(timezone.utc)

        for target_lang in target_langs:
            existing = db.scalar(
                select(MessageTranslation).where(
                    MessageTranslation.message_id == message_id,
                    MessageTranslation.target_lang == target_lang,
                )
            )
            if existing:
                continue

            queue_delay_ms = int((started_at - message.created_at).total_seconds() * 1000)
            provider_start = time.perf_counter()
            translated_text: str | None = None
            input_tokens: int | None = None
            output_tokens: int | None = None
            status = "success"

            key = _cache_key(content_original, source_lang, target_lang, room.default_translation_mode)
            cached = redis_client.get(key)

            try:
                if cached:
                    translated_text = cached
                    provider_latency_ms = 0
                else:
                    provider = build_translation_provider()
                    translated_text, input_tokens, output_tokens = provider.translate(
                        content_original=content_original,
                        source_lang=source_lang,
                        target_lang=target_lang,
                    )
                    redis_client.setex(key, 3600, translated_text)
                    provider_latency_ms = int((time.perf_counter() - provider_start) * 1000)
            except Exception:
                status = "failed"
                provider_latency_ms = int((time.perf_counter() - provider_start) * 1000)

            end_to_end_delay_ms = int((datetime.now(timezone.utc) - message.created_at).total_seconds() * 1000)
            telemetry = TranslationTelemetry(
                room_id=room_id,
                message_id=message_id,
                target_lang=target_lang,
                provider="openai",
                status=status,
                attempt=1,
                queue_delay_ms=queue_delay_ms,
                provider_latency_ms=provider_latency_ms,
                end_to_end_delay_ms=end_to_end_delay_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=_estimate_cost_usd(input_tokens, output_tokens),
                occurred_at=datetime.now(timezone.utc),
            )
            db.add(telemetry)

            if status == "success" and translated_text:
                translation = MessageTranslation(
                    message_id=message_id,
                    target_lang=target_lang,
                    content=translated_text,
                    provider="openai",
                    quality_mode=room.default_translation_mode,
                    translated_at=datetime.now(timezone.utc),
                )
                db.add(translation)
                translations_patch[target_lang] = {
                    "content": translated_text,
                    "provider": "openai",
                    "quality_mode": room.default_translation_mode,
                    "translated_at": datetime.now(timezone.utc).isoformat(),
                }
                success_count += 1
            else:
                failure_count += 1

        if success_count == len(target_langs):
            message.status = "translated"
        elif success_count > 0:
            message.status = "partially_translated"
        else:
            message.status = "translation_unavailable"

        message.version += 1

        room_sequence = (db.scalar(select(func.max(RoomEvent.room_sequence)).where(RoomEvent.room_id == room_id)) or 0) + 1
        event_payload = {
            "type": "MessageUpdated",
            "room_id": room_id,
            "message_id": message.id,
            "version": message.version,
            "original_message": {
                "message_id": message.id,
                "version": message.version,
                "author_user_id": message.author_user_id,
                "source_lang": message.source_lang,
                "content_original": message.content_original,
                "status": message.status,
                "created_at": message.created_at.isoformat() if message.created_at else None,
            },
            "translations": {
                target_lang: {
                    "content": translation.content,
                    "provider": translation.provider,
                    "quality_mode": translation.quality_mode,
                    "translated_at": translation.translated_at.isoformat() if translation.translated_at else None,
                }
                for target_lang, translation in {
                    t.target_lang: t for t in db.scalars(
                        select(MessageTranslation).where(MessageTranslation.message_id == message_id)
                    ).all()
                }.items()
            },
            "translations_patch": translations_patch,
            "status": message.status,
        }

        room_event = RoomEvent(
            room_id=room_id,
            room_sequence=room_sequence,
            event_id=f"evt_{uuid4().hex[:24]}",
            event_type="MessageUpdated",
            payload=event_payload,
            occurred_at=datetime.now(timezone.utc),
        )
        outbox_event = OutboxEvent(
            aggregate_type="message",
            aggregate_id=message.id,
            event_type="MessageUpdated",
            payload=event_payload,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )

        db.add(room_event)
        db.add(outbox_event)
        db.commit()

        _broadcast_room_event(room_id, event_payload)

        return {
            "message_id": message_id,
            "room_id": room_id,
            "status": message.status,
            "successful_translations": str(success_count),
            "failed_translations": str(failure_count),
            "translations_patch": json.dumps(translations_patch),
        }


@celery_app.task(
    bind=True,
    autoretry_for=(TimeoutError, ConnectionError, OSError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 5},
    name="services.worker.app.tasks.translation.translate_message",
)
def translate_message(self, message_id: str, room_id: str, source_lang: str, content_original: str) -> dict[str, str]:
    return run_translation_task(message_id, room_id, source_lang, content_original)


@celery_app.task(name="services.worker.app.tasks.translation.dead_letter_translation")
def dead_letter_translation(
    message_id: str,
    room_id: str,
    source_lang: str,
    content_original: str,
    error_type: str,
    error_message: str,
) -> dict[str, str]:
    return {
        "message_id": message_id,
        "room_id": room_id,
        "status": "dead_letter",
        "source_lang": source_lang,
        "content_original": content_original,
        "error_type": error_type,
        "error_message": error_message,
    }
