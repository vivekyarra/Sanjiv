import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sanjiv.maritime.contracts import OperatingMode, OperationsEvent, OperationsEventType


class OperationsBroker:
    def __init__(self, *, history_size: int = 500, subscriber_queue_size: int = 100) -> None:
        self._history: deque[OperationsEvent] = deque(maxlen=history_size)
        self._subscribers: set[asyncio.Queue[OperationsEvent]] = set()
        self._subscriber_queue_size = subscriber_queue_size
        self._sequence = 0
        self._lock = asyncio.Lock()

    @property
    def cursor(self) -> int:
        return self._sequence

    async def publish(
        self, event_type: OperationsEventType, mode: OperatingMode, payload: dict[str, Any]
    ) -> OperationsEvent:
        async with self._lock:
            self._sequence += 1
            event = OperationsEvent(
                sequence=self._sequence,
                event_type=event_type,
                occurred_at=datetime.now(UTC),
                operating_mode=mode,
                payload=payload,
            )
            self._history.append(event)
            for queue in tuple(self._subscribers):
                if queue.full():
                    while not queue.empty():
                        queue.get_nowait()
                    queue.put_nowait(
                        OperationsEvent(
                            sequence=self._sequence,
                            event_type="RESYNC_REQUIRED",
                            occurred_at=datetime.now(UTC),
                            operating_mode=mode,
                            payload={"reason": "subscriber_queue_overflow"},
                        )
                    )
                else:
                    queue.put_nowait(event)
            return event

    def since(self, cursor: int) -> list[OperationsEvent] | None:
        if not self._history:
            return []
        oldest = self._history[0].sequence
        if cursor and cursor < oldest - 1:
            return None
        return [item for item in self._history if item.sequence > cursor]

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[OperationsEvent]]:
        queue: asyncio.Queue[OperationsEvent] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
