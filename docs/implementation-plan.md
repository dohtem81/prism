# Implementation Plan

## Milestone 1: Foundation

Status:

- DONE (verified 2026-08-05)

Deliverables:

- Repository structure and service boundaries.
- Docker Compose with api, worker, postgres, rabbitmq.
- Docker Compose with redis enabled.
- Config management and environment profiles.
- DB migrations baseline.

Definition of done:

- Services start locally via one compose command.

Verification evidence:

- `docker compose -f deploy/compose/docker-compose.yml up --build -d` completed successfully.
- `docker compose -f deploy/compose/docker-compose.yml ps` showed api, worker, postgres, rabbitmq, and redis running.
- `GET /v1/health` returned `{"status":"ok"}`.

## Milestone 2: Room and Auth APIs

Deliverables:

- JWT-based auth integration.
- Create room and membership APIs.
- Role model (admin/member).
- Preferred language stored per member.

Definition of done:

- Authorized users can create rooms and manage membership.

## Milestone 3: Realtime Messaging (Original Only)

Deliverables:

- WebSocket gateway and room subscriptions.
- SendMessage command path.
- Durable message persistence.
- MessageCreated fanout.
- Redis pub-sub fanout integration for multi-instance readiness.

Definition of done:

- Users in same room receive original messages in real time.

## Milestone 4: Translation Pipeline

Deliverables:

- TranslationRequested queue contract and RabbitMQ exchange/queue bindings.
- Worker consuming and translating target languages.
- MessageUpdated patch events.
- Room-level quality mode wiring.

Definition of done:

- Users receive follow-up translation updates for same message id.

## Milestone 5: History and Replay

Deliverables:

- History API with cursor pagination.
- Reconnect replay by room sequence.
- Deduplication and idempotency checks.

Definition of done:

- Client can recover consistent timeline after disconnect.

## Milestone 6: Hardening and Observability

Deliverables:

- Metrics, logs, and traces.
- Load and chaos tests for queue and provider failures.
- Rate limits and abuse controls.
- Translation error handling policies.
- Redis cache hit-rate, eviction, and keyspace observability dashboards.
- Room-level cost and delay dashboards for admins.

Definition of done:

- SLOs and operational dashboards available.

## Milestone 7: Room Admin Analytics

Deliverables:

- TranslationCompleted telemetry event emission in worker pipeline.
- Aggregation jobs for room-level cost, delay percentiles, and reliability metrics.
- Admin metrics REST endpoints for summary and language breakdown.
- Redis-cached dashboard responses with bounded freshness.

Definition of done:

- Room admin interface can display near real-time spend and delay insights for configurable time windows.

## Suggested Initial Data Model

Tables:

- users
- rooms
- room_members
- messages
- message_translations
- room_events
- outbox_events
- translation_telemetry
- room_metrics_hourly

Minimum indexes:

- messages(room_id, created_at desc)
- room_events(room_id, room_sequence)
- message_translations(message_id, target_lang) unique
- room_members(room_id, user_id) unique
- translation_telemetry(room_id, occurred_at)
- room_metrics_hourly(room_id, bucket_start)

## Acceptance Scenarios

1. User sends message to room and all members receive MessageCreated.
2. Worker appends translation and members receive MessageUpdated.
3. Two recipients with same preferred language trigger one translation call.
4. Re-sent client_message_id returns same message id (idempotency).
5. Disconnected client replays missed events using last room sequence.
6. Room admin can view room spend and delay percentiles for the selected period.
7. When the LLM provider is unavailable, users still receive and can read original messages in real time.
8. When the LLM provider is unavailable, translation status is marked as translation_unavailable without breaking room timeline continuity.
