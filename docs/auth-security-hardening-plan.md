# Auth and API security hardening plan

## Goal
Strengthen the current JWT-based identity model with a broader security pass before the platform is treated as a production-grade service.

## Current status
- JWT-based auth is implemented.
- API endpoints enforce user identity and membership checks.
- Input validation and payload limits are in place.
- The system does not yet include a full hardening pass for broader production security concerns.
- This is intentionally deferred for now because the current app is optimized for local validation and demo use.

## Why we are deferring it
The current app is intentionally minimal and straightforward. The security posture is adequate for a small, controlled deployment and for the existing test suite, but it is not a comprehensive production security design.

## Problem to solve
The app still has gaps in a real-world security model, including:
- token lifecycle and rotation controls
- stronger session management
- secret handling and rotation strategy
- broader audit and security event logging
- abuse protections beyond simple payload validation
- more explicit rejection of invalid or stale identities

## Proposed architecture
Add a layered security model around the current JWT pattern.

### 1) token lifecycle controls
- short-lived access tokens
- refresh token rotation
- explicit revocation and invalidation flow
- timeout and expiry monitoring

### 2) session and device controls
- track active sessions and last-used metadata
- allow logout and token invalidation
- detect abnormal auth patterns or reuse

### 3) secret and config hygiene
- rotate JWT secret material via environment-managed config
- separate internal signing keys from public-facing config
- avoid embedding secrets in source or local dev artifacts

### 4) API security hardening
- request signing or replay protection where needed
- CSRF protection for browser-based clients if used
- safe CORS and origin configuration for API deployment
- structured security event logging for failed auth and permission checks

### 5) auditability
Add security-specific logs for:
- rejected tokens
- invalid room access attempts
- failed membership checks
- suspicious duplicate or replayed requests
- admin actions, if enabled

## Implementation phases

### Phase 1: token lifecycle hardening
Strengthen access/refresh token handling and expiry policies.

### Phase 2: session control and revocation
Add active session tracking and logout/revocation paths.

### Phase 3: API and transport hardening
Review browser/API exposure, origin policy, and CORS boundaries.

### Phase 4: security operations readiness
Add logging, audit trails, and alerting for key auth events.

## Acceptance criteria
- Access tokens are short-lived and rotate safely.
- Invalid or expired tokens are rejected consistently and auditable.
- Users and admin actions are protected by explicit authorization checks.
- Security-relevant events are logged and reviewable.
- The deployment config supports secure secret handling and rotation.

## Relevant files
- services/api/app/auth/dependencies.py
- services/api/app/main.py
- services/api/app/api/users.py
- services/api/app/api/rooms.py
- services/api/app/api/messages.py
- docs/implementation-todo.md
- docs/rate-limiting-and-quotas-plan.md
