from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.demo_bot import main
from shared.db.models import DemoBotJob, Message, User
from shared.demo import DEMO_BOT_ID, DEMO_ROOM_ID


def test_relevant_docs_selects_matching_local_passages(tmp_path, monkeypatch) -> None:
    (tmp_path / "architecture.md").write_text("# Queue\nRabbitMQ carries translation jobs.", encoding="utf-8")
    (tmp_path / "other.md").write_text("# Rooms\nRooms contain users.", encoding="utf-8")
    monkeypatch.setattr(main, "DOCS", tmp_path)
    result = main.relevant_docs("How does RabbitMQ carry translation?")
    assert result[0][0] == "architecture.md"
    assert "RabbitMQ" in result[0][1]


def test_greeting_is_sent_as_french_bot_message() -> None:
    db = MagicMock()
    send_db = MagicMock()
    job = DemoBotJob(id=1, kind="greeting", source_id="user1", status="pending", attempts=0,
                     next_attempt_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc))
    db.scalar.return_value = job
    db.get.return_value = User(id="user1", is_demo=True, display_name="Ada")
    contexts = [MagicMock(), MagicMock()]
    contexts[0].__enter__.return_value = db
    contexts[1].__enter__.return_value = send_db
    with patch.object(main, "SessionLocal", side_effect=contexts), patch.object(main, "send_message") as send:
        assert main.process_next_job()
    payload = send.call_args.args[0]
    assert payload.author_user_id == DEMO_BOT_ID
    assert payload.room_id == DEMO_ROOM_ID and payload.source_lang == "fr"
    assert "Ada" in payload.content_original and "structure" in payload.content_original
    assert job.status == "completed"


def test_bot_job_failure_retries_without_marking_complete() -> None:
    db = MagicMock()
    job = DemoBotJob(id=1, kind="reply", source_id="msg", status="pending", attempts=0,
                     next_attempt_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc))
    db.scalar.return_value = job
    message = Message(id="msg", room_id=DEMO_ROOM_ID, author_user_id="demo")
    db.get.side_effect = [message, User(id="demo", is_demo=True)]
    context = MagicMock()
    context.__enter__.return_value = db
    with patch.object(main, "SessionLocal", return_value=context), patch.object(main, "build_reply", side_effect=RuntimeError("unavailable")):
        assert main.process_next_job()
    assert job.status == "pending" and job.attempts == 1
    db.commit.assert_called_once()


def test_reply_uses_local_model_and_selected_documentation(monkeypatch) -> None:
    db = MagicMock()
    message = Message(id="msg", room_id=DEMO_ROOM_ID, author_user_id="demo", content_original="RabbitMQ",
                      created_at=datetime.now(timezone.utc))
    db.scalars.return_value.all.return_value = [message]
    client = MagicMock()
    redis = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = "RabbitMQ gère la file. Que veux-tu savoir ?"
    monkeypatch.setattr(main, "local_client", lambda: client)
    monkeypatch.setattr(main, "redis_client", redis)
    monkeypatch.setattr(main, "relevant_docs", lambda query: [("architecture.md", "RabbitMQ")])
    reply = main.build_reply(db, message)
    assert "RabbitMQ" in reply
    assert "Documentation fournie : docs/architecture.md" in reply
    redis.setex.assert_called_once_with("prism:demo-bot:processing:msg", 150, "processing")
    redis.delete.assert_called_once_with("prism:demo-bot:processing:msg")
    prompt = client.chat.completions.create.call_args.kwargs["messages"]
    assert "docs/architecture.md" in prompt[1]["content"]


def test_processing_marker_is_removed_after_model_error(monkeypatch) -> None:
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    message = Message(id="msg", room_id=DEMO_ROOM_ID, author_user_id="demo", content_original="question",
                      created_at=datetime.now(timezone.utc))
    client = MagicMock()
    client.chat.completions.create.side_effect = TimeoutError("model timeout")
    redis = MagicMock()
    monkeypatch.setattr(main, "local_client", lambda: client)
    monkeypatch.setattr(main, "redis_client", redis)
    monkeypatch.setattr(main, "relevant_docs", lambda query: [])
    with pytest.raises(TimeoutError):
        main.build_reply(db, message)
    redis.delete.assert_called_once_with("prism:demo-bot:processing:msg")
