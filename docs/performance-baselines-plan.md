# Performance baselines plan

## Goal
Create a repeatable way to measure load, latency, and stability before the project is treated as a real traffic-facing service.

## Current status
- App functions and tests are validated in Docker.
- Basic telemetry exists for queue delay and translation latency.
- There is no benchmark suite, no realistic load harness, and no dataset showing system behavior under pressure.
- This is intentionally deferred because the app is still a small, local, demo-friendly system.

## Why we are deferring it
Load testing is most useful once the system is operating under realistic traffic patterns, higher concurrency, or public-facing usage. For the current milestone, the priority is correctness and demo readiness, not performance tuning for unknown workloads.

## Problem to solve
Without benchmarks, the team cannot answer:
- what is the p95 latency for message send?
- how does translation backlog grow under load?
- what happens when multiple users join the same room?
- how does the worker recover from bursts or temporary provider slowness?

## Proposed approach
Create a lightweight benchmark/reporting workflow that runs in Docker and produces comparable operating data.

### 1) Benchmark categories
Measure these scenarios:
- room creation and membership updates
- message send throughput under a small concurrency burst
- websocket connection fanout for room subscribers
- translation job enqueue and completion time
- reconnect and history replay behavior

### 2) Metrics to capture
At minimum, collect:
- end-to-end message latency
- API request latency by endpoint
- queue age and worker processing time
- room fanout fan-in/fan-out ratios
- number of active websocket connections
- database query timing for hot paths

### 3) Test harness
Use a Dockerized runner to execute:
- a fixed synthetic load against the API,
- coordinated message sends across multiple rooms,
- a translation worker burst,
- reconnect and history replay validation.

### 4) Output format
Store outputs as:
- summary CSV or JSON
- trend chart or markdown report
- per-run comparison against prior baselines

### 5) Operational trigger
Once traffic or concurrency starts to matter, this becomes a required validation step before rolling out changes that affect messaging or translation throughput.

## Implementation phases

### Phase 1: capture baseline metrics in a simple harness
Measure a single test scenario repeatedly to build a stable initial baseline.

### Phase 2: add concurrency scenarios
Increase users, rooms, and parallel message sends to understand scaling limits.

### Phase 3: translate into alerts and capacity guardrails
Set thresholds for queue age, API latency, and translation backlog.

### Phase 4: integrate into release checks
Run benchmark or smoke-load checks before a release when the system is expected to handle more traffic.

## Acceptance criteria
- The project has a repeatable benchmark command for the current stack.
- Load tests produce latency and throughput numbers with a clear format.
- The team can compare warm-up, steady-state, and failure-mode behavior.
- Capacity concerns are documented before the app becomes a public or production-grade workload.

## Relevant files
- deploy/compose/docker-compose.yml
- services/api/app/main.py
- services/api/app/realtime/websocket_gateway.py
- services/worker/app/tasks/translation.py
- shared/db/models.py
- docs/implementation-todo.md
