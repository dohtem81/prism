import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose" / "docker-compose.yml"


def test_model_startup_gates_bot_without_blocking_worker():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    model = services["ollama-model"]
    assert model["depends_on"]["ollama"]["condition"] == "service_healthy"
    bot = services["demo-bot"]
    assert bot["environment"]["DEMO_LOCAL_MODEL"] == model["environment"]["DEMO_LOCAL_MODEL"]
    assert bot["depends_on"]["ollama-model"]["condition"] == "service_completed_successfully"
    assert "ollama-model" not in services["worker"]["depends_on"]


@pytest.mark.parametrize(
    ("installed", "pull_succeeds", "expected_calls", "expected_code"),
    [
        (True, True, ["show test:model"], 0),
        (False, True, ["show test:model", "pull test:model"], 0),
        (False, False, ["show test:model", "pull test:model"], 1),
    ],
)
def test_model_startup_installs_missing_model_and_surfaces_failure(
    tmp_path, installed, pull_succeeds, expected_calls, expected_code
):
    log = tmp_path / "ollama.log"
    ollama = tmp_path / "ollama"
    ollama.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$OLLAMA_TEST_LOG"
case "$1" in
    show) [ "$OLLAMA_TEST_INSTALLED" = yes ] ;;
    pull) [ "$OLLAMA_TEST_PULL_SUCCEEDS" = yes ] ;;
esac
""",
        encoding="utf-8",
    )
    ollama.chmod(0o755)
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    command = services["ollama-model"]["command"][0].replace("$$", "$")
    env = os.environ.copy()
    env.update(
        PATH=f"{tmp_path}:{env['PATH']}",
        DEMO_LOCAL_MODEL="test:model",
        OLLAMA_TEST_LOG=str(log),
        OLLAMA_TEST_INSTALLED="yes" if installed else "no",
        OLLAMA_TEST_PULL_SUCCEEDS="yes" if pull_succeeds else "no",
    )
    result = subprocess.run(["sh", "-c", command], env=env, capture_output=True, text=True)
    assert result.returncode == expected_code
    assert log.read_text(encoding="utf-8").splitlines() == expected_calls
