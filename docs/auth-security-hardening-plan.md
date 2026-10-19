# Authentication and API Security

## Status

Core authentication hardening is implemented. This page documents the current behavior and the
deployment settings that must be reviewed.

## Account and Password Flow

- The API provisions a built-in account with ID and username `admin` on startup if it does not
  already exist. Its default email is `admin@prism.local`.
- The initial password defaults to `password123`; set `ADMIN_INITIAL_PASSWORD` before first
  startup to use a unique value. The value is hashed with bcrypt before storage.
- A newly provisioned admin has `must_change_password` set. The initial password cannot obtain
  an application session: the admin must choose a different password before tokens are issued.
- The account is not reset on later startups. Changing `ADMIN_INITIAL_PASSWORD` does not change
  an existing account's password.
- Public registration reserves the username `admin`.
- Passwords must be 8-72 characters to match the bcrypt input limit.

Migration `0006_add_admin_password_rotation` adds the persisted password-rotation flag. Apply
all migrations before starting the API with this version.

## Registration, Email Verification and Abuse Controls

- New accounts are unverified. Registration sends a verification email (single-use token,
  24-hour expiry, only the SHA-256 is stored) and login returns 403 until the link is used.
  Verification links point at `/ui/verify#token=...` on `PUBLIC_BASE_URL`.
- Migration `0008_add_email_verification` adds `auth.accounts.email_verified_at` and
  `auth.email_verification_tokens`. Accounts that existed before the migration are marked
  verified; the built-in `admin` is created verified.
- `POST /v1/auth/resend-verification` always answers 202 and is limited to 5/hour per IP and
  per identifier. `POST /v1/auth/verify-email` is limited per IP.
- Registration requires a Cloudflare Turnstile token (`TURNSTILE_SECRET`, `TURNSTILE_HOSTNAMES`)
  and is limited to 5/hour and 20/day per IP and 50/hour per email domain
  (`REGISTRATION_IP_PER_HOUR`, `REGISTRATION_IP_PER_DAY`, `REGISTRATION_DOMAIN_PER_HOUR`).
- Login is limited per IP (`LOGIN_IP_LIMIT` per `LOGIN_IP_WINDOW_SECONDS`, default 20/15 min).
  After `LOGIN_LOCKOUT_THRESHOLD` (5) failures an identifier is locked with an exponentially
  growing delay (`LOGIN_LOCKOUT_BASE_SECONDS` 60 up to `LOGIN_LOCKOUT_MAX_SECONDS` 900); locked
  attempts get 429 even with the right password. Unknown usernames are counted and checked in
  constant time like real accounts. A success clears the counter. The same guard covers
  `/v1/auth/password/change`.
- Limiters share Redis and fail open if Redis is unavailable. `RATE_LIMIT_ENABLED=false`
  disables them.
- The registration service has no CORS by default (the browser reaches it through the same-origin
  proxy). Cross-origin use needs an explicit `CORS_ALLOWED_ORIGINS` list; `*` is never used.
- Client IPs come from `X-Forwarded-For` (Uvicorn `--proxy-headers`, trusted from any peer).
  Only the reverse proxy may be reachable by clients; do not publish the api or registration
  ports directly.
- Outgoing mail uses plain SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
  `SMTP_STARTTLS`, `SMTP_SENDER`). The Compose stack includes Mailpit, which accepts all mail on
  `mailpit:1025` and shows it at http://localhost:8025 (bound to localhost only).

## Browser Sessions

- Login and forced password change set `prism_access` and `prism_refresh` cookies. Cookies are
  `HttpOnly`, `Secure` by default, `SameSite=Lax`, and scoped to `/`.
- Login JSON does not contain tokens. Dashboard and room navigation do not pass tokens or user
  IDs in URLs. The server derives the signed-in identity from the access cookie.
- Browser REST calls send cookies same-origin. Refresh rotates the refresh token and updates
  both cookies; logout revokes the session and clears both cookies.
- WebSockets authenticate from the access cookie and reject unapproved `Origin` values. Tokens
  in query strings are not accepted.
- Non-browser clients can continue using `Authorization: Bearer`. Refresh-token JSON requests
  remain supported for these clients; query-string authentication is not supported.
- Cookie-authenticated state-changing requests validate `Origin` to mitigate CSRF. Keep the
  CORS/origin allowlist explicit; do not use wildcard origins with credentials.

## Authorization

- Global operational endpoints under `/v1/admin` require an authenticated user whose ID is in
  `ADMIN_USER_IDS`. The default allowlist is `admin`.
- Room metrics, membership changes, and room deletion use room-level admin membership checks;
  a global admin allowlist entry does not bypass room authorization.
- Users in `ADMIN_USER_IDS` can list and open every room read-only (role `observer` for rooms they
  are not members of): history, UI and WebSocket are allowed, but posting still requires membership.
- The bootstrap account ID is the literal `admin`, so deployments should retain that ID in
  `ADMIN_USER_IDS` unless they intentionally change their bootstrap configuration.

## Deployment Settings

- `ADMIN_INITIAL_PASSWORD`: initial password for the built-in account; change it before first
  startup in any exposed environment.
- `ADMIN_USER_IDS`: JSON list of globally authorized admin user IDs, for example
  `ADMIN_USER_IDS=["admin","user-id"]`.
- `CORS_ALLOWED_ORIGINS`: exact browser origins allowed to use the app. Include the public
  scheme and hostname, such as `https://chat.example.com`.
- `AUTH_COOKIE_SECURE`: defaults to `true`; use HTTPS for browser sessions.
- `JWT_SECRET`: use a strong, unique secret. The default `dev-secret` is warned about outside
  development.

Access tokens use short lifetimes and carry unique IDs. Redis tracks active sessions, token
revocation, refresh rotation, and reuse detection. Authentication and authorization failures
are recorded as structured security events and are visible through the protected operational
admin endpoints.