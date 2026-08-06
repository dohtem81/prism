from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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
