import logging
from datetime import datetime, timezone

import redis

from services.api.app.infra.settings import settings
from shared.logging_utils import get_correlation_id, get_logger
from shared.tracing import get_span_id, get_trace_id

logger = get_logger("prism.security")

AUTH_REJECTED = "auth_rejected"
MEMBERSHIP_DENIED = "membership_denied"
TOKEN_REUSED = "token_reused"
LOGOUT = "logout"
SESSION_CREATED = "session_created"
SESSION_REVOKED = "session_revoked"
ALL_SESSIONS_REVOKED = "all_sessions_revoked_for_user"

_EVENT_LEVELS = {
    LOGOUT: logging.INFO,
    SESSION_CREATED: logging.DEBUG,
    SESSION_REVOKED: logging.INFO,
}

# Only these count as violations; session lifecycle events are logged but not counted.
VIOLATION_EVENTS = frozenset({AUTH_REJECTED, MEMBERSHIP_DENIED, TOKEN_REUSED})

BY_EVENT_KEY = "auth:violations:by_event"
BY_USER_KEY = "auth:violations:by_user"
BY_ROOM_KEY = "auth:violations:by_room"

_redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
    socket_connect_timeout=0.2,
    socket_timeout=0.2,
)


class SecurityEvents:
    """Structured security event logging plus Redis counters that fail open if Redis is unreachable."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def record(
        self,
        event: str,
        *,
        reason: str,
        user_id: str | None = None,
        room_id: str | None = None,
    ) -> None:
        # Never pass tokens or secrets here; reason is a short machine-readable code.
        level = _EVENT_LEVELS.get(event, logging.WARNING)
        logger.log(
            level,
            event,
            extra={
                "security_event": event,
                "user_id": user_id,
                "room_id": room_id,
                "reason": reason,
                "correlation_id": get_correlation_id() or "n/a",
                "trace_id": get_trace_id(),
                "span_id": get_span_id(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        if event in VIOLATION_EVENTS:
            self._count(event, user_id=user_id, room_id=room_id)

    def _count(self, event: str, *, user_id: str | None, room_id: str | None) -> None:
        try:
            self._client.hincrby(BY_EVENT_KEY, event, 1)
            if user_id:
                self._client.hincrby(BY_USER_KEY, user_id, 1)
            if room_id:
                self._client.hincrby(BY_ROOM_KEY, room_id, 1)
        except redis.exceptions.RedisError:
            logger.warning("security_violation_tracking_unavailable", extra={"security_event": event})

    def get_violation_summary(self, top_n: int = 10) -> dict[str, object]:
        def _top(counts: dict[str, str]) -> list[dict[str, object]]:
            parsed = [{"key": key, "count": int(value)} for key, value in counts.items()]
            parsed.sort(key=lambda item: item["count"], reverse=True)
            return parsed[:top_n]

        try:
            by_user = self._client.hgetall(BY_USER_KEY)
            by_room = self._client.hgetall(BY_ROOM_KEY)
            by_event = self._client.hgetall(BY_EVENT_KEY)
        except redis.exceptions.RedisError:
            logger.warning("security_violation_summary_unavailable")
            return {"available": False, "top_offenders": [], "top_rooms": [], "by_scope": []}

        # Same shape as the rate-limit summary; "scope" is the security event type here.
        return {
            "available": True,
            "top_offenders": _top(by_user),
            "top_rooms": _top(by_room),
            "by_scope": _top(by_event),
        }


security_events = SecurityEvents(_redis_client)
