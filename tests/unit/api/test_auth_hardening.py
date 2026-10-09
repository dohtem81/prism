import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from jose import jwt

from services.api.app import main as main_module
from services.api.app.auth import dependencies
from services.api.app.auth.dependencies import ALGORITHM, create_access_token, resolve_authenticated_user_id
from services.api.app.infra.settings import settings


def test_dev_token_authenticates_in_dev_env() -> None:
    with patch.object(settings, "app_env", "dev"):
        assert resolve_authenticated_user_id("dev-token") == "dev-user"


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_dev_token_is_rejected_outside_dev_env(env: str) -> None:
    with patch.object(settings, "app_env", env):
        with pytest.raises(HTTPException) as exc:
            resolve_authenticated_user_id("dev-token")

    assert exc.value.status_code == 401


def test_access_token_uses_configured_ttl_and_defaults_to_30_minutes() -> None:
    assert settings.access_token_ttl_minutes == 30

    token = create_access_token("user_1")
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    remaining = payload["exp"] - datetime.now(timezone.utc).timestamp()
    assert 29 * 60 < remaining <= 30 * 60

    with patch.object(settings, "access_token_ttl_minutes", 5):
        short = jwt.decode(create_access_token("user_1"), settings.jwt_secret, algorithms=[ALGORITHM])
    assert short["exp"] - datetime.now(timezone.utc).timestamp() <= 5 * 60


def test_startup_warns_on_default_secret_outside_dev(caplog: pytest.LogCaptureFixture) -> None:
    with patch.object(settings, "app_env", "prod"), patch.object(settings, "jwt_secret", "dev-secret"):
        with caplog.at_level(logging.WARNING):
            main_module.check_security_settings()

    assert any(record.getMessage() == "insecure_jwt_secret" for record in caplog.records)


def test_startup_does_not_warn_in_dev_or_with_custom_secret(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        with patch.object(settings, "app_env", "dev"), patch.object(settings, "jwt_secret", "dev-secret"):
            main_module.check_security_settings()
        with patch.object(settings, "app_env", "prod"), patch.object(settings, "jwt_secret", "a-strong-secret"):
            main_module.check_security_settings()

    assert not any(record.getMessage() == "insecure_jwt_secret" for record in caplog.records)


def test_cors_uses_explicit_origins_not_wildcard() -> None:
    assert "*" not in settings.cors_allowed_origins
    cors = next(m for m in main_module.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_origins"] == settings.cors_allowed_origins
    assert cors.kwargs["allow_credentials"] is True
