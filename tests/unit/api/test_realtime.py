import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.api.app.api.messages import send_message
from services.api.app.auth.dependencies import create_access_token
from services.api.app.infra.db import get_db
from services.api.app.main import app
from services.api.app.realtime.websocket_gateway import _resolve_user_id, manager
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
    token = create_access_token("user_1")

    websocket_db = MagicMock()
    websocket_room = MagicMock()
    websocket_room.id = "room_1"
    websocket_member = MagicMock()
    websocket_member.user_id = "user_1"
    websocket_db.scalar.side_effect = [websocket_room, websocket_member]
    app.dependency_overrides[get_db] = lambda: websocket_db

    try:
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/room_1?token={token}") as websocket:
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
                assert event["event_type"] == "MessageCreated"
                assert event["event_version"] == 1
                assert event["event_id"].startswith("evt_")
                assert event["room_sequence"] == 8
                assert event["occurred_at"]
                assert event["message"]["message_id"].startswith("msg_")
                celery_client_mock.send_task.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_message_send_and_translation_flow_are_enqueued_and_updated() -> None:
    manager.clear()
    token = create_access_token("user_1")

    websocket_db = MagicMock()
    websocket_room = MagicMock()
    websocket_room.id = "room_1"
    websocket_member = MagicMock()
    websocket_member.user_id = "user_1"
    websocket_db.scalar.side_effect = [websocket_room, websocket_member]
    app.dependency_overrides[get_db] = lambda: websocket_db

    try:
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/room_1?token={token}") as websocket:
                db = MagicMock()
                room = MagicMock()
                room.id = "room_1"
                member = MagicMock()
                member.user_id = "user_1"
                db.scalar.side_effect = [room, member, 7]
                created_at = datetime.now(timezone.utc)
                db.refresh.side_effect = lambda msg: setattr(msg, "created_at", created_at)

                with patch("services.api.app.api.messages.celery_client") as celery_client_mock:
                    response = send_message(_payload(), db=db, current_user_id="user_1")

                assert response.translation_job_enqueued is True
                celery_client_mock.send_task.assert_called_once()
                call_args, call_kwargs = celery_client_mock.send_task.call_args
                assert call_args == ("services.worker.app.tasks.translation.translate_message",)
                assert call_kwargs["queue"] == "translation.requested.q"
                assert call_kwargs["kwargs"]["message_id"] == response.message_id
                assert call_kwargs["kwargs"]["room_id"] == "room_1"
                assert call_kwargs["kwargs"]["source_lang"] == "pl"
                assert call_kwargs["kwargs"]["content_original"] == "Czesc"

                event = websocket.receive_json()
                assert event["type"] == "MessageCreated"
                assert event["event_id"].startswith("evt_")
                assert event["room_sequence"] == 8
                assert event["message"]["message_id"] == response.message_id
    finally:
        app.dependency_overrides.clear()


def test_room_event_publish_uses_redis_channel_for_multi_instance_fanout() -> None:
    manager.clear()
    payload = {
        "event_id": "evt_123",
        "event_type": "MessageCreated",
        "type": "MessageCreated",
        "room_id": "room_1",
        "message": {"message_id": "msg_123"},
    }

    with patch("services.api.app.realtime.websocket_gateway.redis_client.publish") as publish_mock:
        manager.publish_room_event("room_1", payload)

    publish_mock.assert_called_once_with("room:room_1:events", json.dumps(payload))


def test_resolve_user_id_ignores_query_identity_override() -> None:
    token = create_access_token("user_1")

    assert _resolve_user_id(token) == "user_1"


def test_resolve_user_id_rejects_missing_token() -> None:
    with pytest.raises(ValueError):
        _resolve_user_id(None)
