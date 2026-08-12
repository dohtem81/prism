# Chat Translation Platform - Implementation Docs

This documentation set describes the architecture and implementation contracts for a real-time chat application with server-side LLM translation.

## Document Map

1. [Architecture Overview](architecture-overview.md)
2. [Components and Responsibilities](components-and-responsibilities.md)
3. [Data Flow and Contracts](data-flow-and-contracts.md)
4. [Technology Decisions and Trade-offs](technology-decisions.md)
5. [Implementation Plan](implementation-plan.md)
6. [Implementation TODO Tracker](implementation-todo.md)

## Scope

- real-time communication using WebSockets for connected clients
- room-based chat with membership management
- original message broadcast first, translation appended later
- live room dashboard for local testing and QA
- Docker-based local development and deployment baseline

## Current implementation focus

The codebase currently supports the live messaging path, room replay, and message enrichment flow.

Implemented:

- REST API for users, rooms, and message send flow
- WebSocket room fanout for MessageCreated and MessageUpdated events
- room history fetch and reconnect-safe replay of recent messages
- PostgreSQL persistence for rooms, members, messages, translations, and room events
- Celery worker translation pipeline with provider abstraction and retries
- browser dashboard for room-level QA

Planned / not yet implemented:

- admin analytics and metrics surfaces
- multi-instance Redis pub/sub fanout
- structured observability and production hardening

## Non-Goals for MVP

- End-to-end encryption.
- Multi-region active-active deployment.
- Exactly-once delivery semantics.
- Unlimited language support.
