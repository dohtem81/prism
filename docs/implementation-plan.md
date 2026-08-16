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

Status: **DONE** (verified 2026-08-09)

Deliverables:

- JWT-based auth integration. [implemented]
- Create room and membership APIs. [implemented]
- Role model (admin/member). [implemented]
- Preferred language stored per member. [implemented at the user-profile level]

Definition of done:

- Authorized users can create rooms and manage membership. [implemented in API and covered by unit tests]

Verification evidence:

- Docker-based unit suite completed successfully: `16 passed in 0.73s`.
- The API layer includes `/v1/users`, `/v1/rooms`, and `/v1/rooms/{room_id}/members` routes.

Notes:

- This milestone covers the auth-and-rooms foundation only. Realtime messaging is part of Milestone 3.

## Milestone 3: Realtime Messaging (Original Only)

Status:

- IMPLEMENTED (verified 2026-08-11) as an initial in-process slice.

Deliverables:

- WebSocket gateway and room subscriptions. [implemented]
- SendMessage command path. [implemented]
- Durable message persistence. [implemented]
- MessageCreated fanout. [implemented for connected room subscribers]
- Redis pub-sub fanout integration for multi-instance readiness. [not yet implemented]

Definition of done:

- Users in same room receive original messages in real time. [achieved for connected clients in the current single-instance runtime]

Notes:

- The current implementation provides room-scoped realtime delivery for connected clients.
- Reconnect replay/history recovery and multi-instance fanout remain follow-on work for later phases.

## Milestone 4: Translation Pipeline

Status:

- IMPLEMENTED (verified 2026-08-11) as the current backend translation-update slice.

Deliverables:

- TranslationRequested queue contract and RabbitMQ exchange/queue bindings.
- Worker consuming and translating target languages.
- MessageUpdated patch events.
- Room-level quality mode wiring.

Implementation approach:

1. Keep the existing message creation path as the entrypoint for original-message persistence.
2. Introduce a dedicated translation-request flow that queues work for each target language derived from room membership preferences.
3. Have the worker write translated content to the message_translations table, update message status, and emit a MessageUpdated event.
4. Broadcast MessageUpdated events to connected room subscribers so clients receive follow-up translations without breaking the original timeline.
5. Preserve idempotency by deduplicating per message/target-language work and handling provider failures with a translation_unavailable fallback.

Definition of done:

- Users receive follow-up translation updates for the same message id, and provider failures do not break the original room timeline. [implemented for the current backend path; retry/DLQ hardening remain follow-on work]

Notes:

- The current implementation persists translations, updates message status, and emits a MessageUpdated event that preserves the original message id and includes the original message plus translations.
- The worker now uses a translation provider abstraction, and provider/model selection is configuration-driven via `TRANSLATION_PROVIDER` and `TRANSLATION_MODEL` with fallback support.
- The unit test suite validates the translation-update path, provider resolution behavior, dead-letter routing, and the send-message-to-translation-update flow.
- Retry and DLQ behavior is now in place for transient provider failures, and permanent failures are sent to the `translation.failed.q` queue.

## Milestone 5: History and Replay

Status:

- DONE (verified 2026-08-11)

Deliverables:

- Room history endpoint with recent message window. [implemented]
- Reconnect-safe replay using room sequence cursor. [implemented]
- Client-side deduplication by event_id. [implemented]

Definition of done:

- Client recovers consistent timeline after disconnect. [achieved for the current window-based replay]

Notes:

- Full cursor-paginated history for arbitrarily old messages is follow-on work; current replay covers the recent message window.

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
