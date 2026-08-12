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

Important: local secrets and environment values must stay out of Git. The repository tracks only `.env.example`, and a real `.env` file is created locally from that template and never committed.

If port 8000 is already in use, set API_PORT in `.env` to a free host port (example: 8010).

1. Copy the example env file locally:

```bash
cp .env.example .env
```

2. Fill in any required secrets, such as OpenRouter or OpenAI keys, in the local `.env` file.

3. Start infrastructure and services:

```bash
docker compose -f deploy/compose/docker-compose.yml up --build
```

4. Configure the translation provider/model in your local `.env`:

```env
TRANSLATION_PROVIDER=openai
TRANSLATION_MODEL=gpt-4.1-mini
TRANSLATION_FALLBACK_PROVIDER=openai
TRANSLATION_FALLBACK_MODEL=gpt-4.1-mini
OPENAI_API_KEY=replace_me
```

The worker resolves the concrete translation backend from configuration, so the model can be swapped without changing the task flow or message contract.

Do not commit `.env`. Keep secrets only in the local file and rotate them if they were ever exposed in the repository history.

5. Run migrations using Docker (from another shell):

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm api alembic -c migrations/alembic.ini upgrade head
```

6. Run unit tests using Docker:

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm tests
```

7. Optional local tooling path (if needed):

```bash
pip install -r requirements.txt
alembic -c migrations/alembic.ini upgrade head
```

8. For future schema changes:

```bash
alembic -c migrations/alembic.ini revision --autogenerate -m "describe_change"
alembic -c migrations/alembic.ini upgrade head
```

9. Verify API:

```bash
curl http://localhost:8000/v1/health
```

## Current implementation status

The project is currently verified for the core live-chat and translation workflow in Docker-based local development:

Completed and verified:

- room creation and membership management APIs
- user profile creation and language preference persistence
- message persistence, replay, and original-message fan-out
- WebSocket room subscriptions and live message delivery for connected clients
- recent-message replay and reconnect-safe room history fetches
- Celery worker translation queueing and async message enrichment
- MessageUpdated broadcasts with translation patches and status changes
- browser dashboard at /ui and /ui/rooms/{room_id}
- provider abstraction with config-driven model selection and fallback behavior
- transient retry, dead-letter, and update event handling for worker failures
- Docker-first local dev workflow with Postgres, RabbitMQ, Redis, API, and worker services

Current operational reality:

- translation succeeds when the configured external provider is available
- OpenRouter-compatible providers may return 429 rate-limit responses under load
- the worker handles those failures gracefully by marking the message as translation_unavailable and emitting an update state

Still pending or follow-on work:

- admin analytics and room metrics dashboards
- Redis pub/sub fanout across multiple API replicas
- structured observability, correlation IDs, and better traceability across API and worker
- production hardening for payload validation, quotas, and operational safeguards
- richer multi-room and multi-user lifecycle management for larger deployment scenarios

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
