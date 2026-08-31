# Multi-instance fanout plan

## Goal
Allow realtime room events to fan out correctly when multiple API instances are running behind a load balancer.

## Current state
- The current WebSocket gateway is in-memory and intentionally single-instance.
- Redis is already available in the stack for this purpose.
- Multi-instance fanout is consciously deferred for now because the project is deliberately kept simple for local validation and demo use.
- This is a known future scaling path, not an active blocker for the current milestone.

## Problem to solve
Each API instance currently tracks its own socket set. A room message produced by one instance will not reach sockets connected to another instance, which matters only once the system is intentionally scaled beyond the current single-instance design.

## Proposed architecture
1. Use Redis pub/sub for room-level event channels.
2. Each API instance subscribes to room topics and broadcasts to local sockets.
3. The producer API publishes the event after DB commit and local fanout.
4. Keep room-scoped message semantics consistent across replicas.

## Tasks
1. Define channel naming: room:{room_id}:events
2. Add redis pub/sub listener in the API runtime.
3. Publish `MessageCreated` and `MessageUpdated` payloads to Redis.
4. Subscribe once per process and fan out locally to connected sockets.
5. Ensure duplicate suppression when the same process both publishes and receives its own event.
6. Add graceful reconnect behavior for the subscriber.

## Edge cases
- An instance that joins after a message is published should not replay stale events unless history replay is explicitly requested.
- Websocket disconnects and reconnect storms must not break the subscriber loop.
- Ensure a message is published only after persistence succeeds.

## Acceptance criteria
- Multiple API replicas can deliver events to the same room when the design is intentionally scaled.
- A message sent from one instance is visible on sockets connected to another instance.
- Fanout remains room-scoped and does not leak across rooms.
- Local in-memory broadcast remains as the current simple fallback for single-instance environments and demos.

## Relevant code
- services/api/app/realtime/websocket_gateway.py
- services/api/app/api/messages.py
- services/worker/app/tasks/translation.py
- docs/implementation-plan.md
