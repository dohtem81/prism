import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.api.app.infra.db import SessionLocal
from services.api.app.api.messages import send_message
from services.worker.app.tasks.translation import _record_translation_progress
from services.worker.app.tasks import translation
from services.demo_bot import main as bot
from services.api.app.main import app
from shared.db.models import DemoBotJob, Message, MessageTranslation, OutboxEvent, RegisteredAccount, Room, RoomMember, User
from shared.demo import DEMO_BOT_ID, DEMO_ROOM_ID
from shared.schemas.message_events import SendMessage


pytestmark = pytest.mark.skipif(
    os.getenv("PRISM_DEMO_INTEGRATION_TESTS") != "1",
    reason="Requires an isolated, migrated PostgreSQL and Redis database",
)


def test_demo_session_and_chat_with_database() -> None:
    headers = {"Origin": "https://localhost"}
    client = TestClient(app, base_url="https://localhost")
    response = client.post("/v1/auth/demo", json={"display_name": "Guest", "preferred_lang": "fr"}, headers=headers)
    assert response.status_code == 200, response.text
    user_id = response.json()["user_id"]
    with SessionLocal() as db:
        user = db.get(User, user_id)
        member = db.scalar(select(RoomMember).where(RoomMember.user_id == user_id))
        assert user.is_demo and user.display_name == "Guest"
        assert member.room_id == DEMO_ROOM_ID and member.preferred_lang == "fr"
        assert db.get(RegisteredAccount, user_id) is None
        other_id = f"room_{uuid4().hex}"
        db.add(Room(id=other_id, name="Other", default_translation_mode="balanced"))
        db.commit()

    page = client.get(f"/ui/rooms/{DEMO_ROOM_ID}")
    assert page.status_code == 200
    assert 'id="progressBot"' in page.text
    assert "CPU powered" in page.text and "GPU powered" in page.text
    assert client.post("/v1/auth/refresh", headers=headers).status_code == 200
    assert client.post("/v1/rooms", json={"name": "Forbidden"}, headers=headers).status_code == 403
    assert client.post(f"/v1/rooms/{other_id}/join", json={"preferred_lang": "en"}, headers=headers).status_code == 403
    assert client.post("/v1/users", json={"display_name": "Guest", "preferred_lang": "pl"}, headers=headers).status_code == 200
    assert client.post(f"/v1/rooms/{DEMO_ROOM_ID}/join", json={"preferred_lang": "english"}, headers=headers).status_code == 422
    assert client.post(f"/v1/rooms/{DEMO_ROOM_ID}/join", json={"preferred_lang": "de"}, headers=headers).status_code == 200
    with SessionLocal() as db:
        member = db.scalar(select(RoomMember).where(RoomMember.user_id == user_id))
        assert member.preferred_lang == db.get(User, user_id).preferred_lang == "de"

    other = TestClient(app, base_url="https://localhost")
    assert other.post("/v1/auth/demo", json={"display_name": "Other"}, headers=headers).status_code == 200
    with patch("services.api.app.api.messages.dispatch_outbox_ids"), patch(
        "services.api.app.api.messages.manager.publish_room_event"
    ), patch("services.api.app.api.messages.manager.publish_user_event"):
        response = client.post(
            "/v1/messages",
            json={
                "room_id": DEMO_ROOM_ID,
                "author_user_id": user_id,
                "client_message_id": uuid4().hex,
                "source_lang": "pl",
                "content_original": "Hello General",
            },
            headers=headers,
        )
    assert response.status_code in (200, 201), response.text
    message_id = response.json()["message_id"]
    progress = client.get(f"/v1/messages/{message_id}/progress")
    assert progress.json()["stage"] == "dispatch_pending"
    assert progress.json()["original_publication"] == "pending"
    assert progress.json()["update_publication"] == "not_ready"
    assert progress.json()["other_readers"] == 0
    with SessionLocal() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == message_id, OutboxEvent.event_type == "TranslationRequested"))
        event.status = "processed"
        db.commit()
    assert client.get(f"/v1/messages/{message_id}/progress").json()["stage"] == "queued"
    assert client.get(f"/v1/messages/{message_id}/progress").json()["original_publication"] == "pending"
    with SessionLocal() as db:
        original_event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == message_id, OutboxEvent.event_type == "MessageCreated"))
        original_event.status = "processed"
        db.commit()
    assert client.get(f"/v1/messages/{message_id}/progress").json()["original_publication"] == "published"
    with patch("services.api.app.api.rooms.manager.publish_room_event"), patch("services.api.app.api.rooms.manager.publish_user_event"):
        assert other.post(f"/v1/rooms/{DEMO_ROOM_ID}/messages/seen", json={"message_ids": [message_id]}, headers=headers).status_code == 200
    assert client.get(f"/v1/messages/{message_id}/progress").json()["other_readers"] == 1
    _record_translation_progress(message_id, DEMO_ROOM_ID, failed=False)
    assert client.get(f"/v1/messages/{message_id}/progress").json()["stage"] == "worker_started"
    _record_translation_progress(message_id, DEMO_ROOM_ID, failed=True)
    assert client.get(f"/v1/messages/{message_id}/progress").json()["stage"] == "failed"
    with SessionLocal() as db:
        message = db.scalar(select(Message).where(Message.author_user_id == user_id))
        assert message.content_original == "Hello General"
        message.status = "translated"
        db.add(OutboxEvent(aggregate_type="message", aggregate_id=message_id, event_type="MessageUpdated", payload={}, status="pending"))
        db.commit()
    progress = client.get(f"/v1/messages/{message_id}/progress").json()
    assert progress["stage"] == "completed" and progress["update_publication"] == "pending"
    with SessionLocal() as db:
        update_event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == message_id, OutboxEvent.event_type == "MessageUpdated"))
        update_event.status = "processed"
        db.commit()
    assert client.get(f"/v1/messages/{message_id}/progress").json()["update_publication"] == "published"
    assert other.get(f"/v1/messages/{message_id}/progress").status_code == 404
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    with SessionLocal() as db:
        assert db.get(User, user_id).is_demo


def test_bot_greets_and_replies_via_normal_message_pipeline() -> None:
    headers = {"Origin": "https://localhost"}
    client = TestClient(app, base_url="https://localhost")
    response = client.post("/v1/auth/demo", json={"display_name": "Test bot guest"}, headers=headers)
    assert response.status_code == 200
    user_id = response.json()["user_id"]
    with SessionLocal() as db:
        db.query(DemoBotJob).filter(DemoBotJob.source_id != user_id).delete(synchronize_session=False)
        db.commit()
    with patch("services.api.app.api.messages.dispatch_outbox_ids", return_value={"processed_ids": [], "failed": 0}):
        assert bot.process_next_job()
        with SessionLocal() as db:
            greeting = db.scalar(select(Message).where(
                Message.author_user_id == DEMO_BOT_ID, Message.client_message_id == f"demo-bot-greeting-{user_id}"
            ))
            assert greeting.source_lang == "fr"
            assert "Test bot guest" in greeting.content_original
            assert db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == greeting.id,
                                                      OutboxEvent.event_type == "TranslationRequested"))
        response = client.post("/v1/messages", json={
            "room_id": DEMO_ROOM_ID, "author_user_id": user_id, "client_message_id": uuid4().hex,
            "source_lang": "en", "content_original": "How does Prism translate messages?",
        }, headers=headers)
        assert response.status_code == 200
        message_id = response.json()["message_id"]
        with patch.object(bot, "build_reply", return_value="Prism traduit les messages. Une question ?"):
            assert bot.process_next_job()
        with SessionLocal() as db:
            reply = db.scalar(select(Message).where(
                Message.author_user_id == DEMO_BOT_ID, Message.client_message_id == f"demo-bot-reply-{message_id}"
            ))
            assert reply.source_lang == "fr"
            assert db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == reply.id,
                                                      OutboxEvent.event_type == "TranslationRequested"))
            assert db.scalar(select(DemoBotJob).where(DemoBotJob.source_id == reply.id)) is None


def test_bot_reply_translation_progress_follows_reply_outbox_and_worker() -> None:
    headers = {"Origin": "https://localhost"}
    client = TestClient(app, base_url="https://localhost")
    response = client.post("/v1/auth/demo", json={"display_name": "Reply progress", "preferred_lang": "en"}, headers=headers)
    assert response.status_code == 200
    user_id = response.json()["user_id"]
    with patch("services.api.app.api.messages.dispatch_outbox_ids", return_value={"processed_ids": [], "failed": 0}):
        response = client.post("/v1/messages", json={
            "room_id": DEMO_ROOM_ID, "author_user_id": user_id, "client_message_id": uuid4().hex,
            "source_lang": "en", "content_original": "Synthetic progress test",
        }, headers=headers)
        assert response.status_code == 200
        message_id = response.json()["message_id"]
        with SessionLocal() as db:
            db.query(DemoBotJob).filter(DemoBotJob.source_id != message_id).delete(synchronize_session=False)
            db.commit()
        assert client.get(f"/v1/messages/{message_id}/progress").json()["bot_reply"] is None
        with patch.object(bot, "build_reply", return_value="Bonjour !"):
            assert bot.process_next_job()
        with SessionLocal() as db:
            reply = db.scalar(select(Message).where(
                Message.author_user_id == DEMO_BOT_ID,
                Message.client_message_id == f"demo-bot-reply-{message_id}",
            ))
            assert reply is not None
            reply_id = reply.id

    def progress():
        return client.get(f"/v1/messages/{message_id}/progress").json()["bot_reply"]

    assert progress()["stage"] == "dispatch_pending"
    assert progress()["original_publication"] == "pending"
    with SessionLocal() as db:
        for event in db.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == reply_id)).all():
            event.status = "processed"
        db.commit()
    assert progress()["stage"] == "queued"
    assert progress()["original_publication"] == "published"
    _record_translation_progress(reply_id, DEMO_ROOM_ID, failed=False)
    assert progress()["stage"] == "worker_started"
    provider = MagicMock()
    provider.translate.return_value = ("Hello!", 10, 5)
    with patch.dict(translation._TRANSLATION_PROVIDERS, {"openrouter": lambda model: provider}), \
         patch.object(translation.settings, "translation_provider", "openrouter"), \
         patch.object(translation.settings, "translation_model", "test-model"), \
         patch.object(translation.redis_client, "get", return_value=None), \
         patch.object(translation, "dispatch_outbox_ids"):
        result = translation.run_translation_task(reply_id, DEMO_ROOM_ID, "fr", "Bonjour !")
        assert result["status"] == "translated"
    assert progress()["stage"] == "completed"
    assert progress()["update_publication"] == "pending"
    with SessionLocal() as db:
        event = db.scalar(select(OutboxEvent).where(
            OutboxEvent.aggregate_id == reply_id, OutboxEvent.event_type == "MessageUpdated"
        ))
        event.status = "processed"
        db.commit()
    assert progress()["update_publication"] == "published"
    other = TestClient(app, base_url="https://localhost")
    assert other.post("/v1/auth/demo", json={"display_name": "Other"}, headers=headers).status_code == 200
    assert other.get(f"/v1/messages/{message_id}/progress").status_code == 404


@pytest.mark.parametrize("author", ["guest", "bot"])
def test_demo_translation_uses_configured_openrouter_provider(author: str) -> None:
    headers = {"Origin": "https://localhost"}
    client = TestClient(app, base_url="https://localhost")
    response = client.post("/v1/auth/demo", json={"display_name": "Translation guest", "preferred_lang": "de"}, headers=headers)
    user_id = response.json()["user_id"]
    content = "Translation test " + uuid4().hex
    source_lang = "en" if author == "guest" else "fr"
    with patch("services.api.app.api.messages.dispatch_outbox_ids", return_value={"processed_ids": [], "failed": 0}):
        if author == "guest":
            response = client.post("/v1/messages", json={
                "room_id": DEMO_ROOM_ID, "author_user_id": user_id, "client_message_id": uuid4().hex,
                "source_lang": source_lang, "content_original": content,
            }, headers=headers)
            assert response.status_code == 200
            message_id = response.json()["message_id"]
        else:
            with SessionLocal() as db:
                message = send_message(
                    SendMessage(room_id=DEMO_ROOM_ID, author_user_id=DEMO_BOT_ID, client_message_id=uuid4().hex,
                                source_lang=source_lang, content_original=content),
                    db=db, current_user_id=DEMO_BOT_ID,
                )
                message_id = message.message_id
    provider = MagicMock()
    provider.translate.return_value = ("Bonjour", 10, 5)
    with patch.dict(translation._TRANSLATION_PROVIDERS, {"openrouter": lambda model: provider}), \
         patch.object(translation.settings, "translation_provider", "openrouter"), \
         patch.object(translation.settings, "translation_model", "test-model"), \
         patch.object(translation.redis_client, "get", return_value=None), \
         patch.object(translation, "dispatch_outbox_ids"):
        result = translation.run_translation_task(message_id, DEMO_ROOM_ID, source_lang, content)
        assert result["status"] == "translated"
        assert provider.translate.call_count > 0
        assert all(call.kwargs["content_original"] == content for call in provider.translate.call_args_list)
    with SessionLocal() as db:
        rows = db.scalars(select(MessageTranslation).where(MessageTranslation.message_id == message_id)).all()
        assert rows and all(row.provider == "openrouter" for row in rows)
