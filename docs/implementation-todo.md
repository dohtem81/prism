# Implementation TODO

Tracks current task status and next actions.

**Status legend:** `TODO` · `IN_PROGRESS` · `BLOCKED` · `DONE`

---

## Phase summary

| Milestone | Status |
|---|---|
| Milestone 1 — Foundation | DONE |
| Milestone 2 — Room and Auth APIs | DONE |
| Milestone 3 — Realtime Messaging and History | DONE |
| Milestone 4 — Translation Pipeline | DONE |
| Milestone 5 — History Replay | DONE |
| Milestone 6 — Observability | DONE |
| Milestone 7 — Analytics | DONE |

---

## Task tracker

| ID | Milestone | Area | Task | Status | Priority | Last Updated | Notes |
|---|---|---|---|---|---|---|---|
| P1-01 | Milestone 1 | Foundation | Finalize Docker local run flow (api/worker/postgres/rabbitmq/redis) | DONE | High | 2026-08-05 | Compose and Dockerfiles scaffolded. |
| P1-02 | Milestone 1 | Foundation | Validate migrations end-to-end in running environment | DONE | High | 2026-08-05 | Verified via Docker: alembic upgrade head against compose postgres. |
| P1-03 | Milestone 2 | API | Replace temporary X-User-Id auth with JWT auth | DONE | High | 2026-08-09 | JWT-based auth is now implemented and covered by unit tests. |
| P1-04 | Milestone 2 | API | Add room creation and membership endpoints | DONE | High | 2026-08-09 | Room creation and membership management endpoints are implemented. |
| P1-05 | Milestone 3 | Messaging | Implement MessageCreated realtime fanout from outbox | DONE | High | 2026-08-09 | MessageCreated fanout is implemented for connected room subscribers through the realtime gateway. |
| P1-06 | Milestone 3 | Messaging | Implement MessageUpdated realtime fanout from outbox | DONE | High | 2026-08-11 | MessageUpdated fanout is verified in the realtime unit tests and delivered to room subscribers. |
| P1-07 | Milestone 4 | Worker | Add robust retry policy and DLQ handling strategy | DONE | Medium | 2026-08-11 | The worker retries transient provider failures and dispatches permanent failures to the `translation.failed.q` dead-letter queue. |
| P1-08 | Milestone 4 | Worker | Improve translation provider abstraction (adapter interface) | DONE | Medium | 2026-08-11 | A provider abstraction is now implemented and exercised by unit tests, with configuration-driven provider/model selection and fallback handling. |
| P1-09 | Milestone 4 | Worker | Add fallback policy when translation unavailable | DONE | High | 2026-08-09 | translation_unavailable status is set in the current worker flow when translations fail. |
| P1-10 | Cross-cutting | Data | Add seed/dev bootstrap script for users/rooms/members | DONE | Medium | 2026-08-30 | Included in scripts/bootstrap_dev.py and verified by unit tests. |
| P1-11 | Milestone 7 | Analytics | Build room admin metrics summary endpoint | DONE | Medium | 2026-08-30 | `/v1/admin/rooms/{room_id}/metrics` returns room telemetry summary and breakdowns. |
| P1-16 | Milestone 2 | API | Add user onboarding endpoint for profile creation | DONE | High | 2026-08-09 | `/v1/users` creates or updates a user profile and persists preferred language. |
| P1-17 | Milestone 2 | Data | Add user-level preferred language migration | DONE | High | 2026-08-09 | Alembic migration `0002_add_user_preferred_lang` applied successfully in Docker. |
| P1-12 | Milestone 6 | Observability | Add structured logging and correlation ids | DONE | Medium | 2026-08-30 | Request correlation IDs and structured API/worker logging are in place. |
| P1-13 | Milestone 6 | Observability | Add basic metrics for queue delay and translation latency | DONE | Medium | 2026-08-30 | Metrics are recorded and exposed through the room analytics summary. |
| P1-14 | Milestone 3 / 4 | Testing | Add integration test: send message -> queued -> translated | DONE | High | 2026-08-11 | A full send-message-to-translation-update flow test is included in the unit regression suite. |
| P1-15 | Milestone 6 | Security | Validate input limits and enforce payload size checks | DONE | Medium | 2026-08-16 | `SendMessage` now enforces source language format and payload size bounds (including 4000-char content limit); rate limiting and quotas remain follow-on hardening. |
| P1-18 | Milestone 5 | History | Build room history API and reconnect replay | DONE | Medium | 2026-08-11 | The room history endpoint and reconnect-safe replay logic are implemented and validated in the live room flow. |
| P1-19 | Cross-cutting | Architecture | Redis pub/sub multi-replica fanout for the realtime gateway | DONE | High | 2026-10-09 | All room events (API and worker) are published to `room:{room_id}:events`; each API instance subscribes only for rooms with local WebSocket clients, delivers to its own sockets, releases the subscription when the last local client leaves, and re-subscribes after Redis errors. Single-instance runs use the same path. Covered by `tests/unit/api/test_multi_instance_fanout.py`. Sticky sessions/load-balancer config and worker scaling are out of scope. |
| P1-20 | Cross-cutting | Security | Add rate limiting, quotas, and abuse protections for message send volume and API usage | DONE | Medium | 2026-08-30 | All 4 plan phases implemented: Redis-backed per-user/per-room rate limits, daily message/translation-job quotas, and admin violation visibility (`GET /v1/admin/rate-limits/violations`). Fails open on Redis errors. See docs/rate-limiting-and-quotas-plan.md. |
| P1-21 | Milestone 6 | Observability | Add full request tracing and end-to-end distributed tracing beyond basic correlation IDs | DONE | Medium | 2026-08-30 | Lightweight trace context (`shared/tracing.py`) with trace_id/span_id propagates from HTTP requests through Celery into the worker; spans instrument message/room/websocket/admin API handlers and translation task execution (provider call, DLQ, dispatch). Exporter/storage backend remains deferred. See docs/distributed-tracing-plan.md. |
| P1-22 | Cross-cutting | Operations | Capture load, latency, and performance baselines under realistic traffic | TODO | Medium | 2026-08-30 | No benchmark or load/performance dataset exists yet. See docs/performance-baselines-plan.md. |
| P1-23 | Cross-cutting | Security | Add real multi-tenancy boundaries and stronger isolation controls | TODO | Medium | 2026-08-30 | There is no tenant model or hardened multi-tenant isolation beyond basic JWT auth. See docs/multi-tenancy-hardening-plan.md. |
| P1-24 | Cross-cutting | Security | Harden auth and API security beyond basic JWT validation | DONE | Medium | 2026-10-09 | Phase 1 (close known gaps) DONE: `dev-token` bypass only works when `APP_ENV=dev`; access tokens use `ACCESS_TOKEN_TTL_MINUTES` (default 30) instead of 8h; startup logs a WARNING on the default `jwt_secret` outside dev; explicit, configurable CORS (`CORS_ALLOWED_ORIGINS`, no wildcard with credentials); `.env.example` updated; covered by `tests/unit/api/test_auth_hardening.py`. Phase 2 (token lifecycle) DONE: access tokens carry `jti`/`iat`/`type`; Redis-backed token store (`services/api/app/auth/token_store.py`) with `auth:revoked:{jti}` denylist and single-use `auth:refresh:{jti}` registry; refresh tokens (`REFRESH_TOKEN_TTL_DAYS`, default 7) rotate on every use and reuse is rejected; `POST /v1/auth/refresh` and `POST /v1/auth/logout` added; token checks fail closed on Redis errors; covered by `tests/unit/api/test_auth_hardening_phase2.py`. Phase 4 (transport hardening and auditability) DONE: structured security events (`auth_rejected`, `membership_denied`, `token_reused`, `logout`) via `services/api/app/auth/security_events.py` with correlation/trace context; Redis violation counters (`auth:violations:*`, fail open); `GET /v1/admin/auth/violations` (same shape as the rate-limit endpoint); CORS stays explicit with a production note; covered by `tests/unit/api/test_security_events.py`. Phase 3 (session and device visibility) DONE: Redis session records `auth:session:{user_id}:{jti}` (`issued_at`, `last_used_at`, `token_type`, linked `refresh_jti`) created on issuance, touched on every validated access token, removed on rotation and logout; replaying a rotated refresh token revokes all of that user's sessions (denylist + refresh invalidation) and logs `token_reused` and `all_sessions_revoked_for_user`; `GET /v1/admin/auth/sessions` shows active session counts and recent revocations; covered by `tests/unit/api/test_session_tracking.py`. See docs/auth-security-hardening-plan.md. |

---

## Next up

1. Performance baselines — capture load and latency data under realistic traffic (P1-22).
2. Multi-tenancy hardening — real tenant boundaries and stronger isolation (P1-23).

> These are the only remaining TODO items in the tracker; all other milestones and cross-cutting tasks are DONE. P1-22 in docs/performance-baselines-plan.md and P1-23 in docs/multi-tenancy-hardening-plan.md.

---

## Change log

| Date | Change |
|---|---|
| 2026-08-05 | Initial tracker created |
| 2026-08-05 | Milestone 1 (Foundation) marked DONE — Docker startup, migrations, health check, and tests passed |
| 2026-08-09 | Milestones 2 and 3 verified — room/user APIs, realtime fan-out, and translation pipeline operational |
| 2026-08-11 | Milestones 4 and 5 verified — translation provider abstraction, DLQ, history replay, and full test suite passing |
| 2026-08-12 | `.env` removed from repository history; documentation refreshed |
| 2026-08-12 | Docs rewritten for clarity; Mermaid diagrams added to README and data-flow doc |
| 2026-08-16 | WebSocket auth hardened to token-derived identity, realtime event envelope fields aligned with contract, history anchor validation tightened, and payload input limits enforced |
| 2026-08-30 | Added deferred architecture and hardening TODOs for single-instance status, no rate limiting/quotas, limited observability, missing performance data, and basic JWT-only security posture; also linked the explicit scaling-deferral plan for the single-instance choice |
| 2026-10-09 | P1-24 moved to IN_PROGRESS: auth hardening Phase 1 implemented (`dev-token` gated to dev, 30-minute access tokens, default-secret startup warning, explicit CORS, `.env.example` updated) |
| 2026-10-09 | P1-24 Phase 2 implemented: `jti`/`iat` claims, Redis denylist and single-use rotating refresh tokens, `POST /v1/auth/refresh` and `POST /v1/auth/logout`, fail-closed token validation |
| 2026-10-09 | P1-24 Phase 4 implemented: structured security events, Redis violation counters, `GET /v1/admin/auth/violations`, CORS production note (Phase 3 still open) |
| 2026-10-09 | P1-19 DONE: multi-instance realtime fan-out via Redis pub/sub with per-room local subscriptions, cleanup on last disconnect, and re-subscribe on Redis errors |
| 2026-10-09 | P1-24 Phase 3 implemented and P1-24 marked DONE: Redis session tracking, full-user session revocation on refresh-token reuse, `GET /v1/admin/auth/sessions` |
