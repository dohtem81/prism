"""Redis-backed abuse controls shared by the API and registration services; all helpers fail open if Redis is down."""

import hashlib

import redis
from fastapi import HTTPException, Request, status

from shared.logging_utils import get_logger

logger = get_logger("prism.abuse_guard")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def digest(value: str) -> str:
    """Stable key fragment so identifiers (emails, usernames) never appear in Redis keys."""
    return hashlib.sha256(value.strip().casefold().encode()).hexdigest()[:32]


def too_many_requests(retry_after: int, detail: str = "Too many attempts. Try again later.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(int(retry_after), 1))},
    )


def hit(client: redis.Redis, key: str, limit: int, window_seconds: int) -> int | None:
    """Count one event in a fixed window; returns seconds to wait if the limit is exceeded, else None."""
    try:
        count = int(client.incr(key))
        ttl = client.ttl(key)
        if ttl is None or ttl < 0:
            client.expire(key, window_seconds)
            ttl = window_seconds
    except redis.exceptions.RedisError:
        logger.warning("abuse_guard_backend_unavailable", extra={"rate_limit_key": key})
        return None
    return None if count <= limit else int(ttl)


def enforce(client: redis.Redis, key: str, limit: int, window_seconds: int, *, scope: str) -> None:
    retry_after = hit(client, key, limit, window_seconds)
    if retry_after is not None:
        logger.warning("abuse_limit_exceeded", extra={"rate_limit_scope": scope})
        raise too_many_requests(retry_after)


def lockout_remaining(client: redis.Redis, identifier: str) -> int:
    """Seconds left on an active lockout for this identifier (0 when not locked)."""
    try:
        key = f"lockout:lock:{digest(identifier)}"
        if not client.exists(key):
            return 0
        return max(int(client.ttl(key)), 1)
    except redis.exceptions.RedisError:
        return 0


def record_failure(
    client: redis.Redis,
    identifier: str,
    *,
    threshold: int,
    base_seconds: int,
    max_seconds: int,
    window_seconds: int,
) -> None:
    """Count a failed attempt; from `threshold` failures on, lock with exponentially growing delay."""
    try:
        ident = digest(identifier)
        fail_key = f"lockout:fail:{ident}"
        failures = int(client.incr(fail_key))
        if client.ttl(fail_key) < 0:
            client.expire(fail_key, window_seconds)
        if failures >= threshold:
            duration = min(base_seconds * 2 ** (failures - threshold), max_seconds)
            client.set(f"lockout:lock:{ident}", "1", ex=duration)
            logger.warning("account_lockout_started", extra={"lockout_seconds": duration})
    except redis.exceptions.RedisError:
        logger.warning("abuse_guard_backend_unavailable", extra={"rate_limit_scope": "lockout"})


def clear_failures(client: redis.Redis, identifier: str) -> None:
    try:
        ident = digest(identifier)
        client.delete(f"lockout:fail:{ident}")
        client.delete(f"lockout:lock:{ident}")
    except redis.exceptions.RedisError:
        pass
