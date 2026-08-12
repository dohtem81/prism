# Components and Responsibilities

## 1. Realtime Gateway

Responsibilities:

- Authenticate WebSocket sessions.
- Manage connection lifecycle, heartbeats, and reconnect.
- Subscribe/unsubscribe users to room channels.
- Emit MessageCreated and MessageUpdated events.
- Handle delivery acknowledgements and replay requests.

Key outputs:

- Low-latency fanout of original and translated updates.

## 2. Room Service

Responsibilities:

- Create rooms.
- Add/remove members.
- Store room-level translation settings.
- Resolve effective language set for active participants.

Key outputs:

- Membership authorization decisions.
- Translation policy context for each message.

## 3. Message Service

Responsibilities:

- Accept SendMessage commands.
- Validate sender membership and payload schema.
- Persist original message and initial event.
- Publish TranslationRequested jobs.
- Apply idempotency by client_message_id per user and room.

Key outputs:

- Durable message record.
- Job requests for translation worker.

## 4. Translation Worker

Responsibilities:

- Consume TranslationRequested jobs.
- Deduplicate target languages across recipients.
- Skip source language translation.
- Call LLM adapter and apply fallback/retry.
- Persist translation rows.
- Emit MessageUpdated events with version increments.
- On provider outage, mark translation state without impacting original message delivery.

Key outputs:

- Language-specific translation patches.

## 5. LLM Adapter (OpenAI)

Responsibilities:

- Build translation prompts by room mode.
- Execute provider API calls.
- Normalize output schema.
- Enforce timeout, retry, and error mapping.
- Expose token usage for cost metrics.
- Implement circuit breaker behavior for upstream unavailability.

Key outputs:

- Structured translation payloads.
- Structured failure outcomes that allow graceful degradation.

## 6. History Service

> **Status: Implemented.** Room history endpoint returns recent messages with translations for reconnect-safe replay.

Responsibilities:

- Return recent room history with original text and available translations.
- Support cursor-based replay after reconnect or browser refresh.

Key outputs:

- Consistent timeline reconstruction for clients that rejoin a room.

## 7. Persistence Layer

Responsibilities:

- PostgreSQL repositories for rooms, membership, messages, translations, outbox/events.
- Transaction boundaries for message create + outbox write.
- Migration ownership and data constraints.

Key outputs:

- Integrity and durability guarantees.

## 8. Redis Layer

> **Status: Partially used.** Translation result cache is active. Presence, rate limiting, and multi-instance pub/sub fanout are pending.

Responsibilities:

- Translation result cache keyed by content hash, source language, and target language.
- Future: presence tracking, rate-limit counters, and multi-instance WebSocket fan-out.

Key outputs:

- Reduced redundant provider calls for repeated content.

## 9. Observability Layer

Responsibilities:

- Structured logging with correlation ids.
- Metrics for latency, queue lag, error rate, token usage.
- Distributed tracing across API, worker, and provider calls.

Key outputs:

- Operational visibility and incident diagnostics.

## 10. Room Analytics Service

> **Status: Pending.** Telemetry schema exists; aggregation jobs, API, and UI are follow-on work.

Responsibilities:

- Ingest per-translation telemetry events from workers.
- Compute room-scoped aggregates for cost, delay, and reliability.
- Expose admin-facing metrics API with time-window and language-pair breakdowns.
- Cache recent dashboard responses for low-latency reads.

Planned metrics:

- Total translation spend and cost per message by room
- Queue wait time, provider latency, and end-to-end delay percentiles
- Success, failure, and retry rates
- Top language pairs by volume and cost
