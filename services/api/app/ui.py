from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import Depends

from services.api.app.auth.dependencies import get_current_user_id
from services.api.app.infra.db import get_db
from services.api.app.infra.settings import settings
from shared.db.models import Room, RoomMember

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory="templates")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "title": "Prism · Register",
            "registration_service_url": settings.registration_service_url,
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "title": "Prism · Log in",
        },
    )


@router.get("", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Prism Dashboard",
        },
    )


@router.get("/rooms/{room_id}", response_class=HTMLResponse)
async def room_page(request: Request, room_id: str, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)) -> HTMLResponse:
    room = db.scalar(select(Room).where(Room.id == room_id))
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

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": f"Prism · {room.name}",
            "room_id": room_id,
            "room_name": room.name,
            "room_role": membership.role,
        },
    )
