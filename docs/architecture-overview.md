# Architecture Overview

## Design Goals

- Deliver original messages immediately — translation never blocks chat responsiveness.
- Perform translation server-side for consistent output and shared cost across all recipients.
- Support room-based conversations with per-room configurable translation quality.
- Persist the complete message timeline including all translation updates.
- Maintain chat functionality during provider outages through graceful degradation.

---

## High-Level Architecture

```mermaid
flowchart LR
  Client[Browser / API Client] -->|REST + WebSocket| API[FastAPI API]
  API --> PG[(PostgreSQL)]
  API --> MQ[(RabbitMQ)]
  MQ --> Worker[Celery Worker]
  Worker --> LLM[Translation Provider]
  Worker --> PG
  Worker -->|MessageUpdated event| API
  API -->|WebSocket push| Client
  Redis[(Redis)] -.-|cache| API
```

---

## Runtime Topology

| Container | Role |
|---|---|
| `api` | FastAPI REST endpoints, WebSocket gateway, browser dashboard |
| `worker` | Celery consumer for translation jobs |
| `postgres` | Durable store for rooms, members, messages, translations, and events |
| `rabbitmq` | Translation job queue with dead-letter support |
| `redis` | Translation result cache; multi-instance pub/sub fanout is not yet implemented |

---

## State Ownership

| Store | Role |
|---|---|
| **PostgreSQL** | Canonical source of truth for all rooms, memberships, messages, translations, and events |
| **Redis** | Auxiliary cache for translation results and short-lived operational keys — not the authoritative store for any domain entity |

---

## Core Pattern

Event-driven enrichment with a live room timeline:

1. Message is accepted and persisted as original content.
2. Original content is broadcast immediately to all room subscribers via WebSocket.
3. A translation job is queued for each target language derived from room member preferences.
4. Worker translates, persists results, and broadcasts a `MessageUpdated` event with the same `message_id`.
5. Clients patch the message in place — the timeline never resets.
6. Reconnect-safe history replay ensures clients that rejoin see recent messages.

---

## Degraded Mode

When the translation provider is unavailable:

- `MessageCreated` emission is never blocked — original delivery always goes through.
- The worker retries according to the retry policy, then marks the message `translation_unavailable`.
- A `MessageUpdated` event with that status is still broadcast so clients can surface it.
- Translation is best-effort enrichment on top of guaranteed original-message delivery.

---

## Delivery Semantics

| Concept | Behavior |
|---|---|
| Message identity | Stable `message_id` across the original broadcast and all translation updates |
| Versioning | Monotonically incrementing `version` on every server-side update |
| Realtime stream | Fan-out to all currently connected room subscribers |
| History replay | Room history endpoint with cursor-safe replay for reconnecting clients |

---

## Translation Quality Modes

Room admins can configure translation quality per room:

| Mode | Trade-off |
|---|---|
| `low_latency` | Faster, lighter model — prioritises speed |
| `balanced` | Default — good quality at reasonable latency |
| `high_quality` | Slower, more capable model — prioritises accuracy |

Mode influences the prompt profile, model selection, timeout, retry policy, and batching behavior.

---

## Analytics Model *(pending)*

The telemetry schema is in place. Aggregation jobs, API endpoints, and the dashboard are follow-on work.

Planned metrics:
- Translation cost by room and time window
- End-to-end translation delay percentiles
- Queue delay and worker processing time
- Translation success, failure, and retry rates
- Per-language-pair volume and cost breakdown
