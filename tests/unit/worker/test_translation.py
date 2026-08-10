from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.worker.app.tasks.translation import _cache_key, _estimate_cost_usd, translate_message


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


@patch("services.worker.app.tasks.translation.SessionLocal")
def test_translate_message_returns_not_found_when_message_missing(session_local_mock: MagicMock) -> None:
    db = MagicMock()
    db.scalar.return_value = None

    session_local_mock.return_value.__enter__.return_value = db
    session_local_mock.return_value.__exit__.return_value = False

    result = translate_message("msg_1", "room_1", "pl", "Czesc")

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

    result = translate_message("msg_1", "room_1", "pl", "Czesc")

    assert result["status"] == "no_target_languages"
    assert message.status == "translated"
    assert message.version == 2
    db.commit.assert_called_once()


@patch("services.worker.app.tasks.translation.manager.broadcast", new_callable=AsyncMock)
@patch("services.worker.app.tasks.translation.build_translation_provider")
@patch("services.worker.app.tasks.translation.SessionLocal")
def test_translate_message_uses_provider_and_broadcasts_update(
    session_local_mock: MagicMock,
    provider_factory_mock: MagicMock,
    broadcast_mock: AsyncMock,
) -> None:
    provider = MagicMock()
    provider.translate.return_value = ("Hallo", 12, 7)
    provider_factory_mock.return_value = provider

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
    db.scalar.side_effect = [message, room]

    member = MagicMock()
    member.preferred_lang = "de"
    scalars_result = MagicMock()
    scalars_result.all.return_value = [member]
    db.scalars.return_value = scalars_result

    session_local_mock.return_value.__enter__.return_value = db
    session_local_mock.return_value.__exit__.return_value = False

    result = translate_message("msg_1", "room_1", "pl", "Czesc")

    provider_factory_mock.assert_called_once()
    provider.translate.assert_called_once_with("Czesc", "pl", "de")
    assert result["status"] == "translated"
    broadcast_mock.assert_awaited_once()
