# Prism

Prism is a real-time chat platform where messages are automatically translated server-side so every participant reads the conversation in their own language — without any delay to the sender.

When a message is sent, it is delivered immediately to all connected clients. Translation runs asynchronously in the background and is pushed to every client as a live update the moment it completes. If the translation provider is unavailable, the message stays readable in the original language and the status is surfaced to the UI — the chat never blocks.

![Prism demo](docs/imgs/prim_demo.gif)

> When the LLM provider is unavailable, the message is still delivered in the original language and the translation status is shown.
>
> ![Translation unavailable state](docs/imgs/prims_llm_not%20avaliable.gif)

---

## How it works

```
Browser / API Client
        │
        │  REST + WebSocket
        ▼
   FastAPI API  ──── PostgreSQL (messages, rooms, users)
        │
        │  publishes translation job
        ▼
    RabbitMQ
        │
        ▼
  Celery Worker  ──── Translation Provider (OpenAI / OpenRouter)
        │
        │  writes translation, emits MessageUpdated event
        ▼
   FastAPI API  ──── WebSocket push to all room subscribers
```

The API and worker are decoupled — the worker only writes to Postgres and fires an update event back through the API gateway. Translation quality and the model used are config-driven and can be swapped without touching application logic.

---

## Stack

| Layer | Technology |
|---|---|
| API + WebSocket | FastAPI (Python 3.12) |
| Task queue | Celery + RabbitMQ |
| Session / pub-sub | Redis |
| Database | PostgreSQL + Alembic |
| Containerisation | Docker Compose |

---

## Quick start

> Secrets stay local. The repo tracks only `.env.example` — copy it to `.env` and never commit the result.

**1. Create your local env file**

```bash
cp .env.example .env
```

**2. Set your translation provider in `.env`**

```env
TRANSLATION_PROVIDER=openai
TRANSLATION_MODEL=gpt-4.1-mini
TRANSLATION_FALLBACK_PROVIDER=openai
TRANSLATION_FALLBACK_MODEL=gpt-4.1-mini
OPENAI_API_KEY=your_key_here
```

> If port 8000 is already in use, set `API_PORT` in `.env` to a free port (e.g. `8010`).

**3. Start all services**

```bash
docker compose -f deploy/compose/docker-compose.yml up --build
```

**4. Run database migrations** (in a separate shell)

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm api alembic -c migrations/alembic.ini upgrade head
```

**5. Open the dashboard**

Navigate to `http://localhost:8000/ui` — create rooms, add users, send messages, and watch translations arrive live.

**6. Verify the API**

```bash
curl http://localhost:8000/v1/health
```

---

## Docker command reference

| What | Command |
|---|---|
| Start (foreground) | `docker compose -f deploy/compose/docker-compose.yml up --build` |
| Start (detached) | `docker compose -f deploy/compose/docker-compose.yml up --build -d` |
| Stop | `docker compose -f deploy/compose/docker-compose.yml down` |
| Stop + wipe volumes | `docker compose -f deploy/compose/docker-compose.yml down -v` |
| Run migrations | `docker compose -f deploy/compose/docker-compose.yml run --rm api alembic -c migrations/alembic.ini upgrade head` |
| Run tests | `docker compose -f deploy/compose/docker-compose.yml run --rm tests` |
| API logs | `docker compose -f deploy/compose/docker-compose.yml logs -f api` |
| Worker logs | `docker compose -f deploy/compose/docker-compose.yml logs -f worker` |

**Creating a new migration after schema changes:**

```bash
docker compose -f deploy/compose/docker-compose.yml run --rm api \
  alembic -c migrations/alembic.ini revision --autogenerate -m "describe_change"
docker compose -f deploy/compose/docker-compose.yml run --rm api \
  alembic -c migrations/alembic.ini upgrade head
```

---

## Running tests

```bash
# Docker (recommended)
docker compose -f deploy/compose/docker-compose.yml run --rm tests

# Local
pip install -r requirements.txt
pytest -q tests/unit
```

---

## Project status

**Working now:**
- Room creation and membership management
- User profiles with per-user language preferences
- Message send, persistence, and WebSocket fan-out to all room subscribers
- Async translation via configurable LLM provider with live `MessageUpdated` push
- Graceful degradation — provider failures mark the message `translation_unavailable` and push a status update without breaking chat
- Reconnect-safe room history replay
- Docker-first local dev with Postgres, RabbitMQ, Redis, API, and worker

**Planned:**
- Redis pub/sub fan-out across multiple API replicas
- Admin analytics and room metrics dashboards
- Structured observability and correlation IDs
- Production hardening (payload validation, quotas, rate limiting)



