from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from services.api.app.auth import security_events as events
from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.auth.security_events import security_events
from services.api.app.infra.db import get_db
from services.api.app.infra.rate_limit import rate_limiter
from services.api.app.infra.settings import settings
from services.api.app.realtime.websocket_gateway import manager
from shared.db.models import Message, MessageReceipt, MessageTranslation, Room, RoomMember, User
from shared.receipts import compute_message_receipts, unread_counts_for_user
from shared.schemas.rooms import (
    CreateRoomRequest,
    CreateRoomResponse,
    JoinRoomRequest,
    JoinRoomSelfRequest,
    MarkSeenRequest,
    MarkSeenResponse,
    RoomMessageResponse,
    RoomMembershipResponse,
    RoomSummary,
)
from shared.tracing import start_span

router = APIRouter(prefix="/v1/rooms", tags=["rooms"])


def _message_is_after_anchor(message: Message, anchor: Message) -> bool:
    if message.created_at > anchor.created_at:
        return True
    if message.created_at < anchor.created_at:
        return False
    return message.id > anchor.id


@router.post("", response_model=CreateRoomResponse)
def create_room(
    payload: CreateRoomRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> CreateRoomResponse:
    rate_limiter.enforce(
        f"rl:user:{current_user_id}:rooms_create",
        settings.rate_limit_room_creation_per_user_per_hour,
        3600,
        scope="room_creation_per_user",
        user_id=current_user_id,
    )

    room_id = f"room_{uuid4().hex[:24]}"
    with start_span("api.room.create", user_id=current_user_id):
        room = Room(
            id=room_id,
            name=payload.name,
            default_translation_mode="balanced",
            created_at=datetime.now(timezone.utc),
        )
        membership = RoomMember(
            room_id=room_id,
            user_id=current_user_id,
            role="admin",
            preferred_lang=payload.preferred_lang,
            created_at=datetime.now(timezone.utc),
        )

        db.add(room)
        db.add(membership)
        db.commit()

    return CreateRoomResponse(
        room_id=room.id,
        name=room.name,
        role=membership.role,
        preferred_lang=membership.preferred_lang,
        default_translation_mode=room.default_translation_mode,
        created_at=room.created_at,
    )


@router.get("", response_model=list[RoomSummary])
def list_rooms(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> list[RoomSummary]:
    memberships = db.scalars(
        select(RoomMember).where(RoomMember.user_id == current_user_id)
    ).all()

    rooms: list[RoomSummary] = []
    unread_counts = unread_counts_for_user(db, current_user_id)
    for membership in memberships:
        room = db.get(Room, membership.room_id)
        if room:
            unread = unread_counts.get(room.id, 0)
            rooms.append(
                RoomSummary(
                    room_id=room.id,
                    name=room.name,
                    role=membership.role,
                    preferred_lang=membership.preferred_lang,
                    default_translation_mode=room.default_translation_mode,
                    created_at=room.created_at,
                    has_unread=unread > 0,
                    unread_count=unread,
                )
            )

    return rooms


@router.post("/{room_id}/members", response_model=RoomMembershipResponse)
def upsert_membership(
    room_id: str,
    payload: JoinRoomRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> RoomMembershipResponse:
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    actor = db.scalar(select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == current_user_id))
    if not actor or actor.role != "admin":
        security_events.record(
            events.MEMBERSHIP_DENIED,
            reason="not_admin" if actor else "not_a_member",
            user_id=current_user_id,
            room_id=room_id,
        )
        raise HTTPException(status_code=403, detail="Only room admins can manage members")

    rate_limiter.enforce(
        f"rl:user:{current_user_id}:room_members",
        settings.rate_limit_room_membership_per_admin_per_minute,
        60,
        scope="room_membership_per_admin",
        user_id=current_user_id,
        room_id=room_id,
    )

    membership = db.scalar(select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == payload.user_id))
    with start_span("api.room.membership.upsert", room_id=room_id, user_id=current_user_id):
        if membership is None:
            membership = RoomMember(
                room_id=room_id,
                user_id=payload.user_id,
                role="member",
                preferred_lang=payload.preferred_lang,
                created_at=datetime.now(timezone.utc),
            )
            db.add(membership)
        else:
            membership.preferred_lang = payload.preferred_lang
            membership.role = "member"

        db.commit()
    return RoomMembershipResponse(
        room_id=membership.room_id,
        user_id=membership.user_id,
        role=membership.role,
        preferred_lang=membership.preferred_lang,
        created_at=membership.created_at,
    )


@router.post("/{room_id}/join", response_model=RoomMembershipResponse)
def join_room(
    room_id: str,
    payload: JoinRoomSelfRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> RoomMembershipResponse:
    """Self-service join, unlike POST /members which requires the caller to already be a room admin."""
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    membership = db.scalar(
        select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == current_user_id)
    )
    with start_span("api.room.join", room_id=room_id, user_id=current_user_id):
        if membership is None:
            membership = RoomMember(
                room_id=room_id,
                user_id=current_user_id,
                role="member",
                preferred_lang=payload.preferred_lang,
                created_at=datetime.now(timezone.utc),
            )
            db.add(membership)
        else:
            membership.preferred_lang = payload.preferred_lang

        db.commit()
    return RoomMembershipResponse(
        room_id=membership.room_id,
        user_id=membership.user_id,
        role=membership.role,
        preferred_lang=membership.preferred_lang,
        created_at=membership.created_at,
    )


@router.get("/{room_id}/messages", response_model=list[RoomMessageResponse])
def list_room_messages(
    room_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=50, ge=1, le=200),
    since_message_id: str | None = None,
) -> list[RoomMessageResponse]:
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    membership = db.scalar(
        select(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == current_user_id,
        )
    )
    if not membership:
        security_events.record(
            events.MEMBERSHIP_DENIED, reason="not_a_member", user_id=current_user_id, room_id=room_id
        )
        raise HTTPException(status_code=403, detail="User is not a room member")

    with start_span("api.room.history.replay", room_id=room_id, user_id=current_user_id):
        if since_message_id:
            anchor = db.scalar(
                select(Message).where(
                    Message.room_id == room_id,
                    Message.id == since_message_id,
                )
            )
            if anchor is None:
                raise HTTPException(status_code=404, detail="Anchor message not found")

            query = (
                select(Message)
                .where(
                    Message.room_id == room_id,
                    or_(
                        Message.created_at > anchor.created_at,
                        and_(Message.created_at == anchor.created_at, Message.id > anchor.id),
                    ),
                )
                .order_by(Message.created_at.asc(), Message.id.asc())
                .limit(limit)
            )
            messages = db.scalars(query).all()
        else:
            query = (
                select(Message)
                .where(Message.room_id == room_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
            messages = list(reversed(db.scalars(query).all()))

        receipts_by_message = compute_message_receipts(db, room_id, messages)
        author_names = {
            row[0]: row[1]
            for row in db.execute(
                select(User.id, User.display_name).where(User.id.in_({m.author_user_id for m in messages}))
            ).all()
        }
        results: list[RoomMessageResponse] = []
        for message in messages:
            translation_rows = db.scalars(
                select(MessageTranslation).where(MessageTranslation.message_id == message.id)
            ).all()
            translations = {
                row.target_lang: {
                    "content": row.content,
                    "provider": row.provider,
                    "quality_mode": row.quality_mode,
                    "translated_at": row.translated_at,
                }
                for row in translation_rows
            }
            results.append(
                RoomMessageResponse(
                    message_id=message.id,
                    version=message.version,
                    author_user_id=message.author_user_id,
                    author_display_name=author_names.get(message.author_user_id),
                    source_lang=message.source_lang,
                    content_original=message.content_original,
                    status=message.status,
                    created_at=message.created_at,
                    translations=translations,
                    receipts=receipts_by_message.get(message.id, {"seen": [], "unseen": []}),
                )
            )

        return results


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(
    room_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> None:
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    actor = db.scalar(select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == current_user_id))
    if not actor or actor.role != "admin":
        security_events.record(
            events.MEMBERSHIP_DENIED,
            reason="not_admin" if actor else "not_a_member",
            user_id=current_user_id,
            room_id=room_id,
        )
        raise HTTPException(status_code=403, detail="Only room admins can delete a room")

    member_ids = [row[0] for row in db.execute(select(RoomMember.user_id).where(RoomMember.room_id == room_id)).all()]

    with start_span("api.room.delete", room_id=room_id, user_id=current_user_id):
        # Messages, members, events, translations and receipts go via ON DELETE CASCADE.
        db.delete(room)
        db.commit()

    manager.publish_room_event(room_id, {"type": "RoomDeleted", "room_id": room_id})
    for member_id in member_ids:
        manager.publish_user_event(member_id, {"type": "RoomUnreadHint", "room_id": room_id})


@router.post("/{room_id}/messages/seen", response_model=MarkSeenResponse)
def mark_messages_seen(
    room_id: str,
    payload: MarkSeenRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> MarkSeenResponse:
    membership = db.scalar(
        select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == current_user_id)
    )
    if not membership:
        security_events.record(
            events.MEMBERSHIP_DENIED, reason="not_a_member", user_id=current_user_id, room_id=room_id
        )
        raise HTTPException(status_code=403, detail="User is not a room member")

    requested_ids = list(dict.fromkeys(payload.message_ids))
    valid_ids = [
        row[0]
        for row in db.execute(
            select(Message.id).where(
                Message.room_id == room_id,
                Message.id.in_(requested_ids),
                Message.author_user_id != current_user_id,
            )
        ).all()
    ]
    if not valid_ids:
        return MarkSeenResponse(marked=0)

    seen_at = datetime.now(timezone.utc)
    with start_span("api.room.messages.seen", room_id=room_id, user_id=current_user_id):
        existing = {
            receipt.message_id: receipt
            for receipt in db.scalars(
                select(MessageReceipt).where(
                    MessageReceipt.user_id == current_user_id,
                    MessageReceipt.message_id.in_(valid_ids),
                )
            ).all()
        }
        for message_id in valid_ids:
            receipt = existing.get(message_id)
            if receipt is None:
                db.add(MessageReceipt(message_id=message_id, user_id=current_user_id, seen_at=seen_at))
            else:
                receipt.seen_at = seen_at
        db.commit()

    user = db.get(User, current_user_id)
    manager.publish_room_event(
        room_id,
        {
            "type": "MessageSeen",
            "room_id": room_id,
            "user_id": current_user_id,
            "display_name": user.display_name if user else None,
            "message_ids": valid_ids,
            "seen_at": seen_at.isoformat(),
        },
    )
    manager.publish_user_event(current_user_id, {"type": "RoomUnreadHint", "room_id": room_id})
    return MarkSeenResponse(marked=len(valid_ids))
