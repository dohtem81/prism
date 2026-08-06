from celery import Celery

from services.api.app.infra.settings import settings

celery_client = Celery(
    "prism_api",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
