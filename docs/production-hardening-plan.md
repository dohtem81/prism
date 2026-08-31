# Production hardening plan

## Goal
Add operational safety, traceability, and runtime metrics before treating the system as production-ready.

## Scope
- Structured logging for API and worker
- Request correlation IDs across queue and websocket paths
- Queue delay and translation latency metrics
- Basic dashboards and alert thresholds

## Current state
- API and worker are functional and covered by unit tests.
- Redis and RabbitMQ are already part of the stack.
- Observability work remains explicit TODO in the implementation tracker.

## Tasks
1. Add request-scoped correlation IDs from HTTP requests into logs and worker jobs.
2. Standardize log structure for API, worker, and dead-letter flows.
3. Instrument queue delay metrics for translation.requested.q.
4. Instrument provider latency and end-to-end translation delay metrics.
5. Expose Prometheus or structured metrics endpoints for operational dashboards.
6. Add SLO-style alert thresholds for queue lag and failed translations.

## Implementation notes
- Propagate idempotency keys and message ids through the worker job payload.
- Attach correlation ids to `MessageCreated` / `MessageUpdated` events when emitted.
- Store metrics in a lightweight in-process or Prometheus backend compatible with current stack.

## Acceptance criteria
- Every API request has a trace/correlation id in logs.
- Translation tasks log both job metadata and outcome.
- Queue delay and provider latency metrics are visible.
- Dead-letter events are traceable back to the original room/message context.

## Relevant code
- services/api/app/api/messages.py
- services/api/app/realtime/websocket_gateway.py
- services/worker/app/tasks/translation.py
- docs/implementation-todo.md
