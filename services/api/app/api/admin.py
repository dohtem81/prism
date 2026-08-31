from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.analytics.metrics import build_room_metrics_summary
from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.db import get_db
from services.api.app.infra.rate_limit import rate_limiter
from shared.db.models import Room, RoomMember, TranslationTelemetry

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/rate-limits/violations")
def get_rate_limit_violations(
    top_n: int = Query(default=10, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    return rate_limiter.get_violation_summary(top_n=top_n)


@router.get("/rooms/{room_id}/metrics")
def get_room_metrics(
    room_id: str,
    window_hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    membership = db.scalar(
        select(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == current_user_id,
        )
    )
    if membership is None or membership.role != "admin":
        raise HTTPException(status_code=403, detail="Only room admins can view room metrics")

    telemetry_rows = db.scalars(
        select(TranslationTelemetry).where(
            TranslationTelemetry.room_id == room_id,
        )
    ).all()

    return build_room_metrics_summary(room_id=room_id, telemetry_rows=telemetry_rows, window_hours=window_hours)
