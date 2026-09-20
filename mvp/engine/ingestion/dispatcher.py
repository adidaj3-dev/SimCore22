# mvp/engine/ingestion/dispatcher.py
import asyncio
from collections import deque
from typing import Deque, Optional, Union, Callable, List

from mvp.engine.models.events import ShotEvent, PlayerEvent, HoleEvent, ScoreEvent

Event = Union[ShotEvent, PlayerEvent, HoleEvent, ScoreEvent]


class EventDispatcher:
    """
    Central event bus for SimCore22.
    - Ingestion sources push events in
    - Engine loop pulls events out
    - UI listeners receive events immediately
    """

    def __init__(self) -> None:
        # Queue for engine loop
        self._queue: Deque[Event] = deque()
        self._event_available = asyncio.Event()

        # Listener callbacks (dashboard, etc.)
        self._listeners: List[Callable[[Event], None]] = []

    def add_listener(self, callback: Callable[[Event], None]) -> None:
        """Register a callback that receives every event immediately."""
        self._listeners.append(callback)

    def emit(self, event: Event) -> None:
        """Push event into queue AND notify listeners."""
        # Queue behavior
        self._queue.append(event)
        self._event_available.set()

        # Notify listeners immediately
        for callback in self._listeners:
            try:
                callback(event)
            except Exception as e:
                print(f"[DISPATCHER] Listener error: {e}")

    async def next_event(self, timeout: Optional[float] = None) -> Optional[Event]:
        """Engine loop waits for next event from queue."""
        while not self._queue:
            self._event_available.clear()
            try:
                await asyncio.wait_for(self._event_available.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return None

        return self._queue.popleft()
