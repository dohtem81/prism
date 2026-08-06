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

Phase summary:

- Milestone 1 (Foundation): DONE

| ID | Area | Task | Status | Priority | Last Updated | Notes |
|---|---|---|---|---|---|---|
| P1-01 | Foundation | Finalize Docker local run flow (api/worker/postgres/rabbitmq/redis) | DONE | High | 2026-08-05 | Compose and Dockerfiles scaffolded. |
| P1-02 | Foundation | Validate migrations end-to-end in running environment | DONE | High | 2026-08-05 | Verified via Docker: alembic upgrade head against compose postgres. |
| P1-03 | API | Replace temporary X-User-Id auth with JWT auth | TODO | High | 2026-08-05 | Header-based auth is interim only. |
| P1-04 | API | Add room creation and membership endpoints | TODO | High | 2026-08-05 | Needed for end-to-end manual testing without direct DB writes. |
| P1-05 | Messaging | Implement MessageCreated realtime fanout from outbox | TODO | High | 2026-08-05 | Outbox writes exist; publisher/fanout loop still needed. |
| P1-06 | Messaging | Implement MessageUpdated realtime fanout from outbox | TODO | High | 2026-08-05 | Worker writes outbox event; publish pipeline pending. |
| P1-07 | Worker | Add robust retry policy and DLQ handling strategy | TODO | Medium | 2026-08-05 | Configure Celery retry/backoff and failed-task observability. |
| P1-08 | Worker | Improve translation provider abstraction (adapter interface) | TODO | Medium | 2026-08-05 | OpenAI call is inline; extract adapter for testability. |
| P1-09 | Worker | Add fallback policy when translation unavailable | IN_PROGRESS | High | 2026-08-05 | translation_unavailable status already set; add retry/circuit logic. |
| P1-10 | Data | Add seed/dev bootstrap script for users/rooms/members | TODO | Medium | 2026-08-05 | Speeds local QA and API testing. |
| P1-11 | Analytics | Build room admin metrics summary endpoint | TODO | Medium | 2026-08-05 | Contract exists in docs, implementation pending. |
| P1-12 | Observability | Add structured logging and correlation ids | TODO | Medium | 2026-08-05 | Needed across api + worker + outbox publisher. |
| P1-13 | Observability | Add basic metrics for queue delay and translation latency | TODO | Medium | 2026-08-05 | Start with counters/histograms and dashboard stub. |
| P1-14 | Testing | Add integration test: send message -> queued -> translated | TODO | High | 2026-08-05 | Cover idempotency and translation_unavailable path. |
| P1-15 | Security | Validate input limits and enforce payload size checks | TODO | Medium | 2026-08-05 | Prevent abuse and oversized requests. |

## Near-Term Execution Order

1. P1-04 Add room/membership endpoints.
2. P1-05 and P1-06 Build outbox publisher + websocket fanout.
3. P1-14 Add integration test for core message flow.
4. P1-03 Replace temp auth with JWT.

## Change Log

- 2026-08-05: Initial tracker created.
- 2026-08-05: Marked Milestone 1 (Foundation) as DONE after docker startup, migrations, health check, and dockerized tests passed.
