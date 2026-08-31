# Distributed tracing plan

## Goal
Add end-to-end tracing for requests, message processing, and translation work so failures and latency issues can be diagnosed quickly once the app moves beyond a simple demo deployment.

## Current status
- Structured request logging and correlation IDs are already in place.
- Queue and translation metrics exist at a basic level.
- There is no full distributed tracing stack or end-to-end request graph yet.
- This is intentionally deferred for now because the project is still operating in a compact, single-instance, validation-focused setup.

## Why we are deferring it
The system is currently small enough that correlation IDs and high-level logs are sufficient for debugging and local QA. A full tracing stack adds operational complexity and infrastructure costs without providing much benefit until traffic, services, and failure modes become more realistic.

## Problem to solve
Without structured tracing across API and worker boundaries, it is harder to answer questions such as:
- where did a message get stuck?
- which worker step added latency?
- which request triggered a failed translation?
- what was the upstream correlation between API request and background job?

## Proposed architecture
Use an OpenTelemetry-style model with a lightweight implementation, layered around the existing structured logging and correlation ID approach.

### 1) Trace propagation
Propagate a trace ID and span ID across:
- HTTP requests into the FastAPI API
- Celery task execution
- Redis event publishing and local gateway fanout
- queue wait and translation latency stages

### 2) API spans
Instrument these critical call paths:
- room creation
- membership mutation
- message creation
- websocket connect and room subscribe
- history replay
- admin metrics fetch

### 3) Worker spans
Instrument these steps:
- task receive
- provider call
- retry attempt
- DLQ classification
- translation completion
- dispatch of `MessageUpdated`

### 4) span naming and attributes
Attach useful attributes such as:
- `room_id`
- `user_id`
- `message_id`
- `provider`
- `model`
- `status`
- `queue_name`
- `retry_count`

### 5) metrics correlation
Let traces and metrics share a common correlation model so logs, metrics, and traces become easier to connect during incident analysis.

## Implementation phases

### Phase 1: request correlation upgrade — DONE
`shared/tracing.py` adds a lightweight trace context (`trace_id`/`span_id`, contextvars-based)
layered on top of the existing correlation ID. The API request middleware in
`services/api/app/main.py` accepts an inbound `X-Trace-ID` header (falling back to the
correlation ID) and returns it on the response.

### Phase 2: API instrumentation — DONE
Spans wrap the critical request handlers:
- `api.message.create` (services/api/app/api/messages.py)
- `api.room.create`, `api.room.membership.upsert`, `api.room.history.replay`
  (services/api/app/api/rooms.py)
- `api.ws.connect` (services/api/app/realtime/websocket_gateway.py)
- `api.admin.metrics.fetch` (services/api/app/api/admin.py)

### Phase 3: worker instrumentation — DONE
`services/worker/app/tasks/translation.py` adopts the inbound `trace_id`/`correlation_id`
passed from the API (via Celery task kwargs) and adds spans:
- `worker.translation.task_receive` (includes `retry_count` from the Celery task request)
- `worker.translation.provider_call`
- `worker.translation.dlq_classify`
- `worker.translation.dispatch_update`

### Phase 4: exporter and storage — deferred
No OTLP exporter or external tracing backend is wired up yet. Spans are currently emitted
as structured log events (`span_started`/`span_completed`/`span_failed`) carrying
`trace_id`, `span_id`, `parent_span_id`, and span attributes, which is enough to
reconstruct request/message flow from logs. Adding a real collector/exporter remains
future work once the app runs beyond local validation.

## Recommended direction
The ideal future design is:
- a shared trace context propagated through HTTP and Celery,
- minimal instrumentation at the service boundary,
- storage/visualization enabled when real operational use warrants it.

## Acceptance criteria
- Every API request has a trace context and request correlation ID. ✅
- Message lifecycle events can be reconstructed across API and worker boundaries. ✅
  (trace_id propagates from the HTTP request into the Celery task and its spans)
- Translation latency and retry behavior are visible in traces. ✅
  (`worker.translation.provider_call` spans plus `retry_count` on `task_receive`)
- Operator diagnostics can answer where work stalled and why. ✅ for logs-based analysis;
  a dedicated trace visualization backend is still deferred (see Phase 4).

## Relevant files
- services/api/app/main.py
- services/api/app/auth/dependencies.py
- services/api/app/api/messages.py
- services/api/app/realtime/websocket_gateway.py
- services/worker/app/tasks/translation.py
- shared/logging_utils.py
- docs/implementation-todo.md
