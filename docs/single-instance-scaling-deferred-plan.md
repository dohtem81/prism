# Single-instance scaling deferred plan

## Goal
Document the scaling limitation and the planned path for multi-instance fanout without treating it as a required implementation for the current milestone.

## Current status
- The system is intentionally single-instance for the current implementation.
- Redis is already present in the stack and is the correct future scaling primitive for cross-instance fanout.
- The current app is designed for simplicity, local testing, and demo use.
- We are aware of the problem if the system is scaled horizontally behind a load balancer.

## Why we are deferring it
We do not need multi-instance fanout right now because:
- the application is still operating in a single-node development and demo configuration;
- the current goal is to keep the runtime simple and predictable;
- the architecture remains easy to validate and test without replica coordination;
- the problem is known and already identified as a future expansion item.

This is not an accidental omission. It is a conscious product decision to prioritize simplicity and rapid validation over horizontal scaling today.

## Known limitation
If multiple API instances are deployed behind a load balancer, each instance will only know about its own in-memory WebSocket connections. A message published on one instance will not automatically reach sockets connected to another instance unless a cross-instance delivery mechanism is added.

## Planned future approach
When scaling becomes necessary, the planned model is:
1. Keep PostgreSQL as the source of truth for persisted room state.
2. Publish room events to Redis channels such as `room:{room_id}:events`.
3. Each API instance subscribes to room channels and fans out only to locally connected sockets.
4. Preserve room-scoped event semantics and avoid duplicate local fanout.
5. Add reconnect logic, health checks, and deduplication rules for subscriber reliability.

## Expected path when we do scale
- Phase A: local single-instance app remains the default for demos and tests.
- Phase B: Redis pub/sub fanout is introduced behind the existing realtime gateway.
- Phase C: add multi-instance validation tests and replica startup checks.
- Phase D: scale API instances behind a load balancer with room fanout staying consistent.

## Acceptance criteria for eventual scaling
- Multiple API replicas can deliver a room event to the same room.
- A message sent from one instance is visible on sockets connected to another instance.
- No duplicate deliveries are introduced by the room fanout mechanism.
- The single-instance app remains operational and simple for local testing.

## Relevant files
- services/api/app/realtime/websocket_gateway.py
- services/api/app/api/messages.py
- services/worker/app/tasks/translation.py
- docs/multi-instance-fanout-plan.md
- docs/implementation-todo.md
