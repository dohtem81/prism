from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.db import get_db
from shared.db.models import Message, MessageTranslation, Room, RoomMember
from shared.schemas.rooms import (
    CreateRoomRequest,
    CreateRoomResponse,
    JoinRoomRequest,
    RoomMessageResponse,
    RoomMembershipResponse,
    RoomSummary,
)

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
    room_id = f"room_{uuid4().hex[:24]}"
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
    for membership in memberships:
        room = db.get(Room, membership.room_id)
        if room:
            rooms.append(
                RoomSummary(
                    room_id=room.id,
                    name=room.name,
                    role=membership.role,
                    preferred_lang=membership.preferred_lang,
                    default_translation_mode=room.default_translation_mode,
                    created_at=room.created_at,
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
        raise HTTPException(status_code=403, detail="Only room admins can manage members")

    membership = db.scalar(select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == payload.user_id))
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
        raise HTTPException(status_code=403, detail="User is not a room member")

    query = select(Message).where(Message.room_id == room_id)
    if since_message_id:
        anchor = db.scalar(select(Message).where(Message.id == since_message_id))
    else:
        anchor = None

    query = query.order_by(Message.created_at.asc(), Message.id.asc()).limit(limit)
    messages = db.scalars(query).all()
    if anchor is not None:
        messages = [message for message in messages if _message_is_after_anchor(message, anchor)]

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
                source_lang=message.source_lang,
                content_original=message.content_original,
                status=message.status,
                created_at=message.created_at,
                translations=translations,
            )
        )

    return results
