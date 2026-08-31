# Auth and API security hardening plan

## Goal
Strengthen the current JWT-based identity model with a broader security pass before the platform is treated as a production-grade service.

## Current status
- JWT-based auth is implemented (`services/api/app/auth/dependencies.py`).
- API endpoints enforce user identity and membership checks.
- Input validation, payload limits, and rate limiting/quotas are in place (see `docs/rate-limiting-and-quotas-plan.md`).
- Structured logging, correlation IDs, and lightweight distributed tracing are in place (see `docs/distributed-tracing-plan.md`).
- The system does not yet include a full hardening pass for token lifecycle, session control, or transport/config hygiene.
- This is intentionally deferred for now because the current app is optimized for local validation and demo use.

## Why we are deferring it
The current app is intentionally minimal and straightforward. The security posture is adequate for a small, controlled deployment and for the existing test suite, but it is not a comprehensive production security design.

## Concrete gaps in the current implementation
These are specific, verified gaps in `services/api/app/auth/dependencies.py` and `services/api/app/main.py`, not general concerns:
- `resolve_authenticated_user_id` accepts a hardcoded `"dev-token"` literal that resolves to `"dev-user"` **regardless of environment** — this is a backdoor if ever deployed with `APP_ENV=prod` (or any real environment) and `settings.app_env` is never checked.
- Access tokens are valid for 8 hours (`create_access_token`), have no `jti`, and cannot be revoked — a leaked token stays valid until natural expiry with no way to invalidate it.
- There is no refresh token flow — clients hold one long-lived token instead of a short-lived access token + rotating refresh token.
- `settings.jwt_secret` defaults to `"dev-secret"` and there is no startup check preventing that default from being used outside local dev.
- `services/api/app/main.py` has no CORS middleware configured at all — any browser-based client behavior depends on browser defaults rather than an explicit, reviewed origin policy.
- Auth failures (`401`/`403` from `get_current_user_id`, membership checks) are not logged as security events — they raise and return, but nothing records them for audit or abuse detection, unlike the rate-limit violation tracking already built in `services/api/app/infra/rate_limit.py`.

## Proposed architecture
Add a layered security model around the current JWT pattern, reusing infra already proven in this codebase (Redis via `rate_limit.py`, structured logging via `shared/logging_utils.py`, tracing via `shared/tracing.py`).

### 1) token lifecycle controls
- short-lived access tokens (minutes, not hours)
- refresh token issuance + rotation
- explicit revocation via a Redis-backed denylist keyed by token `jti`
- timeout and expiry monitoring

### 2) session and device controls
- track active sessions (issued_at, last_used_at) in Redis, keyed by user + `jti`
- add a logout endpoint that revokes the current session/refresh token
- detect refresh-token reuse (a rotated-out token used again) and revoke all sessions for that user

### 3) secret and config hygiene
- fail startup (or loudly warn) if `jwt_secret` is left at its default outside local dev
- document JWT secret rotation via environment-managed config
- explicit `app_env` gate around any dev-only auth bypass (`dev-token`)

### 4) API security hardening
- explicit CORS configuration (`allow_origins` from settings, no wildcard-with-credentials)
- CSRF protection only if/when cookie-based auth is introduced (not needed for the current bearer-token-only model — tracked as conditional, not required now)
- structured security event logging for failed auth and permission checks, reusing the existing `rl:violations:*` Redis-hash pattern from `rate_limit.py`

### 5) auditability
Add security-specific logs/counters for:
- rejected tokens (expired, malformed, revoked)
- invalid room access attempts
- failed membership checks
- refresh-token reuse detection
- admin actions, if/when introduced

## Implementation phases

### Phase 1: close known gaps (quick wins, low risk)
Scope: `services/api/app/auth/dependencies.py`, `services/api/app/infra/settings.py`, `services/api/app/main.py`
- Gate the `"dev-token"` bypass behind `settings.app_env == "dev"` so it cannot resolve an identity in any other environment.
- Add a startup check/log warning if `jwt_secret` equals the default `"dev-secret"` while `app_env != "dev"`.
- Add explicit CORS middleware with an allow-list driven by a new `cors_allowed_origins` setting (default `["http://localhost:8000"]` for local dev).
- Shorten the default access token lifetime (e.g. 8h → 30m) via a new `access_token_ttl_minutes` setting.

### Phase 2: token lifecycle hardening
Scope: new `services/api/app/auth/token_store.py` (Redis-backed, mirrors the pattern in `infra/rate_limit.py`), `auth/dependencies.py`
- Add a `jti` (unique token id) and `iat` claim to every issued access token.
- Add a refresh token type (longer-lived, single-use) with rotation on each use.
- Add a Redis denylist (`auth:revoked:{jti}`) checked during token validation; fail open (log + allow) only for the rate-limit path, but fail **closed** (reject) here since this is a security control, not a capacity control.
- Add a `POST /v1/auth/refresh` endpoint and a `POST /v1/auth/logout` endpoint that revokes the current session.

### Phase 3: session and device visibility
Scope: `token_store.py`, new `GET /v1/admin/auth/sessions` admin endpoint (mirrors `GET /v1/admin/rate-limits/violations`)
- Track last-used metadata per session in Redis.
- Detect and log refresh-token reuse; revoke all sessions for the affected user on detection.
- Expose active session counts / recent revocations for operator visibility.

### Phase 4: transport hardening and auditability
Scope: `main.py`, `shared/logging_utils.py` or a small `security_events.py` helper
- Finalize CORS/origin policy for the deployment target.
- Log structured security events (`auth_rejected`, `membership_denied`, `token_reused`) with correlation ID and trace context, following the existing logging conventions.
- Track violation counts in Redis hashes (same approach as `rate_limiter.record_violation`) so they can be surfaced through the admin API alongside rate-limit violations.

## Acceptance criteria
- The `dev-token` bypass cannot authenticate outside `app_env == "dev"`.
- Access tokens are short-lived (≤30m) and refresh tokens rotate safely.
- A revoked or reused token is rejected immediately, even if not yet expired.
- CORS is explicitly configured — no implicit/default-open origin behavior.
- Security-relevant events (rejected tokens, denied membership checks, token reuse) are logged and countable via the admin API.
- The deployment config supports secure secret handling and flags insecure defaults outside dev.

## Relevant files
- services/api/app/auth/dependencies.py
- services/api/app/infra/settings.py
- services/api/app/infra/rate_limit.py (pattern reference for Redis-backed state + violation tracking)
- services/api/app/main.py
- services/api/app/api/users.py
- services/api/app/api/rooms.py
- services/api/app/api/messages.py
- services/api/app/api/admin.py
- docs/implementation-todo.md
- docs/rate-limiting-and-quotas-plan.md

