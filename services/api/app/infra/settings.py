from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "prism"
    app_env: str = "dev"
    app_log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql+psycopg://prism:prism@localhost:5432/prism"
    celery_broker_url: str = "amqp://prism:prism@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"

    redis_host: str = "localhost"
    redis_port: int = 6379
    jwt_secret: str = "dev-secret"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 7
    # Short timeouts so an unreachable Redis rejects requests quickly instead of hanging them.
    token_store_redis_timeout_seconds: float = 0.5
    # Local-dev default only. Production deployments MUST set this explicitly to their real
    # browser origin(s); JSON list in env, e.g. CORS_ALLOWED_ORIGINS=["https://app.example.com"].
    # Never use "*" with credentials. Auth is bearer-token only (no cookies, so no CSRF surface).
    cors_allowed_origins: list[str] = ["http://localhost:8000"]

    # Base URL the webui uses to reach the standalone registration service from the browser.
    registration_service_url: str = "http://localhost:8100"

    rate_limit_enabled: bool = True
    rate_limit_messages_per_user_per_minute: int = 30
    rate_limit_messages_per_room_per_minute: int = 120
    rate_limit_room_creation_per_user_per_hour: int = 10
    rate_limit_room_membership_per_admin_per_minute: int = 20
    rate_limit_ws_connections_per_user: int = 3

    rate_limit_messages_per_user_per_day: int = 2000
    rate_limit_messages_per_room_per_day: int = 5000
    rate_limit_translation_jobs_per_user_per_day: int = 2000


settings = Settings()
