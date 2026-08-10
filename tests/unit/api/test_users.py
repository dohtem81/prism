from datetime import datetime, timezone
from unittest.mock import MagicMock

from services.api.app.api.users import create_user
from shared.db.models import User
from shared.schemas.users import CreateUserRequest


def test_create_user_creates_profile_for_new_subject() -> None:
    db = MagicMock()
    db.scalar.return_value = None

    response = create_user(
        CreateUserRequest(display_name="Ada", preferred_lang="en"),
        db=db,
        current_user_id="user_123",
    )

    assert response.user_id == "user_123"
    assert response.display_name == "Ada"
    assert response.preferred_lang == "en"
    assert db.add.call_count == 1
    db.commit.assert_called_once()


def test_create_user_updates_existing_profile_when_display_name_provided() -> None:
    db = MagicMock()
    existing = User(id="user_123", display_name="Old", preferred_lang="pl", created_at=datetime.now(timezone.utc))
    db.scalar.return_value = existing

    response = create_user(
        CreateUserRequest(display_name="New", preferred_lang="de"),
        db=db,
        current_user_id="user_123",
    )

    assert response.display_name == "New"
    assert response.preferred_lang == "de"
    db.commit.assert_called_once()
