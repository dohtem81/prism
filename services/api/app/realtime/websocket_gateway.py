import asyncio
import json
from collections import defaultdict
from typing import DefaultDict

import redis
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.api.app.auth.dependencies import resolve_authenticated_user_id
from services.api.app.infra.db import get_db
from services.api.app.infra.settings import settings
from shared.db.models import Room, RoomMember

redis_client = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)

router = APIRouter(tags=["realtime"])


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: DefaultDict[str, set[WebSocket]] = defaultdict(set)
        self._user_connections: DefaultDict[str, set[WebSocket]] = defaultdict(set)
        self._redis_listeners: set[str] = set()
        self._redis_listener_tasks: set[asyncio.Task[None]] = set()

    def active_connection_count(self, user_id: str) -> int:
        return len(self._user_connections.get(user_id, set()))

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str | None = None) -> None:
        await websocket.accept()
        self._connections[room_id].add(websocket)
        if user_id is not None:
            self._user_connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str | None = None, user_id: str | None = None) -> None:
        if user_id is not None:
            self._user_connections[user_id].discard(websocket)
            if not self._user_connections[user_id]:
                del self._user_connections[user_id]

        if room_id is not None:
            self._connections[room_id].discard(websocket)
            if not self._connections[room_id]:
                del self._connections[room_id]
            return

        for current_room_id in list(self._connections.keys()):
            self._connections[current_room_id].discard(websocket)
            if not self._connections[current_room_id]:
                del self._connections[current_room_id]

    async def _handle_redis_message(self, room_id: str, raw_message: str) -> None:
        try:
            payload = json.loads(raw_message)
        except (TypeError, ValueError):
            return

        await self.broadcast(room_id, payload)

    async def ensure_redis_listener(self, room_id: str) -> None:
        if room_id in self._redis_listeners:
            return

        self._redis_listeners.add(room_id)

        async def _listen_for_room_events() -> None:
            pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
            channel = f"room:{room_id}:events"
            pubsub.subscribe(channel)
            try:
                while True:
                    message = pubsub.get_message(timeout=1)
                    if not message or message.get("type") != "message":
                        continue
                    data = message.get("data")
                    if isinstance(data, str):
                        await self._handle_redis_message(room_id, data)
            except Exception:
                self._redis_listeners.discard(room_id)
                pubsub.close()

        task = asyncio.create_task(_listen_for_room_events())
        self._redis_listener_tasks.add(task)
        task.add_done_callback(self._redis_listener_tasks.discard)

    def publish_room_event(self, room_id: str, payload: dict) -> None:
        redis_client.publish(f"room:{room_id}:events", json.dumps(payload))

    async def broadcast(self, room_id: str, payload: dict) -> None:
        sockets = list(self._connections.get(room_id, set()))
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(websocket, room_id)

    def clear(self) -> None:
        self._connections.clear()
        self._user_connections.clear()
        self._redis_listeners.clear()
        for task in list(self._redis_listener_tasks):
            task.cancel()
        self._redis_listener_tasks.clear()


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

    if manager.active_connection_count(resolved_user_id) >= settings.rate_limit_ws_connections_per_user:
        await websocket.close(code=1013)
        return

    await manager.connect(websocket, room_id, resolved_user_id)
    await manager.ensure_redis_listener(room_id)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id, resolved_user_id)
        return
