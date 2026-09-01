import redis

from services.registration.app.infra.settings import settings

_redis_client = redis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
    socket_connect_timeout=0.2,
    socket_timeout=0.2,
)


def get_redis() -> redis.Redis:
    return _redis_client
