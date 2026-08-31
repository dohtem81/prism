# Dev tooling bootstrap plan

## Goal
Create a fast local QA path for users, rooms, members, and message flows without manual database setup each time.

## Current state
- Core API flow works, but there is no seed script for realistic local exploration.
- This is tracked as a follow-up task in the implementation tracker.

## Scope
- Seed users with preferred languages
- Create rooms and memberships
- Add members with admin/participant roles
- Optionally insert example messages and translation payloads

## Proposed script
- CLI script under scripts/ or tools/
- Accept environment target (local/dev)
- Support dry-run mode and idempotent inserts

## Tasks
1. Add a bootstrap script with explicit user creation data.
2. Create sample rooms and membership combinations.
3. Add room-level translation preferences.
4. Optionally generate message history for demo replay testing.
5. Log the created ids and credentials for quick testing.

## Example outputs
- user_1 / user_2 / user_3
- room_alpha / room_beta
- membership assignment and preferred language by user

## Acceptance criteria
- A developer can run one command to create a realistic local dataset.
- The seeded data is repeatable and safe to re-run.
- Room flows and message history can be exercised through the app without manual setup.

## Relevant code
- services/api/app/api/users.py
- services/api/app/api/rooms.py
- shared/db/models.py
- docs/implementation-todo.md
