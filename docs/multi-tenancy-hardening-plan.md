# Multi-tenancy hardening plan

## Goal
Add explicit tenant isolation and authorization boundaries so the app can safely support multiple logical tenants or client organizations without relying on implicit trust.

## Current status
- User identity is based on JWT auth.
- Rooms and users are persisted in a shared data model.
- There is no tenant model, no field-level or policy-level tenant boundaries, and no explicit isolation mechanism beyond basic auth and room membership.
- This is intentionally deferred because the current app is a single-tenant demo environment and not yet operating as a multi-tenant platform.

## Why we are deferring it
The system is currently designed around a simple room-based model where users are part of a shared deployment. That is adequate for local validation and product demos, but it becomes unsafe and confusing once multiple client organizations or isolated customer groups share the same deployment.

## Problem to solve
Without a proper tenant model, data can be accidentally exposed across organizations, especially when:
- room IDs are reused across customer contexts,
- user identity is not scoped to a tenant,
- admin actions are not restricted by tenant boundaries,
- object-level authorization is not enforced consistently.

## Proposed architecture
Introduce a clear tenant boundary at the data layer and authorization layer.

### 1) Tenant model
Add a tenant entity that owns:
- users
- rooms
- room membership
- provider or configuration metadata
- admin permissions and quotas

### 2) Query scoping
Every read/write path should be tenant-scoped, especially on:
- room access
- user lookups
- message queries
- admin metrics endpoints
- translation or notification jobs

### 3) Authorization checks
Require an explicit check that the current user belongs to the target tenant and has the necessary role before:
- creating rooms
- inviting members
- reading history
- viewing metrics
- performing admin actions

### 4) Data isolation rules
Apply tenant boundaries to:
- database row filtering
- Redis keys
- websocket room topic scope
- future event bus namespaces

## Implementation phases

### Phase 1: tenant entity and migration
Add the tenant table and migration, then attach each user and room to a tenant.

### Phase 2: authorization and query filtering
Scope all room and message access checks by tenant.

### Phase 3: admin isolation
Ensure admin endpoints only return tenant-local data and only for authorized users.

### Phase 4: policy enforcement
Introduce role-based access and default-deny checks for multi-tenant operations.

## Acceptance criteria
- There is an explicit tenant on every user and room record.
- A user cannot access another tenant’s rooms or metrics.
- Redis keys and websocket room channels are tenant-scoped properly.
- Admin APIs enforce tenant and role boundaries.

## Relevant files
- shared/db/models.py
- services/api/app/auth/dependencies.py
- services/api/app/api/rooms.py
- services/api/app/api/users.py
- services/api/app/api/messages.py
- docs/implementation-todo.md
