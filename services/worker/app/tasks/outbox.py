from typing import Any

from services.worker.app.celery_app import celery_app
from services.worker.app.infra.db import SessionLocal
from services.api.app.realtime.websocket_gateway import manager
from shared.outbox_dispatcher import dispatch_pending_outbox


@celery_app.task(name="services.worker.app.tasks.outbox.dispatch_pending_outbox_events")
def dispatch_pending_outbox_events() -> dict[str, Any]:
    return dispatch_pending_outbox(
        SessionLocal,
        send_task=celery_app.send_task,
        publish_room_event=manager.publish_room_event,
        publish_user_event=manager.publish_user_event,
    )