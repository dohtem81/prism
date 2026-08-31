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

### Phase 1: request correlation upgrade
Keep the current correlation IDs but standardize them into a trace context compatible with mature observability tooling.

### Phase 2: API instrumentation
Add tracing to the FastAPI boundary and the most important request handlers.

### Phase 3: worker instrumentation
Add spans for translation job execution, retries, and final delivery.

### Phase 4: exporter and storage
Add a collector or exporter target such as OTLP, a local tracing backend, or a team-standard platform when the app grows beyond local validation.

## Recommended direction
The ideal future design is:
- a shared trace context propagated through HTTP and Celery,
- minimal instrumentation at the service boundary,
- storage/visualization enabled when real operational use warrants it.

## Acceptance criteria
- Every API request has a trace context and request correlation ID.
- Message lifecycle events can be reconstructed across API and worker boundaries.
- Translation latency and retry behavior are visible in traces.
- Operator diagnostics can answer where work stalled and why.

## Relevant files
- services/api/app/main.py
- services/api/app/auth/dependencies.py
- services/api/app/api/messages.py
- services/api/app/realtime/websocket_gateway.py
- services/worker/app/tasks/translation.py
- shared/logging_utils.py
- docs/implementation-todo.md
