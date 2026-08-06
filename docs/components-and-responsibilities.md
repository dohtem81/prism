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

Responsibilities:

- Return paginated room history.
- Include original text and available translations.
- Support replay from room sequence on reconnect.

Key outputs:

- Consistent timeline reconstruction for clients.

## 7. Persistence Layer

Responsibilities:

- PostgreSQL repositories for rooms, membership, messages, translations, outbox/events.
- Transaction boundaries for message create + outbox write.
- Migration ownership and data constraints.

Key outputs:

- Integrity and durability guarantees.

## 8. Redis Layer

Responsibilities:

- Maintain ephemeral presence state with TTL heartbeats.
- Cache hot room metadata and membership snapshots.
- Provide pub-sub channel for cross-instance websocket fanout.
- Hold short-lived translation cache entries.
- Enforce rate-limit and dedup counters.

Key outputs:

- Reduced database load and lower end-to-end latency.
- Stable realtime behavior across multiple API instances.

## 9. Observability Layer

Responsibilities:

- Structured logging with correlation ids.
- Metrics for latency, queue lag, error rate, token usage.
- Distributed tracing across API, worker, and provider calls.

Key outputs:

- Operational visibility and incident diagnostics.

## 10. Room Analytics Service

Responsibilities:

- Ingest translation telemetry events from workers.
- Compute room-scoped aggregates for cost and delay.
- Expose admin-facing metrics APIs with time windows and breakdowns.
- Cache recent dashboard responses in Redis for low-latency UI queries.

Key outputs:

- Room admin dashboard data for spend, delay, reliability, and usage.

Tracked metrics:

- Total translation spend by room.
- Cost per message and cost per translated character/token.
- Queue wait time, provider latency, and end-to-end translation delay.
- Success rate, failure rate, and retry rate.
- Top language pairs by volume and cost.
