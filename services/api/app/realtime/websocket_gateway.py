from collections import defaultdict
from typing import DefaultDict

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import resolve_authenticated_user_id
from services.api.app.infra.db import get_db
from shared.db.models import Room, RoomMember

router = APIRouter(tags=["realtime"])


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: DefaultDict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, room_id: str) -> None:
        await websocket.accept()
        self._connections[room_id].add(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str | None = None) -> None:
        if room_id is not None:
            self._connections[room_id].discard(websocket)
            if not self._connections[room_id]:
                del self._connections[room_id]
            return

        for current_room_id in list(self._connections.keys()):
            self._connections[current_room_id].discard(websocket)
            if not self._connections[current_room_id]:
                del self._connections[current_room_id]

    async def broadcast(self, room_id: str, payload: dict) -> None:
        sockets = list(self._connections.get(room_id, set()))
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(websocket, room_id)

    def clear(self) -> None:
        self._connections.clear()


manager = ConnectionManager()


def _resolve_user_id(token: str | None) -> str:
    if not token:
        raise ValueError("Missing token")
    try:
        return resolve_authenticated_user_id(token)
    except Exception as exc:
        raise ValueError("Invalid token") from exc


@router.websocket("/ws/{room_id}")
async def websocket_gateway(
    websocket: WebSocket,
    room_id: str,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    try:
        resolved_user_id = _resolve_user_id(token)
    except ValueError:
        await websocket.close(code=1008)
        return

    room = db.scalar(select(Room).where(Room.id == room_id))
    if not room:
        await websocket.close(code=1008)
        return

    membership = db.scalar(
        select(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == resolved_user_id,
        )
    )
    if not membership:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, room_id)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        return
