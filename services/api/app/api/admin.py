from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.analytics.metrics import build_room_metrics_summary
from services.api.app.auth import security_events as events
from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.auth.security_events import security_events
from services.api.app.auth.token_store import token_store
from services.api.app.infra.db import get_db
from services.api.app.infra.rate_limit import rate_limiter
from shared.db.models import Room, RoomMember, TranslationTelemetry
from shared.tracing import start_span

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/rate-limits/violations")
def get_rate_limit_violations(
    top_n: int = Query(default=10, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    return rate_limiter.get_violation_summary(top_n=top_n)


@router.get("/auth/violations")
def get_auth_violations(
    top_n: int = Query(default=10, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    """Same shape as the rate-limit summary; `by_scope` holds counts per security event type."""
    return security_events.get_violation_summary(top_n=top_n)


@router.get("/auth/sessions")
def get_auth_sessions(
    top_n: int = Query(default=10, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    """Active session counts (one per live refresh token) and recent revocations / reuse detections."""
    return token_store.get_session_overview(top_n=top_n)


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
        security_events.record(
            events.MEMBERSHIP_DENIED,
            reason="not_admin" if membership else "not_a_member",
            user_id=current_user_id,
            room_id=room_id,
        )
        raise HTTPException(status_code=403, detail="Only room admins can view room metrics")

    with start_span("api.admin.metrics.fetch", room_id=room_id, user_id=current_user_id):
        telemetry_rows = db.scalars(
            select(TranslationTelemetry).where(
                TranslationTelemetry.room_id == room_id,
            )
        ).all()

        return build_room_metrics_summary(room_id=room_id, telemetry_rows=telemetry_rows, window_hours=window_hours)
