#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

if ! docker info >/dev/null; then
    echo "Docker is unavailable; start Docker and try again." >&2
    exit 1
fi

if ! docker image inspect ollama/ollama:latest >/dev/null 2>&1; then
    docker compose --env-file "$root/.env" -f "$root/deploy/compose/docker-compose.yml" pull ollama
fi

gpu=false
if probe=$(docker run --rm --gpus all --entrypoint nvidia-smi ollama/ollama:latest 2>&1); then
    gpu=true
    DEMO_DEFAULT_LOCAL_MODEL=qwen2.5:7b
    echo "Docker-accessible NVIDIA GPU detected."
else
    DEMO_DEFAULT_LOCAL_MODEL=qwen2.5:1.5b
    echo "No Docker-accessible NVIDIA GPU detected; using CPU. GPU probe: $probe" >&2
fi
export DEMO_DEFAULT_LOCAL_MODEL

compose() {
    if [ "$gpu" = true ]; then
        docker compose --env-file "$root/.env" -f "$root/deploy/compose/docker-compose.yml" \
            -f "$root/deploy/compose/docker-compose.gpu.yml" "$@"
    else
        docker compose --env-file "$root/.env" -f "$root/deploy/compose/docker-compose.yml" "$@"
    fi
}

compose config -q
model=$(compose config --environment | sed -n 's/^DEMO_LOCAL_MODEL=//p')
model=${model:-$DEMO_DEFAULT_LOCAL_MODEL}
echo "Demo bot will use $model. Compose will install it if needed."

compose run --build --rm api alembic -c migrations/alembic.ini upgrade head
compose up --build -d
