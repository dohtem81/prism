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


def test_translation_update_broadcasts_message_updated_event() -> None:
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
                message = MagicMock()
                message.id = "msg_123"
                message.created_at = datetime.now(timezone.utc)
                message.status = "translated"
                message.version = 2
                message.author_user_id = "user_1"
                message.source_lang = "en"
                message.content_original = "hello"
                message.room_id = "room_1"

                room = MagicMock()
                room.id = "room_1"
                room.default_translation_mode = "balanced"
                member = MagicMock()
                member.preferred_lang = "fr"
                translation = MagicMock()
                translation.target_lang = "fr"
                translation.content = "bonjour"
                translation.provider = "openai"
                translation.quality_mode = "balanced"
                translation.translated_at = datetime.now(timezone.utc)

                db.scalar.side_effect = [message, room, 1]
                db.scalars.return_value.all.return_value = [translation]

                with patch("services.worker.app.tasks.translation.build_translation_provider") as provider_factory_mock:
                    provider = MagicMock()
                    provider.translate.return_value = ("bonjour", 10, 5)
                    provider_factory_mock.return_value = provider

                    with patch("services.worker.app.tasks.translation.redis_client") as redis_client_mock:
                        redis_client_mock.get.return_value = None
                        with patch("services.worker.app.tasks.translation.SessionLocal") as session_local_mock:
                            session_local_mock.return_value.__enter__.return_value = db
                            session_local_mock.return_value.__exit__.return_value = False

                            from services.worker.app.tasks.translation import translate_message

                            result = translate_message("msg_123", "room_1", "en", "hello")

                event = websocket.receive_json()
                assert event["type"] == "MessageUpdated"
                assert event["message_id"] == "msg_123"
                assert event["translations"]["fr"]["content"] == "bonjour"
                assert result["status"] == "translated"
    finally:
        app.dependency_overrides.clear()


def test_message_send_and_translation_flow_are_enqueued_and_updated() -> None:
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
                db.refresh.side_effect = lambda msg: setattr(msg, "created_at", created_at)

                with patch("services.api.app.api.messages.celery_client") as celery_client_mock:
                    response = send_message(_payload(), db=db, current_user_id="user_1")

                assert response.translation_job_enqueued is True
                celery_client_mock.send_task.assert_called_once_with(
                    "services.worker.app.tasks.translation.translate_message",
                    kwargs={
                        "message_id": response.message_id,
                        "room_id": "room_1",
                        "source_lang": "pl",
                        "content_original": "Czesc",
                    },
                    queue="translation.requested.q",
                )

                event = websocket.receive_json()
                assert event["type"] == "MessageCreated"
                assert event["message"]["message_id"] == response.message_id

                worker_db = MagicMock()
                worker_message = MagicMock()
                worker_message.id = response.message_id
                worker_message.created_at = datetime.now(timezone.utc)
                worker_message.status = "original_only"
                worker_message.version = 1
                worker_message.author_user_id = "user_1"
                worker_message.source_lang = "pl"
                worker_message.content_original = "Czesc"
                worker_message.room_id = "room_1"

                worker_room = MagicMock()
                worker_room.id = "room_1"
                worker_room.default_translation_mode = "balanced"
                worker_member = MagicMock()
                worker_member.preferred_lang = "de"
                worker_translation = MagicMock()
                worker_translation.target_lang = "de"
                worker_translation.content = "Hallo"
                worker_translation.provider = "openai"
                worker_translation.quality_mode = "balanced"
                worker_translation.translated_at = datetime.now(timezone.utc)

                worker_db.scalar.side_effect = [worker_message, worker_room, 1]
                worker_db.scalars.return_value.all.return_value = [worker_translation]

                with patch("services.worker.app.tasks.translation.build_translation_provider") as provider_factory_mock:
                    provider = MagicMock()
                    provider.translate.return_value = ("Hallo", 12, 7)
                    provider_factory_mock.return_value = provider
                    with patch("services.worker.app.tasks.translation.redis_client") as redis_client_mock:
                        redis_client_mock.get.return_value = None
                        with patch("services.worker.app.tasks.translation.SessionLocal") as session_local_mock:
                            session_local_mock.return_value.__enter__.return_value = worker_db
                            session_local_mock.return_value.__exit__.return_value = False

                            result = send_message._globals["translate_message"] if False else __import__("services.worker.app.tasks.translation", fromlist=["translate_message"]).translate_message
                            result = __import__("services.worker.app.tasks.translation", fromlist=["translate_message"]).translate_message(
                                response.message_id,
                                "room_1",
                                "pl",
                                "Czesc",
                            )

                assert result["status"] == "translated"
                event = websocket.receive_json()
                assert event["type"] == "MessageUpdated"
                assert event["message_id"] == response.message_id
                assert event["translations"]["de"]["content"] == "Hallo"
    finally:
        app.dependency_overrides.clear()
