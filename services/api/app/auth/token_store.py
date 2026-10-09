import json

import redis

from services.api.app.infra.settings import settings
from shared.logging_utils import get_logger

logger = get_logger("prism.api.token_store")

REVOKED_PREFIX = "auth:revoked:"
REFRESH_PREFIX = "auth:refresh:"


class TokenStoreUnavailable(Exception):
    """Redis could not be reached; security checks must fail closed."""


class RefreshState:
    OK = "ok"
    REUSED = "reused"
    UNKNOWN = "unknown"


class TokenStore:
    """Redis-backed denylist for access tokens and single-use registry for refresh tokens."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        """Deny a jti until the token would have expired anyway."""
        try:
            self._client.set(f"{REVOKED_PREFIX}{jti}", "1", ex=max(int(ttl_seconds), 1))
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "revoke"})
            raise TokenStoreUnavailable from exc

    def is_revoked(self, jti: str) -> bool:
        try:
            return bool(self._client.exists(f"{REVOKED_PREFIX}{jti}"))
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "is_revoked"})
            raise TokenStoreUnavailable from exc

    def store_refresh(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        key = f"{REFRESH_PREFIX}{jti}"
        try:
            pipe = self._client.pipeline()
            pipe.hset(key, mapping={"user_id": user_id})
            pipe.expire(key, max(int(ttl_seconds), 1))
            pipe.execute()
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "store_refresh"})
            raise TokenStoreUnavailable from exc

    def consume_refresh(self, jti: str) -> tuple[str, str | None]:
        """Mark a refresh token as used. Returns (state, user_id); only the first call returns OK."""
        key = f"{REFRESH_PREFIX}{jti}"
        try:
            data = self._client.hgetall(key)
            if not data:
                return RefreshState.UNKNOWN, None
            # HSETNX is the atomic gate: exactly one caller wins the rotation.
            if not self._client.hsetnx(key, "rotated", "1"):
                return RefreshState.REUSED, data.get("user_id")
            return RefreshState.OK, data.get("user_id")
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "consume_refresh"})
            raise TokenStoreUnavailable from exc

    def invalidate_refresh(self, jti: str) -> None:
        """Make a still-unused refresh token unusable (e.g. on logout)."""
        key = f"{REFRESH_PREFIX}{jti}"
        try:
            if self._client.exists(key):
                self._client.hsetnx(key, "rotated", "1")
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "invalidate_refresh"})
            raise TokenStoreUnavailable from exc


_redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
    socket_connect_timeout=settings.token_store_redis_timeout_seconds,
    socket_timeout=settings.token_store_redis_timeout_seconds,
)

token_store = TokenStore(_redis_client)
