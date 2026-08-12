# Prism — Documentation

Real-time multilingual chat platform with server-side LLM translation.

## Demo

Full working flow — messages sent and translated in real time:

![Working app demo](imgs/prim_demo.gif)

Degraded state — translation provider unavailable, original message delivery unaffected:

![LLM unavailable demo](imgs/prims_llm_not%20avaliable.gif)

## Documents

| Document | Purpose |
|---|---|
| [Architecture Overview](architecture-overview.md) | System topology, state ownership, and degraded-mode behavior |
| [Components and Responsibilities](components-and-responsibilities.md) | Component contracts and boundaries |
| [Data Flow and Contracts](data-flow-and-contracts.md) | Message lifecycle, event schemas, REST and queue contracts |
| [Technology Decisions](technology-decisions.md) | Stack rationale and trade-offs |
| [Implementation Plan](implementation-plan.md) | Milestone breakdown with verification evidence |
| [Implementation TODO](implementation-todo.md) | Current task status and near-term execution order |

## Scope

- Room-based real-time chat with WebSocket delivery
- Original message broadcast first, translation delivered as an async enrichment
- Per-user language preference — each member receives translations in their preferred language
- Provider abstraction with configurable model and fallback
- Browser dashboard for manual QA and live room verification
- Docker-based local development and deployment

## What is implemented

| Feature | Status |
|---|---|
| User profile and language preference API | Done |
| Room creation and membership management API | Done |
| Message send, persist, and fan-out | Done |
| WebSocket room subscriptions and live delivery | Done |
| Room history fetch and reconnect-safe replay | Done |
| Celery translation worker with provider abstraction | Done |
| MessageUpdated broadcast with translation patches | Done |
| Dead-letter handling for provider failures | Done |
| Browser QA dashboard | Done |
| Admin analytics and room metrics API | Pending |
| Multi-instance Redis pub/sub fanout | Pending |
| Structured observability and correlation IDs | Pending |

## Secrets and environment

Only `.env.example` is tracked in this repository. A real `.env` file is local-only and must never be committed.

```bash
cp .env.example .env
# Add provider API keys and any local overrides
```

## Out of scope for current phase

- End-to-end encryption
- Multi-region active-active deployment
- Exactly-once delivery semantics
- Unlimited language support
