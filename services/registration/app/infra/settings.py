from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "prism-registration"
    app_env: str = "dev"
    app_log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8100

    database_url: str = "postgresql+psycopg://prism:prism@localhost:5432/prism"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_cache_ttl_seconds: int = 3600

    # Where clients are sent when registration fails because the account already exists.
    auth_service_url: str = "http://localhost:8000/v1/auth/login"


settings = Settings()
