from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from shared.db.models import Room, RoomMember, User


def seed_demo_data(db: Session) -> dict[str, object]:
    user_id = f"user_{uuid4().hex[:8]}"
    room_id = f"room_{uuid4().hex[:8]}"

    user = User(
        id=user_id,
        display_name="Demo User",
        preferred_lang="en",
        created_at=datetime.now(timezone.utc),
    )
    room = Room(
        id=room_id,
        name="Demo Room",
        default_translation_mode="balanced",
        created_at=datetime.now(timezone.utc),
    )
    membership = RoomMember(
        room_id=room_id,
        user_id=user_id,
        role="admin",
        preferred_lang="en",
        created_at=datetime.now(timezone.utc),
    )

    db.add(user)
    db.add(room)
    db.add(membership)
    db.commit()

    return {
        "users": 1,
        "room_id": room_id,
        "user_id": user_id,
    }


if __name__ == "__main__":
    from services.api.app.infra.db import SessionLocal

    with SessionLocal() as db:
        payload = seed_demo_data(db)
        print(f"Seeded demo data: {payload}")
