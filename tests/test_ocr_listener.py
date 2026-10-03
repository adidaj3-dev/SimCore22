import asyncio
import time

import numpy as np

from simcore22.engine.models.events import HoleEvent, PlayerEvent
from simcore22.engine.ocr.ocr_listener import HudReading, OCRHudListener


def _listener():
    events = []
    return OCRHudListener(emit_callback=events.append), events


def test_events_are_emitted_only_when_something_changes():
    listener, events = _listener()

    listener.publish(HudReading(player_name="Sam", hole_number=1))
    assert [type(e) for e in events] == [PlayerEvent, HoleEvent]

    listener.publish(HudReading(player_name="Sam", hole_number=1))   # same screen again
    assert len(events) == 2

    listener.publish(HudReading(player_name="Sam", hole_number=2))   # next hole
    assert isinstance(events[-1], HoleEvent) and events[-1].hole_number == 2

    listener.publish(HudReading(player_name="Alex", hole_number=2))  # next player
    assert isinstance(events[-1], PlayerEvent) and events[-1].player_name == "Alex"


def test_an_unreadable_frame_emits_nothing():
    listener, events = _listener()
    listener.publish(HudReading())
    assert events == []


def test_reading_a_frame_does_not_freeze_the_event_loop(monkeypatch):
    """OCR takes real time; the engine must keep handling events and commands meanwhile."""
    listener, events = _listener()

    def slow_read(frame):
        time.sleep(0.6)  # stand-in for Tesseract
        return HudReading(player_name="Sam", hole_number=1)

    monkeypatch.setattr(listener, "read_frame", slow_read)
    ticks = []

    async def ticker():
        while True:
            ticks.append(1)
            await asyncio.sleep(0.05)

    async def go():
        task = asyncio.create_task(ticker())
        await listener.process_frame(np.zeros((10, 10, 3), np.uint8))
        task.cancel()

    asyncio.run(go())

    assert len(ticks) >= 8                     # the loop kept running during the 0.6s read
    assert [type(e) for e in events] == [PlayerEvent, HoleEvent]  # ...and the result was still emitted


def test_a_failing_read_is_logged_not_raised(monkeypatch):
    listener, events = _listener()

    def boom(frame):
        raise RuntimeError("tesseract exploded")

    monkeypatch.setattr(listener, "read_frame", boom)
    asyncio.run(listener.process_frame(np.zeros((10, 10, 3), np.uint8)))  # must not raise
    assert events == []
