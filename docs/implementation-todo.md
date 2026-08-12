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
- Milestone 2 (Room and Auth APIs): DONE for the implemented auth/room/user-profile pieces.
- Milestone 3 (Realtime Messaging and History): DONE for the live room path and reconnect-safe history replay.
- Milestones 4-7: Planned follow-on work after the live room path is stabilized.

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
| P1-05 | Milestone 3 | Messaging | Implement MessageCreated realtime fanout from outbox | DONE | High | 2026-08-09 | MessageCreated fanout is implemented for connected room subscribers through the realtime gateway. |
| P1-06 | Milestone 3 | Messaging | Implement MessageUpdated realtime fanout from outbox | DONE | High | 2026-08-11 | MessageUpdated fanout is verified in the realtime unit tests and delivered to room subscribers. |
| P1-07 | Milestone 4 | Worker | Add robust retry policy and DLQ handling strategy | DONE | Medium | 2026-08-11 | The worker retries transient provider failures and dispatches permanent failures to the `translation.failed.q` dead-letter queue. |
| P1-08 | Milestone 4 | Worker | Improve translation provider abstraction (adapter interface) | DONE | Medium | 2026-08-11 | A provider abstraction is now implemented and exercised by unit tests, with configuration-driven provider/model selection and fallback handling. |
| P1-09 | Milestone 4 | Worker | Add fallback policy when translation unavailable | DONE | High | 2026-08-09 | translation_unavailable status is set in the current worker flow when translations fail. |
| P1-10 | Cross-cutting | Data | Add seed/dev bootstrap script for users/rooms/members | TODO | Medium | 2026-08-11 | Useful for local QA, but not required for the current live-room slice. |
| P1-11 | Milestone 7 | Analytics | Build room admin metrics summary endpoint | TODO | Medium | 2026-08-11 | The telemetry tables exist, but the analytics API and dashboards are still pending. |
| P1-16 | Milestone 2 | API | Add user onboarding endpoint for profile creation | DONE | High | 2026-08-09 | `/v1/users` creates or updates a user profile and persists preferred language. |
| P1-17 | Milestone 2 | Data | Add user-level preferred language migration | DONE | High | 2026-08-09 | Alembic migration `0002_add_user_preferred_lang` applied successfully in Docker. |
| P1-12 | Milestone 6 | Observability | Add structured logging and correlation ids | TODO | Medium | 2026-08-11 | Needed across api + worker + outbox publisher. |
| P1-13 | Milestone 6 | Observability | Add basic metrics for queue delay and translation latency | TODO | Medium | 2026-08-11 | Start with counters/histograms and dashboard stub. |
| P1-14 | Milestone 3 / 4 | Testing | Add integration test: send message -> queued -> translated | DONE | High | 2026-08-11 | A full send-message-to-translation-update flow test is included in the unit regression suite. |
| P1-15 | Milestone 6 | Security | Validate input limits and enforce payload size checks | TODO | Medium | 2026-08-11 | Prevent abuse and oversized requests. |
| P1-18 | Milestone 5 | History | Build room history API and reconnect replay | DONE | Medium | 2026-08-11 | The room history endpoint and reconnect-safe replay logic are implemented and validated in the live room flow. |

## Near-Term Execution Order

1. Keep the current live room flow as the baseline for chat behavior.
2. Focus on production hardening: metrics, structured logs, and input validation.
3. Complete the analytics layer for room admin metrics and cost visibility.
4. Extend the runtime for multi-instance fanout and operational resilience.

## Phase 4 Execution Focus

- P1-07: add retry and DLQ handling for translation worker failures.
- P1-08: extract a translation provider adapter so the worker logic is testable.
- P1-09: ensure translation_unavailable is surfaced cleanly when providers fail.
- P1-14: add an integration test for send message -> translation -> MessageUpdated.

## Change Log

- 2026-08-05: Initial tracker created.
- 2026-08-05: Marked Milestone 1 (Foundation) as DONE after docker startup, migrations, health check, and dockerized tests passed.
