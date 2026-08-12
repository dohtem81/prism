from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    celery_broker_url: str = "amqp://prism:prism@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"
    database_url: str = "postgresql+psycopg://prism:prism@localhost:5432/prism"
    translation_provider: str = "openai"
    translation_model: str = "gpt-4.1-mini"
    translation_fallback_provider: str | None = None
    translation_fallback_model: str | None = None
    openai_api_key: str | None = None
    openai_translation_model: str = "gpt-4.1-mini"
    redis_host: str = "localhost"
    redis_port: int = 6379


settings = WorkerSettings()
