import asyncio
import queue
from collections import defaultdict
from unittest.mock import patch

from services.api.app.realtime import websocket_gateway
from services.api.app.realtime.websocket_gateway import ConnectionManager


class FakePubSub:
    def __init__(self, broker: "FakeBroker") -> None:
        self._broker = broker
        self.messages: queue.Queue = queue.Queue()
        self.channels: list[str] = []
        self.closed = False

    def subscribe(self, channel: str) -> None:
        self.channels.append(channel)
        self._broker.subscribers[channel].append(self)

    def get_message(self, timeout: float = 0):
        if self._broker.fail_next_get:
            self._broker.fail_next_get = False
            raise ConnectionError("redis connection lost")
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.closed = True
        for channel in self.channels:
            if self in self._broker.subscribers[channel]:
                self._broker.subscribers[channel].remove(self)


class FakeBroker:
    """In-memory stand-in for the Redis client shared by every simulated API instance."""

    def __init__(self) -> None:
        self.subscribers: dict[str, list[FakePubSub]] = defaultdict(list)
        self.fail_next_get = False
        self.pubsubs_created = 0

    def publish(self, channel: str, data: str) -> int:
        targets = list(self.subscribers[channel])
        for pubsub in targets:
            pubsub.messages.put({"type": "message", "channel": channel, "data": data})
        return len(targets)

    def pubsub(self, ignore_subscribe_messages: bool = True) -> FakePubSub:
        self.pubsubs_created += 1
        return FakePubSub(self)


class FakeSocket:
    def __init__(self) -> None:
        self.received: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, payload: dict) -> None:
        self.received.append(payload)


async def _wait_for(condition, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


def _event(room_id: str, message_id: str, event_type: str = "MessageCreated") -> dict:
    return {"type": event_type, "event_type": event_type, "room_id": room_id, "message": {"message_id": message_id}}


def _run(coro_fn) -> None:
    broker = FakeBroker()
    with patch.object(websocket_gateway, "redis_client", broker):
        asyncio.run(coro_fn(broker))


def test_event_published_by_one_instance_reaches_clients_on_another_instance() -> None:
    async def scenario(broker: FakeBroker) -> None:
        instance_a, instance_b = ConnectionManager(), ConnectionManager()
        client_a, client_b, other_room_b = FakeSocket(), FakeSocket(), FakeSocket()

        await instance_a.connect(client_a, "room_1")
        await instance_a.ensure_redis_listener("room_1")
        await instance_b.connect(client_b, "room_1")
        await instance_b.ensure_redis_listener("room_1")
        await instance_b.connect(other_room_b, "room_2")
        await instance_b.ensure_redis_listener("room_2")
        await _wait_for(
            lambda: len(broker.subscribers["room:room_1:events"]) == 2
            and len(broker.subscribers["room:room_2:events"]) == 1
        )

        created = _event("room_1", "msg_1")
        instance_a.publish_room_event("room_1", created)
        updated = _event("room_1", "msg_1", "MessageUpdated")
        instance_b.publish_room_event("room_1", updated)

        await _wait_for(lambda: len(client_a.received) == 2 and len(client_b.received) == 2)
        assert {e["event_type"] for e in client_a.received} == {"MessageCreated", "MessageUpdated"}
        assert {e["event_type"] for e in client_b.received} == {"MessageCreated", "MessageUpdated"}
        assert other_room_b.received == []

        for manager, socket, room in (
            (instance_a, client_a, "room_1"),
            (instance_b, client_b, "room_1"),
            (instance_b, other_room_b, "room_2"),
        ):
            manager.disconnect(socket, room)
        await _wait_for(lambda: not instance_a._redis_listeners and not instance_b._redis_listeners)

    _run(scenario)


def test_each_event_is_delivered_once_per_local_client() -> None:
    async def scenario(broker: FakeBroker) -> None:
        instance_a, instance_b = ConnectionManager(), ConnectionManager()
        client_a, client_b = FakeSocket(), FakeSocket()
        for manager, socket in ((instance_a, client_a), (instance_b, client_b)):
            await manager.connect(socket, "room_1")
            await manager.ensure_redis_listener("room_1")
            await manager.ensure_redis_listener("room_1")
        await _wait_for(lambda: len(broker.subscribers["room:room_1:events"]) == 2)

        instance_a.publish_room_event("room_1", _event("room_1", "msg_1"))
        await _wait_for(lambda: client_a.received and client_b.received)
        await asyncio.sleep(0.3)

        assert len(client_a.received) == 1 and len(client_b.received) == 1
        instance_a.disconnect(client_a, "room_1")
        instance_b.disconnect(client_b, "room_1")
        await _wait_for(lambda: not instance_a._redis_listeners and not instance_b._redis_listeners)

    _run(scenario)


def test_single_instance_still_delivers_through_redis() -> None:
    async def scenario(broker: FakeBroker) -> None:
        instance = ConnectionManager()
        client = FakeSocket()
        await instance.connect(client, "room_1")
        await instance.ensure_redis_listener("room_1")
        await _wait_for(lambda: broker.subscribers["room:room_1:events"])

        instance.publish_room_event("room_1", _event("room_1", "msg_1"))

        await _wait_for(lambda: len(client.received) == 1)
        instance.disconnect(client, "room_1")
        await _wait_for(lambda: not instance._redis_listeners)

    _run(scenario)


def test_subscription_is_released_when_last_local_client_leaves() -> None:
    async def scenario(broker: FakeBroker) -> None:
        instance = ConnectionManager()
        first, second = FakeSocket(), FakeSocket()
        await instance.connect(first, "room_1")
        await instance.connect(second, "room_1")
        await instance.ensure_redis_listener("room_1")
        await _wait_for(lambda: len(broker.subscribers["room:room_1:events"]) == 1)

        instance.disconnect(first, "room_1")
        await asyncio.sleep(1.3)
        assert len(broker.subscribers["room:room_1:events"]) == 1  # one client still local

        instance.disconnect(second, "room_1")
        await _wait_for(lambda: not instance._redis_listeners)
        assert broker.subscribers["room:room_1:events"] == []

        # A later connection subscribes again.
        third = FakeSocket()
        await instance.connect(third, "room_1")
        await instance.ensure_redis_listener("room_1")
        await _wait_for(lambda: len(broker.subscribers["room:room_1:events"]) == 1)
        instance.publish_room_event("room_1", _event("room_1", "msg_2"))
        await _wait_for(lambda: len(third.received) == 1)
        instance.disconnect(third, "room_1")
        await _wait_for(lambda: not instance._redis_listeners)

    _run(scenario)


def test_listener_resubscribes_after_a_redis_error() -> None:
    async def scenario(broker: FakeBroker) -> None:
        instance = ConnectionManager()
        client = FakeSocket()
        await instance.connect(client, "room_1")
        broker.fail_next_get = True
        await instance.ensure_redis_listener("room_1")

        await _wait_for(lambda: broker.pubsubs_created >= 2 and len(broker.subscribers["room:room_1:events"]) == 1)
        instance.publish_room_event("room_1", _event("room_1", "msg_1"))

        await _wait_for(lambda: len(client.received) == 1)
        instance.disconnect(client, "room_1")
        await _wait_for(lambda: not instance._redis_listeners)

    _run(scenario)
