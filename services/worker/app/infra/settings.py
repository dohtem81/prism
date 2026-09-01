from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    celery_broker_url: str = "amqp://prism:prism@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"
    database_url: str = "postgresql+psycopg://prism:prism@localhost:5432/prism"
    translation_provider: str = "openrouter"
    # If set, used for every quality mode, overriding the per-mode settings below.
    translation_model: str | None = None
    translation_fallback_provider: str | None = None
    translation_fallback_model: str | None = None
    # Per-room "quality mode" model overrides, used only when translation_model is unset.
    translation_model_low_latency: str | None = None
    translation_model_balanced: str | None = None
    translation_model_high_quality: str | None = None
    openai_api_key: str | None = None
    openai_translation_model: str = "gpt-4.1-mini"
    # OpenRouter exposes an OpenAI-compatible API that routes to many underlying LLMs by model slug.
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_url: str | None = None
    openrouter_app_name: str = "prism"
    redis_host: str = "localhost"
    redis_port: int = 6379


settings = WorkerSettings()
