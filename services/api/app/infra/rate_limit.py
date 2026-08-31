from dataclasses import dataclass

import redis
from fastapi import HTTPException, status

from services.api.app.infra.settings import settings
from shared.logging_utils import get_correlation_id, get_logger

logger = get_logger("prism.api.rate_limit")

_redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
    socket_connect_timeout=0.2,
    socket_timeout=0.2,
)


@dataclass
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class RateLimiter:
    """Redis-backed fixed-window rate limiter that fails open if Redis is unreachable."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        if not settings.rate_limit_enabled:
            return RateLimitDecision(allowed=True, limit=limit, remaining=limit, reset_seconds=window_seconds)

        try:
            pipe = self._client.pipeline()
            pipe.incr(key, 1)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if ttl is None or ttl < 0:
                self._client.expire(key, window_seconds)
                ttl = window_seconds
        except redis.exceptions.RedisError:
            logger.warning("rate_limit_backend_unavailable", extra={"rate_limit_key": key})
            return RateLimitDecision(allowed=True, limit=limit, remaining=limit, reset_seconds=window_seconds)

        remaining = max(limit - count, 0)
        allowed = count <= limit
        return RateLimitDecision(allowed=allowed, limit=limit, remaining=remaining, reset_seconds=ttl)

    def enforce(self, key: str, limit: int, window_seconds: int, *, scope: str) -> RateLimitDecision:
        decision = self.check(key, limit, window_seconds)
        if not decision.allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "rate_limit_key": key,
                    "rate_limit_scope": scope,
                    "correlation_id": get_correlation_id(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(decision.reset_seconds),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": str(decision.remaining),
                    "X-RateLimit-Reset": str(decision.reset_seconds),
                },
            )
        return decision


rate_limiter = RateLimiter(_redis_client)
