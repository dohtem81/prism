# Technology Decisions and Trade-offs

## Core Stack

- Python 3.12+
- FastAPI (REST + WebSocket)
- PostgreSQL 16
- RabbitMQ 3.13+
- Background workers (Celery recommended)
- Redis 7 (cache, presence, pub-sub fanout, rate limiting)
- OpenAI API for translation
- Docker and Docker Compose

## Why This Stack

### FastAPI
Pros:

- Strong async support and performance.
- Type hints and OpenAPI generation for REST endpoints.
- Good ecosystem for WebSocket and dependency injection.

Cons:

- Requires disciplined architecture to avoid monolithic app growth.

### PostgreSQL
Pros:

- Durable, relational, and query-friendly message history.
- Strong transactional behavior for outbox pattern.

Cons:

- Needs indexing and partition strategy at higher scale.

Decision: split user identity into two linked tables, not one.

- `public.users` (room/message identity: `display_name`, `preferred_lang`) and `auth.accounts`
  (registration credentials: `email`, `username`, `password_hash`, isolated in the `auth` schema)
  are separate tables, joined 1:1 via `auth.accounts.id` as a foreign key to `users.id`.
- Why not a single merged table:
  - Credentials stay isolated in a schema that can be locked down independently from chat data.
  - Users register once but send many messages — `auth.accounts` stays small and low-traffic,
    while `users`/`messages` are written and read constantly. Keeping them separate avoids
    bloating or contending with the hot chat tables and keeps the accounts table cheap to
    back up, audit, or migrate independently.
  - `users.id` remains the single stable identity referenced by rooms/messages regardless of
    how auth storage evolves later (e.g. moving to a dedicated auth database or service).

### Password Hashing

Decision:

- Hash passwords with `bcrypt` directly (not `passlib`, which has known compatibility issues
  with modern bcrypt releases).
- Cap password input to 72 bytes, bcrypt's hashing limit.

### Redis
Pros:

- Very low latency for hot-room cache and user presence.
- Can reduce PostgreSQL read load for frequently accessed room metadata.
- Useful for multi-instance WebSocket pub/sub fanout.

Cons:

- Extra operational component with memory tuning and eviction policy risks.
- Adds consistency complexity if treated as primary storage.

Decision:

- Do not store canonical room state only in Redis.
- Keep PostgreSQL as source of truth for rooms and memberships.
- Use Redis as a read-through cache and ephemeral presence store.
- Use Redis from day one for cache, presence, and operational controls.

Primary Redis use cases in this system:

- Presence and heartbeat tracking.
- Hot-room metadata and membership cache.
- Multi-instance WebSocket fanout.
- Translation result cache by source/target language pair.
- Rate limiting and abuse control counters.
- Short-lived dedup keys for request and event replay protection.

### Worker Queue
Decision:

- Use RabbitMQ as the translation job queue.

Why RabbitMQ:

- Mature delivery semantics, ack/nack, dead-letter queues, and retry topology.
- Clear routing model for translation jobs.
- Better fit than Redis pub/sub for durable asynchronous processing.

Suggested baseline:

- Exchange: topic (chat.translation)
- Routing key: translation.requested
- Queue: translation.requested.q
- Dead-letter queue: translation.requested.dlq

### OpenAI Translation
Pros:

- High quality and quick integration.
- Prompt control allows mode-specific behavior.

Cons:

- Ongoing cost and external dependency.
- Latency variance under load.

Mitigations:

- Translation cache.
- Per-room mode selection.
- Timeouts + retry + fallback behavior.

Availability behavior:

- Translation is a best-effort asynchronous enrichment.
- If OpenAI is unavailable, chat still functions with original-message delivery.
- Failures are surfaced as translation_unavailable status and telemetry events.

### Room Cost and Delay Analytics
Decision:

- Track translation telemetry per target-language attempt and aggregate by room.

Approach:

- Persist raw telemetry events in PostgreSQL.
- Materialize hourly aggregates for admin dashboards.
- Use Redis to cache dashboard query responses for short windows.

Trade-offs:

- Raw telemetry in PostgreSQL keeps auditability and supports backfills.
- Aggregated tables reduce dashboard query cost and response time.
- Redis-cached summaries improve admin UI latency but can be briefly stale.

Recommended freshness targets:

- Near real-time cards: 15 to 60 seconds delayed.
- Historical trend charts: 1 to 5 minute refresh intervals.

## Scalability Strategy

Phase 1:

- Single API replica, single worker.
- RabbitMQ required.
- Redis required.

Phase 2:

- Multiple API replicas + Redis pub/sub.
- Worker autoscaling by queue depth.

Phase 3:

- Partitioned message tables.
- RabbitMQ federation or migration to Kafka only if replay throughput requirements justify it.

## Redis Decision Guide

Recommended Redis keyspaces:

- presence:user:{user_id}
- room:meta:{room_id}
- room:members:{room_id}
- rate_limit:{scope}:{id}
- dedup:request:{request_id}
- translation:cache:{hash}

TTL guidance:

- Presence keys: 30 to 90 seconds with heartbeat refresh.
- Dedup keys: 2 to 10 minutes.
- Translation cache: 1 to 24 hours depending on cost goals.
- Room metadata cache: 1 to 5 minutes with explicit invalidation on updates.

## Security Baseline

- JWT auth for REST and WebSocket handshake.
- Authorization checks on every room action.
- Input validation and size limits.
- Secret management via environment variables.
- Audit logs for admin room actions.
