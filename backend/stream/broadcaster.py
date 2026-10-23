"""Server-sent event fan-out.

Subscribers get bounded queues. When a slow client falls behind, the oldest event
is dropped rather than growing memory or blocking ingestion; the console always
has a polling fallback, so a dropped frame is not a correctness problem.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from backend.config import settings


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sequence = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=settings.stream_queue_size)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        if self._loop is None:
            return
        self._sequence += 1
        payload = {"type": event_type, "sequence": self._sequence, "data": data}
        try:
            self._loop.call_soon_threadsafe(self._dispatch, payload)
        except RuntimeError:
            return

    def _dispatch(self, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


def format_sse(payload: dict[str, Any]) -> str:
    return f"event: {payload['type']}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


bus = EventBus()
