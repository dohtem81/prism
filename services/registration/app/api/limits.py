from fastapi import Request
from redis import Redis

from services.registration.app.infra.settings import settings
from shared import abuse_guard


def enforce_registration_limits(request: Request, cache: Redis, email: str) -> None:
    if not settings.rate_limit_enabled:
        return
    ip = abuse_guard.client_ip(request)
    domain = email.rsplit("@", 1)[-1].casefold()
    abuse_guard.enforce(
        cache, f"rl:reg:ip:hour:{ip}", settings.registration_ip_per_hour, 3600, scope="registration_ip_hour"
    )
    abuse_guard.enforce(
        cache, f"rl:reg:ip:day:{ip}", settings.registration_ip_per_day, 86400, scope="registration_ip_day"
    )
    abuse_guard.enforce(
        cache,
        f"rl:reg:domain:{abuse_guard.digest(domain)}",
        settings.registration_domain_per_hour,
        3600,
        scope="registration_domain_hour",
    )
