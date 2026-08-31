# Analytics layer plan

## Goal
Provide room-level admin visibility into translation spend, delay, and reliability.

## Scope
- Room admin metrics summary endpoint
- Cost visibility by room and time window
- Delay percentiles and queue health
- Translation success/failure breakdown

## Current state
- Telemetry tables and worker instrumentation exist.
- The analytics API and dashboard layer remain TODO.

## Tasks
1. Define nightly or near-real-time aggregation jobs from translation telemetry.
2. Add room metrics storage model for hourly summaries.
3. Build a room metrics summary API for admins.
4. Include cost, latency, success rate, retry rate, and language-pair breakdown.
5. Add bounded freshness/caching in Redis to keep admin views fast.

## Data model ideas
- room_metrics_hourly
- room_metrics_daily
- language_pair_rollups
- translation_telemetry (source of truth)

## API design
- GET /v1/admin/rooms/{room_id}/metrics?window=24h
- Return summary totals plus breakdowns by language pair and time bucket.
- Keep response payload compact and cacheable.

## Acceptance criteria
- Admin can fetch room-level translation cost and lag data.
- Metrics are aggregated from persisted telemetry, not live-only data.
- Endpoint remains fast through Redis caching with freshness guardrails.
- The dashboard can display a concise summary without loading raw event history.

## Relevant code
- shared/db/models.py
- services/worker/app/tasks/translation.py
- docs/implementation-todo.md
- docs/architecture-overview.md
