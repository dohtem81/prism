from celery import Celery
from services.worker.app.infra.settings import settings

celery_app = Celery(
    "prism_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.task_routes = {
    "services.worker.app.tasks.translation.translate_message": {
        "queue": "translation.requested.q",
    },
}

celery_app.autodiscover_tasks(["services.worker.app.tasks"])
