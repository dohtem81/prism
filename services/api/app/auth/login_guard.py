from fastapi import Request

from services.api.app.infra.rate_limit import rate_limiter
from services.api.app.infra.settings import settings
from shared import abuse_guard
from shared.db.models import RegisteredAccount
from shared.security import hash_password, verify_password

_dummy_hash: str | None = None


def get_client():
    return rate_limiter.client


def enforce_attempt_allowed(request: Request, identifier: str) -> None:
    """Reject before any password check when the IP is over its budget or the account is locked."""
    if not settings.rate_limit_enabled:
        return
    client = get_client()
    ip = abuse_guard.client_ip(request)
    abuse_guard.enforce(
        client, f"rl:login:ip:{ip}", settings.login_ip_limit, settings.login_ip_window_seconds, scope="login_ip"
    )
    remaining = abuse_guard.lockout_remaining(client, identifier)
    if remaining:
        raise abuse_guard.too_many_requests(remaining, "Too many failed attempts. Try again later.")


def enforce_budget(request: Request, scope: str, limit: int, window_seconds: int, identifier: str | None = None) -> None:
    """Per-IP (and optionally per-identifier) fixed-window limit for non-login auth endpoints."""
    if not settings.rate_limit_enabled:
        return
    client = get_client()
    abuse_guard.enforce(client, f"rl:{scope}:ip:{abuse_guard.client_ip(request)}", limit, window_seconds, scope=scope)
    if identifier:
        abuse_guard.enforce(
            client, f"rl:{scope}:id:{abuse_guard.digest(identifier)}", limit, window_seconds, scope=scope
        )


def credentials_valid(account: RegisteredAccount | None, password: str, verify=verify_password) -> bool:
    """Always runs one bcrypt check so unknown accounts take as long as real ones."""
    global _dummy_hash
    if account is None:
        if _dummy_hash is None:
            _dummy_hash = hash_password("prism-dummy-password")
        verify(password, _dummy_hash)
        return False
    return verify(password, account.password_hash)


def record_failure(identifier: str) -> None:
    if not settings.rate_limit_enabled:
        return
    abuse_guard.record_failure(
        get_client(),
        identifier,
        threshold=settings.login_lockout_threshold,
        base_seconds=settings.login_lockout_base_seconds,
        max_seconds=settings.login_lockout_max_seconds,
        window_seconds=settings.login_failure_window_seconds,
    )


def record_success(identifier: str) -> None:
    abuse_guard.clear_failures(get_client(), identifier)
