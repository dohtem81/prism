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

Status:

- Planned, not implemented yet.

Responsibilities:

- return paginated room history
- include original text and available translations
- support replay after reconnect or browser refresh

Key outputs:

- consistent timeline reconstruction for clients after the current live-room stage is complete

## 7. Persistence Layer

Responsibilities:

- PostgreSQL repositories for rooms, membership, messages, translations, outbox/events.
- Transaction boundaries for message create + outbox write.
- Migration ownership and data constraints.

Key outputs:

- Integrity and durability guarantees.

## 8. Redis Layer

Status:

- Infrastructure present, but not fully used for the current runtime model.

Responsibilities:

- local cache support for transient metadata or translation lookups
- future presence tracking and rate-limit support
- future multi-instance pub/sub fanout and replay support

Key outputs:

- reduced local operational friction for the current single-instance setup
- foundation for later scaling work without changing the current message contract

## 9. Observability Layer

Responsibilities:

- Structured logging with correlation ids.
- Metrics for latency, queue lag, error rate, token usage.
- Distributed tracing across API, worker, and provider calls.

Key outputs:

- Operational visibility and incident diagnostics.

## 10. Room Analytics Service

Status:

- Planned, not implemented yet.

Responsibilities:

- ingest translation telemetry events from workers
- compute room-scoped aggregates for cost and delay
- expose admin-facing metrics APIs with time windows and breakdowns
- cache recent dashboard responses for low-latency admin views

Key outputs:

- room admin dashboard data for spend, delay, reliability, and usage once this phase is implemented

Tracked metrics:

- total translation spend by room
- cost per message and cost per translated character/token
- queue wait time, provider latency, and end-to-end translation delay
- success rate, failure rate, and retry rate
- top language pairs by volume and cost

The telemetry schema exists in the data model, but the analytics API and UI layers are still pending.
