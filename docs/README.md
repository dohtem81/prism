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

- Real-time communication using WebSockets.
- Room-based chat with membership management.
- Original message broadcast first, translation appended later.
- Message history persistence and replay.
- Docker-based local development and deployment baseline.

## Non-Goals for MVP

- End-to-end encryption.
- Multi-region active-active deployment.
- Exactly-once delivery semantics.
- Unlimited language support.
