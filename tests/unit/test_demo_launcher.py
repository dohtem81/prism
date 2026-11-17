import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "start-demo.sh"


@pytest.mark.parametrize(
    ("gpu", "override", "expected_model"),
    [
        (True, "", "qwen2.5:7b"),
        (False, "", "qwen2.5:1.5b"),
        (False, "custom:latest", "custom:latest"),
    ],
)
def test_launcher_selects_backend_and_model(tmp_path, gpu, override, expected_model):
    log = tmp_path / "docker.log"
    docker = tmp_path / "docker"
    docker.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$DOCKER_TEST_LOG"
case "$1 $2" in
    "run --rm") [ "$DOCKER_TEST_GPU" = yes ] || { echo "GPU unavailable" >&2; exit 1; } ;;
    "compose --env-file")
        case " $* " in
            *" config --environment "*) [ -z "$DOCKER_TEST_OVERRIDE" ] || printf 'DEMO_LOCAL_MODEL=%s\\n' "$DOCKER_TEST_OVERRIDE" ;;
        esac ;;
esac
""",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=f"{tmp_path}:{env['PATH']}",
        DOCKER_TEST_LOG=str(log),
        DOCKER_TEST_GPU="yes" if gpu else "no",
        DOCKER_TEST_OVERRIDE=override,
    )
    env.pop("DEMO_LOCAL_MODEL", None)
    result = subprocess.run(["sh", str(LAUNCHER)], env=env, capture_output=True, text=True, check=True)
    calls = log.read_text(encoding="utf-8").splitlines()
    compose_calls = [call for call in calls if call.startswith("compose ")]
    assert compose_calls
    assert all(("docker-compose.gpu.yml" in call) == gpu for call in compose_calls)
    assert any("alembic -c migrations/alembic.ini upgrade head" in call for call in compose_calls)
    assert any(call.endswith("up --build -d") for call in compose_calls)
    assert f"will use {expected_model}" in result.stdout


def test_launcher_stops_if_docker_is_unavailable(tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    result = subprocess.run(["sh", str(LAUNCHER)], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Docker is unavailable" in result.stderr
