from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.worker.app.tasks.translation import (
    OpenAITranslationProvider,
    _cache_key,
    _estimate_cost_usd,
    build_translation_provider,
    run_translation_task,
    translate_message,
)


def test_cache_key_is_deterministic() -> None:
    key1 = _cache_key("hello", "en", "pl", "balanced")
    key2 = _cache_key("hello", "en", "pl", "balanced")
    key3 = _cache_key("hello", "en", "de", "balanced")

    assert key1 == key2
    assert key1 != key3
    assert key1.startswith("translation:cache:")


def test_estimate_cost_returns_none_for_missing_tokens() -> None:
    assert _estimate_cost_usd(None, 10) is None
    assert _estimate_cost_usd(10, None) is None


def test_estimate_cost_returns_value() -> None:
    assert _estimate_cost_usd(1000, 1000) == 0.001


def test_build_translation_provider_uses_configured_model() -> None:
    provider = build_translation_provider(provider_name="openai", model_name="gpt-4o-mini")

    assert isinstance(provider, OpenAITranslationProvider)
    assert provider.model == "gpt-4o-mini"


def test_build_translation_provider_rejects_unknown_provider() -> None:
    # Explicit empty fallback so this doesn't depend on TRANSLATION_FALLBACK_PROVIDER in the ambient env/.env.
    with pytest.raises(ValueError, match="Unsupported translation provider"):
        build_translation_provider(provider_name="unknown", fallback_provider_name="")


def test_run_translation_task_sends_failed_job_to_dead_letter_queue() -> None:
    with patch("services.worker.app.tasks.translation._run_translation_task", side_effect=TimeoutError("provider timeout")):
        with patch("services.worker.app.tasks.translation.celery_app.send_task") as send_task_mock:
            result = run_translation_task("msg_1", "room_1", "pl", "Czesc")

            assert result["status"] == "dead_letter"
            send_task_mock.assert_called_once_with(
                "services.worker.app.tasks.translation.dead_letter_translation",
                kwargs={
                    "message_id": "msg_1",
                    "room_id": "room_1",
                    "source_lang": "pl",
                    "content_original": "Czesc",
                    "error_type": "TimeoutError",
                    "error_message": "provider timeout",
                },
                queue="translation.failed.q",
            )


def test_build_translation_provider_uses_configured_fallback() -> None:
    provider = build_translation_provider(
        provider_name="unknown",
        model_name="gpt-4o-mini",
        fallback_provider_name="openai",
        fallback_model_name="gpt-4o-mini",
    )

    assert isinstance(provider, OpenAITranslationProvider)
    assert provider.model == "gpt-4o-mini"


@patch("services.worker.app.tasks.translation.SessionLocal")
def test_translate_message_returns_not_found_when_message_missing(session_local_mock: MagicMock) -> None:
    db = MagicMock()
    db.scalar.return_value = None

    session_local_mock.return_value.__enter__.return_value = db
    session_local_mock.return_value.__exit__.return_value = False

    result = run_translation_task("msg_1", "room_1", "pl", "Czesc")

    assert result["status"] == "not_found"


@patch("services.worker.app.tasks.translation.SessionLocal")
def test_translate_message_handles_no_target_languages(session_local_mock: MagicMock) -> None:
    message = MagicMock()
    message.created_at = datetime.now(timezone.utc)
    message.status = "original_only"
    message.version = 1

    room = MagicMock()
    room.default_translation_mode = "balanced"

    db = MagicMock()
    db.scalar.side_effect = [message, room]

    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    db.scalars.return_value = scalars_result

    session_local_mock.return_value.__enter__.return_value = db
    session_local_mock.return_value.__exit__.return_value = False

    result = run_translation_task("msg_1", "room_1", "pl", "Czesc")

    assert result["status"] == "no_target_languages"
    assert message.status == "translated"
    assert message.version == 2
    db.commit.assert_called_once()


@patch("services.worker.app.tasks.translation.manager.broadcast", new_callable=AsyncMock)
@patch("services.worker.app.tasks.translation.redis_client")
@patch("services.worker.app.tasks.translation.build_translation_provider")
@patch("services.worker.app.tasks.translation.SessionLocal")
def test_translate_message_uses_provider_and_broadcasts_update(
    session_local_mock: MagicMock,
    provider_factory_mock: MagicMock,
    redis_client_mock: MagicMock,
    broadcast_mock: AsyncMock,
) -> None:
    provider = MagicMock()
    provider.translate.return_value = ("Hallo", 12, 7)
    provider_factory_mock.return_value = provider
    redis_client_mock.get.return_value = None

    message = MagicMock()
    message.id = "msg_1"
    message.created_at = datetime.now(timezone.utc)
    message.status = "original_only"
    message.version = 1
    message.author_user_id = "user_1"
    message.source_lang = "pl"
    message.content_original = "Czesc"

    room = MagicMock()
    room.id = "room_1"
    room.default_translation_mode = "balanced"

    db = MagicMock()
    db.scalar.side_effect = [message, room, None, 1]

    member = MagicMock()
    member.preferred_lang = "de"
    members_result = MagicMock()
    members_result.all.return_value = [member]
    translations_result = MagicMock()
    translations_result.all.return_value = [
        MagicMock(
            target_lang="de",
            content="Hallo",
            provider="openai",
            quality_mode="balanced",
            translated_at=datetime.now(timezone.utc),
        )
    ]
    db.scalars.side_effect = [members_result, translations_result]

    session_local_mock.return_value.__enter__.return_value = db
    session_local_mock.return_value.__exit__.return_value = False

    result = translate_message("msg_1", "room_1", "pl", "Czesc")

    provider_factory_mock.assert_called_once()
    provider.translate.assert_called_once_with(
        content_original="Czesc",
        source_lang="pl",
        target_lang="de",
    )
    assert result["status"] == "translated"
    broadcast_mock.assert_awaited_once()
    broadcast_room_id, event = broadcast_mock.await_args.args
    assert broadcast_room_id == "room_1"
    assert event["type"] == "MessageUpdated"
    assert event["event_type"] == "MessageUpdated"
    assert event["event_version"] == 1
    assert event["event_id"].startswith("evt_")
    assert event["room_sequence"] == 2
    assert event["occurred_at"]
    assert event["message_id"] == "msg_1"
    assert event["translations"]["de"]["content"] == "Hallo"
