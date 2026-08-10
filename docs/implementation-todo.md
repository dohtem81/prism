# Implementation TODO Tracker

This document tracks implementation work, current status, and next actions.

Status legend:

- TODO: Not started
- IN_PROGRESS: Actively being implemented
- BLOCKED: Waiting on dependency or decision
- DONE: Completed and verified

## How To Update

1. Change Status for the item.
2. Update Last Updated date.
3. Add short progress notes.
4. If blocked, include blocker details in Notes.

## Current Roadmap Items

Working convention:

- Docker-first execution is the default for local development, tests, and verification.
- Prefer compose-based commands over bare Python or pytest commands unless a Docker path is unavailable.
- The canonical compose entrypoint is `docker compose -f deploy/compose/docker-compose.yml ...`.

Phase summary:

- Milestone 1 (Foundation): DONE
- Milestone 2 (Room and Auth APIs): DONE for the implemented auth/room/user-profile pieces; remaining work is tracked below as follow-on items.
- Milestone 3 (Realtime Messaging): NEXT
- Milestones 4-7: Planned after the realtime path is in place.

Milestone mapping:

- Milestone 1: P1-01, P1-02
- Milestone 2: P1-03, P1-04, P1-16, P1-17
- Milestone 3: P1-05, P1-06, P1-14
- Milestone 4: P1-07, P1-08, P1-09
- Milestone 6: P1-12, P1-13, P1-15
- Milestone 7: P1-11
- Cross-cutting/local QA: P1-10

| ID | Milestone | Area | Task | Status | Priority | Last Updated | Notes |
|---|---|---|---|---|---|---|---|
| P1-01 | Milestone 1 | Foundation | Finalize Docker local run flow (api/worker/postgres/rabbitmq/redis) | DONE | High | 2026-08-05 | Compose and Dockerfiles scaffolded. |
| P1-02 | Milestone 1 | Foundation | Validate migrations end-to-end in running environment | DONE | High | 2026-08-05 | Verified via Docker: alembic upgrade head against compose postgres. |
| P1-03 | Milestone 2 | API | Replace temporary X-User-Id auth with JWT auth | DONE | High | 2026-08-09 | JWT-based auth is now implemented and covered by unit tests. |
| P1-04 | Milestone 2 | API | Add room creation and membership endpoints | DONE | High | 2026-08-09 | Room creation and membership management endpoints are implemented. |
| P1-05 | Milestone 3 | Messaging | Implement MessageCreated realtime fanout from outbox | TODO | High | 2026-08-05 | Outbox writes exist; publisher/fanout loop still needed. |
| P1-06 | Milestone 3 | Messaging | Implement MessageUpdated realtime fanout from outbox | TODO | High | 2026-08-05 | Worker writes outbox event; publish pipeline pending. |
| P1-07 | Milestone 4 | Worker | Add robust retry policy and DLQ handling strategy | TODO | Medium | 2026-08-05 | Configure Celery retry/backoff and failed-task observability. |
| P1-08 | Milestone 4 | Worker | Improve translation provider abstraction (adapter interface) | TODO | Medium | 2026-08-05 | OpenAI call is inline; extract adapter for testability. |
| P1-09 | Milestone 4 | Worker | Add fallback policy when translation unavailable | IN_PROGRESS | High | 2026-08-05 | translation_unavailable status already set; add retry/circuit logic. |
| P1-10 | Cross-cutting | Data | Add seed/dev bootstrap script for users/rooms/members | TODO | Medium | 2026-08-05 | Speeds local QA and API testing. |
| P1-11 | Milestone 7 | Analytics | Build room admin metrics summary endpoint | TODO | Medium | 2026-08-05 | Contract exists in docs, implementation pending. |
| P1-16 | Milestone 2 | API | Add user onboarding endpoint for profile creation | DONE | High | 2026-08-09 | `/v1/users` creates or updates a user profile and persists preferred language. |
| P1-17 | Milestone 2 | Data | Add user-level preferred language migration | DONE | High | 2026-08-09 | Alembic migration `0002_add_user_preferred_lang` applied successfully in Docker. |
| P1-12 | Milestone 6 | Observability | Add structured logging and correlation ids | TODO | Medium | 2026-08-05 | Needed across api + worker + outbox publisher. |
| P1-13 | Milestone 6 | Observability | Add basic metrics for queue delay and translation latency | TODO | Medium | 2026-08-05 | Start with counters/histograms and dashboard stub. |
| P1-14 | Milestone 3 / 4 | Testing | Add integration test: send message -> queued -> translated | TODO | High | 2026-08-05 | Cover idempotency and translation_unavailable path. |
| P1-15 | Milestone 6 | Security | Validate input limits and enforce payload size checks | TODO | Medium | 2026-08-05 | Prevent abuse and oversized requests. |

## Near-Term Execution Order

1. Complete the remaining Milestone 2 follow-on work if any.
2. Start Milestone 3 by implementing P1-05 and P1-06 for outbox publisher + websocket fanout.
3. Add P1-14 to validate the core message flow end to end.
4. Move on to Milestone 4 work once realtime delivery is stable.

## Change Log

- 2026-08-05: Initial tracker created.
- 2026-08-05: Marked Milestone 1 (Foundation) as DONE after docker startup, migrations, health check, and dockerized tests passed.
