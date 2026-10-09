from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from shared.db.models import Message, MessageReceipt, MessageTranslation, RoomMember, User


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def compute_message_receipts(db: Session, room_id: str, messages: Iterable[Message]) -> dict[str, dict[str, Any]]:
    """Per message: who has seen it and who has not (JSON-serializable).

    A member counts as unseen when they have no receipt, or when a translation in their own
    language arrived after they last saw the message. Messages created before a member joined
    are not listed for that member; authors count as having seen their own message.
    """
    messages = list(messages)
    if not messages:
        return {}

    message_ids = [m.id for m in messages]
    members = db.execute(
        select(RoomMember.user_id, RoomMember.preferred_lang, RoomMember.created_at, User.display_name)
        .outerjoin(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == room_id)
    ).all()
    receipts = {
        (row.message_id, row.user_id): row.seen_at
        for row in db.execute(
            select(MessageReceipt.message_id, MessageReceipt.user_id, MessageReceipt.seen_at).where(
                MessageReceipt.message_id.in_(message_ids)
            )
        ).all()
    }
    translated_at: dict[tuple[str, str], datetime] = {}
    for row in db.execute(
        select(MessageTranslation.message_id, MessageTranslation.target_lang, MessageTranslation.translated_at).where(
            MessageTranslation.message_id.in_(message_ids)
        )
    ).all():
        translated_at[(row.message_id, row.target_lang)] = row.translated_at

    result: dict[str, dict[str, Any]] = {}
    for message in messages:
        seen: list[dict[str, Any]] = []
        unseen: list[dict[str, Any]] = []
        for member in members:
            if member.user_id == message.author_user_id:
                seen.append(_entry(member, message.created_at))
                continue
            if _aware(member.created_at) > _aware(message.created_at):
                continue
            seen_at = receipts.get((message.id, member.user_id))
            newest = translated_at.get((message.id, member.preferred_lang))
            if seen_at is None or (newest is not None and _aware(newest) > _aware(seen_at)):
                unseen.append(_entry(member, None))
            else:
                seen.append(_entry(member, seen_at))
        result[message.id] = {"seen": seen, "unseen": unseen}
    return result


def _entry(member: Any, seen_at: datetime | None) -> dict[str, Any]:
    entry: dict[str, Any] = {"user_id": member.user_id, "display_name": member.display_name}
    if seen_at is not None:
        entry["seen_at"] = seen_at.isoformat()
    return entry


def unread_counts_for_user(db: Session, user_id: str) -> dict[str, int]:
    """Unseen message count per room for every room the user belongs to."""
    newer_translation = exists().where(
        MessageTranslation.message_id == Message.id,
        MessageTranslation.target_lang == RoomMember.preferred_lang,
        MessageTranslation.translated_at > MessageReceipt.seen_at,
    )
    rows = db.execute(
        select(RoomMember.room_id, func.count(Message.id))
        .join(Message, Message.room_id == RoomMember.room_id)
        .outerjoin(
            MessageReceipt,
            and_(MessageReceipt.message_id == Message.id, MessageReceipt.user_id == user_id),
        )
        .where(
            RoomMember.user_id == user_id,
            Message.author_user_id != user_id,
            Message.created_at >= RoomMember.created_at,
            or_(MessageReceipt.id.is_(None), newer_translation),
        )
        .group_by(RoomMember.room_id)
    ).all()
    counts: dict[str, int] = defaultdict(int)
    for room_id, count in rows:
        counts[room_id] = int(count)
    return counts
