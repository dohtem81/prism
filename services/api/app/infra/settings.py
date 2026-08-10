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


settings = Settings()
