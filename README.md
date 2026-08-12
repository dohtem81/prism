# Prism

Phase 1 scaffold for a real-time chat platform with server-side translation.

## Stack

- Python 3.12
- FastAPI (API + WebSocket)
- Celery worker
- RabbitMQ
- Redis
- PostgreSQL
- Alembic migrations

## Scripts

Use these command aliases as the standard Docker-first workflow.

| Script | Command |
|---|---|
| `script:up` | `docker compose -f deploy/compose/docker-compose.yml up --build` |
| `script:up:detached` | `docker compose -f deploy/compose/docker-compose.yml up --build -d` |
| `script:down` | `docker compose -f deploy/compose/docker-compose.yml down` |
| `script:down:volumes` | `docker compose -f deploy/compose/docker-compose.yml down -v` |
| `script:migrate` | `docker compose -f deploy/compose/docker-compose.yml run --rm api alembic -c migrations/alembic.ini upgrade head` |
| `script:test` | `docker compose -f deploy/compose/docker-compose.yml run --rm tests` |
| `script:logs:api` | `docker compose -f deploy/compose/docker-compose.yml logs -f api` |
| `script:logs:worker` | `docker compose -f deploy/compose/docker-compose.yml logs -f worker` |

## Quick Start

If port 8000 is already in use, set API_PORT in .env to a free host port (example: 8010).

1. Copy env file:

```bash
cp .env.example .env
```

2. Start infrastructure and services:

```bash
docker compose -f deploy/compose/docker-compose.yml up --build
```

3. Configure translation provider/model in `.env`:

```env
TRANSLATION_PROVIDER=openai
TRANSLATION_MODEL=gpt-4.1-mini
TRANSLATION_FALLBACK_PROVIDER=openai
TRANSLATION_FALLBACK_MODEL=gpt-4.1-mini
OPENAI_API_KEY=replace_me
```

The worker resolves the concrete translation backend from configuration, so the model can be swapped without changing the task flow or message contract.

4. Run migrations using Docker (from another shell):

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm api alembic -c migrations/alembic.ini upgrade head
```

4. Run unit tests using Docker:

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm tests
```

5. Optional local tooling path (if needed):

```bash
pip install -r requirements.txt
alembic -c migrations/alembic.ini upgrade head
```

6. For future schema changes:

```bash
alembic -c migrations/alembic.ini revision --autogenerate -m "describe_change"
alembic -c migrations/alembic.ini upgrade head
```

7. Verify API:

```bash
curl http://localhost:8000/v1/health
```

## Current implementation status

The current codebase is verified for the live room flow and reconnect-safe message replay:

- room creation and membership management APIs
- user profile creation and language preference persistence
- original message persistence and room fan-out
- WebSocket room subscription and live message delivery for connected clients
- room message history fetch with reconnect-safe replay semantics
- Celery translation queueing and worker-side updates
- MessageUpdated broadcast with translation patches and room status changes
- browser dashboard at /ui and /ui/rooms/{room_id}
- provider abstraction with config-driven model selection and fallback behavior
- transient retry and dead-letter handling for worker failures

Still pending or follow-on work:

- admin analytics endpoints and aggregated room metrics dashboards
- Redis pub/sub fanout across multiple API replicas
- structured logging and correlation IDs across API and worker
- input validation and payload hardening for production use

## Web dashboard

A lightweight browser dashboard is available through the FastAPI app at:

- /ui
- /ui/rooms/{room_id}

This is intended for local verification and manual QA of room membership, send flow, live message updates, and reconnect-safe recent-message replay.

## Run Unit Tests

Local:

```bash
pip install -r requirements.txt
pytest -q tests/unit
```

Docker:

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm tests
```
