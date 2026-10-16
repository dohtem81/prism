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
celery_app.conf.beat_schedule = {
    "dispatch-pending-outbox-events": {
        "task": "services.worker.app.tasks.outbox.dispatch_pending_outbox_events",
        "schedule": 10.0,
    },
}

# autodiscover_tasks(["services.worker.app.tasks"]) would look for a "tasks.tasks" submodule,
# which doesn't exist here, so tasks never registered. Import the module directly instead.
import services.worker.app.tasks.translation  # noqa: E402, F401
import services.worker.app.tasks.outbox  # noqa: E402, F401
