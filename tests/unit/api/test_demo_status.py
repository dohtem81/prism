from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.api.app.api.demo_status import ollama_status


@pytest.mark.parametrize(
    ("models", "expected"),
    [
        ([], "idle"),
        ([{"name": "other", "size": 100, "size_vram": 100}], "idle"),
        ([{"name": "test:1", "size": 100, "size_vram": 0}], "cpu"),
        ([{"name": "test:1", "size": 100, "size_vram": 100}], "gpu"),
        ([{"name": "test:1", "size": 100, "size_vram": 30}], "mixed"),
        ([{"name": "test:1", "size": 100, "size_vram": 101}], "unavailable"),
    ],
)
def test_ollama_reports_actual_loaded_processor(models, expected) -> None:
    response = MagicMock()
    response.json.return_value = {"models": models}
    with patch("services.api.app.api.demo_status.local_model", return_value="test:1"), \
         patch("services.api.app.api.demo_status.httpx.get", return_value=response):
        assert ollama_status().processor == expected


def test_ollama_status_handles_connection_failure() -> None:
    with patch("services.api.app.api.demo_status.httpx.get", side_effect=httpx.ConnectError("offline")):
        assert ollama_status().processor == "unavailable"
