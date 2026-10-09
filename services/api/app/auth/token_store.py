import json
from datetime import datetime, timezone

import redis

from services.api.app.infra.settings import settings
from shared.logging_utils import get_logger

logger = get_logger("prism.api.token_store")

REVOKED_PREFIX = "auth:revoked:"
REFRESH_PREFIX = "auth:refresh:"
SESSION_PREFIX = "auth:session:"
REVOCATIONS_KEY = "auth:revocations"
MAX_RECENT_REVOCATIONS = 100


class TokenStoreUnavailable(Exception):
    """Redis could not be reached; security checks must fail closed."""


class RefreshState:
    OK = "ok"
    REUSED = "reused"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_key(user_id: str, jti: str) -> str:
    return f"{SESSION_PREFIX}{user_id}:{jti}"


class TokenStore:
    """Redis-backed denylist, single-use refresh registry, and active-session tracking."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    # --- denylist -------------------------------------------------------------------------

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

    # --- refresh tokens -------------------------------------------------------------------

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
            if data.get("revoked"):
                return RefreshState.REVOKED, data.get("user_id")
            # HSETNX is the atomic gate: exactly one caller wins the rotation.
            if not self._client.hsetnx(key, "rotated", "1"):
                return RefreshState.REUSED, data.get("user_id")
            return RefreshState.OK, data.get("user_id")
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "consume_refresh"})
            raise TokenStoreUnavailable from exc

    def invalidate_refresh(self, jti: str) -> None:
        """Make a still-unused refresh token unusable (logout / session revocation); not a reuse signal."""
        key = f"{REFRESH_PREFIX}{jti}"
        try:
            if self._client.exists(key):
                self._client.hsetnx(key, "revoked", "1")
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "invalidate_refresh"})
            raise TokenStoreUnavailable from exc

    # --- sessions -------------------------------------------------------------------------

    def create_session(
        self, user_id: str, jti: str, token_type: str, ttl_seconds: int, refresh_jti: str | None = None
    ) -> None:
        """Record an issued token. `refresh_jti` links an access token to the refresh token issued with it."""
        key = _session_key(user_id, jti)
        now = _now()
        mapping = {"issued_at": now, "last_used_at": now, "token_type": token_type}
        if refresh_jti:
            mapping["refresh_jti"] = refresh_jti
        try:
            pipe = self._client.pipeline()
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, max(int(ttl_seconds), 1))
            pipe.execute()
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "create_session"})
            raise TokenStoreUnavailable from exc

    def touch_session(self, user_id: str, jti: str) -> None:
        """Update last_used_at. Fails open: the token was already validated, this is bookkeeping."""
        key = _session_key(user_id, jti)
        try:
            if self._client.exists(key):
                self._client.hset(key, "last_used_at", _now())
        except redis.exceptions.RedisError:
            logger.warning("session_touch_unavailable")

    def get_session(self, user_id: str, jti: str) -> dict[str, str] | None:
        try:
            data = self._client.hgetall(_session_key(user_id, jti))
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "get_session"})
            raise TokenStoreUnavailable from exc
        return dict(data) if data else None

    def end_session(self, user_id: str, jti: str) -> None:
        try:
            self._client.delete(_session_key(user_id, jti))
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "end_session"})
            raise TokenStoreUnavailable from exc

    def _session_keys(self, user_id: str) -> list[str]:
        prefix = f"{SESSION_PREFIX}{user_id}:"
        return [key for key in self._client.scan_iter(match=f"{prefix}*") if key.startswith(prefix)]

    def list_active_sessions(self, user_id: str) -> list[dict[str, str]]:
        try:
            sessions = []
            for key in self._session_keys(user_id):
                data = self._client.hgetall(key)
                if data:
                    sessions.append({"jti": key.rsplit(":", 1)[1], **data})
            return sessions
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "list_active_sessions"})
            raise TokenStoreUnavailable from exc

    def count_active_sessions(self, user_id: str) -> int:
        """Sessions are counted by refresh tokens: one live refresh token per login."""
        return sum(1 for session in self.list_active_sessions(user_id) if session.get("token_type") == "refresh")

    def revoke_all_sessions(self, user_id: str, reason: str) -> int:
        """Deny every token the user holds: access jtis go on the denylist, refresh tokens are invalidated."""
        revoked = 0
        try:
            for key in self._session_keys(user_id):
                data = self._client.hgetall(key)
                jti = key.rsplit(":", 1)[1]
                if data.get("token_type") == "refresh":
                    self.invalidate_refresh(jti)
                else:
                    self.revoke(jti, max(int(self._client.ttl(key)), 1))
                self._client.delete(key)
                revoked += 1
        except redis.exceptions.RedisError as exc:
            logger.error("token_store_unavailable", extra={"operation": "revoke_all_sessions"})
            raise TokenStoreUnavailable from exc

        self.record_revocation(user_id, reason, revoked)
        return revoked

    # --- revocation history and admin overview --------------------------------------------

    def record_revocation(self, user_id: str, reason: str, sessions_revoked: int) -> None:
        """Keep a short list of recent revocations for operators; fails open."""
        entry = json.dumps(
            {"timestamp": _now(), "user_id": user_id, "reason": reason, "sessions_revoked": sessions_revoked}
        )
        try:
            self._client.lpush(REVOCATIONS_KEY, entry)
            self._client.ltrim(REVOCATIONS_KEY, 0, MAX_RECENT_REVOCATIONS - 1)
        except redis.exceptions.RedisError:
            logger.warning("revocation_tracking_unavailable")

    def get_recent_revocations(self, limit: int = 20) -> list[dict[str, object]]:
        try:
            raw = self._client.lrange(REVOCATIONS_KEY, 0, max(limit, 1) - 1)
        except redis.exceptions.RedisError as exc:
            raise TokenStoreUnavailable from exc
        return [json.loads(item) for item in raw]

    def get_session_overview(self, top_n: int = 10) -> dict[str, object]:
        """Operator summary shaped like the violation summaries: key/count lists plus an availability flag."""
        try:
            sessions_by_user: dict[str, int] = {}
            access_tokens = 0
            for key in self._client.scan_iter(match=f"{SESSION_PREFIX}*"):
                data = self._client.hgetall(key)
                user_id = key[len(SESSION_PREFIX):].rsplit(":", 1)[0]
                if data.get("token_type") == "refresh":
                    sessions_by_user[user_id] = sessions_by_user.get(user_id, 0) + 1
                elif data:
                    access_tokens += 1
            recent = self.get_recent_revocations(limit=top_n)
        except (redis.exceptions.RedisError, TokenStoreUnavailable):
            logger.warning("session_overview_unavailable")
            return {
                "available": False,
                "active_sessions": 0,
                "active_access_tokens": 0,
                "users_with_sessions": 0,
                "top_users": [],
                "recent_revocations": [],
            }

        top_users = sorted(
            ({"key": user, "count": count} for user, count in sessions_by_user.items()),
            key=lambda item: item["count"],
            reverse=True,
        )[:top_n]
        return {
            "available": True,
            "active_sessions": sum(sessions_by_user.values()),
            "active_access_tokens": access_tokens,
            "users_with_sessions": len(sessions_by_user),
            "top_users": top_users,
            "recent_revocations": recent,
        }


_redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
    socket_connect_timeout=settings.token_store_redis_timeout_seconds,
    socket_timeout=settings.token_store_redis_timeout_seconds,
)

token_store = TokenStore(_redis_client)
