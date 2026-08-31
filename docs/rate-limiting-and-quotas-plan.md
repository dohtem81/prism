# Rate limiting and quotas plan

## Goal
Add abuse protection and predictable capacity controls without blocking the current single-instance demo flow.

## Current state
- JWT-based auth is implemented.
- Message payload validation and content size limits are enforced.
- There is no active rate limiting, no request quota enforcement, and no per-user or per-room abuse controls yet.
- The app is still intentionally kept simple for local testing and demo usage.

## Why this is intentionally deferred until later
The project is currently optimized for simplicity, validation, and demo readiness rather than production-scale abuse protection. This is a known gap, not a hidden bug.

The system should add limiting only once the app is running in a more real-world environment with:
- more users and active rooms,
- external traffic or public exposure,
- more visible abuse risks,
- higher operational expectations around fairness and cost control.

## Problem to solve
Without limits, a single user, bot, or client can generate excessive message traffic, create room churn, or spam translation jobs. In a public or semi-public deployment, this can cause:
- queue overload,
- provider cost spikes,
- degraded latency for other users,
- noisy operational signals and unfair resource consumption.

## Proposed approach
Use Redis-backed rate limiting in front of the API layer, with a small set of configurable limits and quotas.

### 1) Endpoint-level limits
Apply different policies depending on endpoint type:
- POST /v1/messages
  - limit per user per minute
  - limit per room per minute
  - burst allowance for normal chat
- POST /v1/rooms
  - lower limit per user per hour
- POST /v1/rooms/{room_id}/members
  - low limit per admin action burst
- WebSocket connect path
  - cap number of active connections per user
  - cap per room connection count if needed

### 2) User and room quotas
Track quotas in Redis or persisted counters:
- message count per user per time window
- messages per room per time window
- translation job quota per user or room
- daily or hourly maximums for abusive behavior

### 3) Token bucket or sliding window
Use a lightweight algorithm that fits the stack:
- Redis INCR + TTL for short sliding-window counters
- token bucket for burst-safe traffic shaping
- per-policy keys such as:
  - `rl:user:{user_id}:messages`
  - `rl:room:{room_id}:messages`
  - `rl:ip:{ip}:api`

### 4) Response metadata
When a client is rate-limited, return clear metadata:
- `429 Too Many Requests`
- retry-after seconds
- rate-limit headers such as:
  - X-RateLimit-Limit
  - X-RateLimit-Remaining
  - X-RateLimit-Reset

### 5) Monitoring and alerts
When a limit is hit, log it with user/room context and correlation ID so it is traceable. Count violations to identify abusive patterns.

## Implementation phases

### Phase 1: hardcoded defaults for local safety
Add rate limiting behind config defaults:
- low per-user burst limit for message creation
- low per-IP threshold for API endpoints
- room-level per-minute guardrails

This is enough to protect the demo environment while staying simple.

### Phase 2: Redis-backed enforcement
Move the logic behind a shared helper in the API layer:
- `services/api/app/infra/rate_limit.py`
- `check_rate_limit(key, limit, window_seconds)`
- `record_rate_limit_hit(...)`

### Phase 3: quota enforcement
Add user and room quotas for stronger protection:
- per-user message budget
- per-room message budget
- translation-cost budget if the platform expands externally

### Phase 4: admin visibility
Expose quota and violation metrics through the admin API, including:
- top offenders,
- rate-limited requests by endpoint,
- room-level abuse counts.

## Proposed default policy
These are starting values, not final production numbers:
- messages per user per minute: 30
- messages per room per minute: 120
- room creation per user per hour: 10
- active websocket connections per user: 3
- burst allowance: small multiplier above steady-state rate

These should be tuned after real traffic data is available.

## Acceptance criteria
- API requests are throttled before expensive translation work is enqueued.
- A user who exceeds the configured limit gets a clear `429` response.
- The rate limit state is stored in Redis and is cheap to check.
- Rate-limit hits are logged with correlating request metadata.
- Room and user quotas can be tuned via config without changing app logic.

## Relevant files
- services/api/app/api/messages.py
- services/api/app/api/rooms.py
- services/api/app/auth/dependencies.py
- services/api/app/main.py
- services/api/app/infra/settings.py
- docs/implementation-todo.md
- docs/production-hardening-plan.md
