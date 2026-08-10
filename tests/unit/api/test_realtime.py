from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from services.api.app.api.messages import send_message
from services.api.app.infra.db import get_db
from services.api.app.main import app
from services.api.app.realtime.websocket_gateway import manager
from shared.schemas.message_events import SendMessage


def _payload() -> SendMessage:
    return SendMessage(
        author_user_id="user_1",
        room_id="room_1",
        client_message_id="cmsg_1",
        source_lang="pl",
        content_original="Czesc",
    )


def test_message_broadcasts_to_room_websocket_subscribers() -> None:
    manager.clear()

    websocket_db = MagicMock()
    websocket_room = MagicMock()
    websocket_room.id = "room_1"
    websocket_member = MagicMock()
    websocket_member.user_id = "user_1"
    websocket_db.scalar.side_effect = [websocket_room, websocket_member]
    app.dependency_overrides[get_db] = lambda: websocket_db

    try:
        with TestClient(app) as client:
            with client.websocket_connect("/ws/room_1?token=dev-token&user_id=user_1") as websocket:
                db = MagicMock()
                room = MagicMock()
                room.id = "room_1"
                member = MagicMock()
                member.user_id = "user_1"
                db.scalar.side_effect = [room, member, 7]

                created_at = datetime.now(timezone.utc)

                def _refresh(msg):
                    msg.created_at = created_at

                db.refresh.side_effect = _refresh

                with patch("services.api.app.api.messages.celery_client") as celery_client_mock:
                    send_message(_payload(), db=db, current_user_id="user_1")

                event = websocket.receive_json()
                assert event["type"] == "MessageCreated"
                assert event["message"]["message_id"].startswith("msg_")
                celery_client_mock.send_task.assert_called_once()
    finally:
        app.dependency_overrides.clear()
