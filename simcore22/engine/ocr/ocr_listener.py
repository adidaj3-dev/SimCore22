# simcore22/engine/ocr/ocr_listener.py
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import numpy as np

from simcore22.engine.models.events import (
    ShotEvent,
    PlayerEvent,
    HoleEvent,
)
from .hud_crops import (
    capture_hud_frame_from_image,
    capture_player_name_frame_from_image,
    capture_hole_number_frame_from_image,
)
from .parsing import (
    parse_player_name,
    parse_hole_number,
    parse_shot_tiles,
)

logger = logging.getLogger(__name__)


@dataclass
class HudReading:
    """What one frame of the HUD says (nothing is emitted from this)."""
    player_name: Optional[str] = None
    hole_number: Optional[int] = None
    shot_data: Dict[str, Any] = field(default_factory=dict)


class OCRHudListener:
    """
    Reads the HUD from frames and emits engine events (player changed, hole
    changed, shot). Frames come from a capture loop.

    Reading a frame is slow (Tesseract), so it runs in a worker thread
    (`read_frame`); the events are emitted back on the event-loop thread
    (`publish`), because the event bus is not thread-safe.
    """

    def __init__(
        self,
        emit_callback: Callable[[Any], None],   # synchronous (EventDispatcher.emit)
        base_dir: Path | None = None,
        poll_interval: float = 1.0,
    ):
        self.emit = emit_callback
        self.base_dir = base_dir
        self.poll_interval = poll_interval

        self._last_player: Optional[str] = None
        self._last_hole: Optional[int] = None

    async def process_frame(self, frame: np.ndarray) -> None:
        """Read the frame without blocking the event loop, then emit what changed."""
        try:
            reading = await asyncio.to_thread(self.read_frame, frame)
            self.publish(reading)
        except Exception:
            logger.exception("OCRHudListener.process_frame failed")

    def read_frame(self, frame: np.ndarray) -> HudReading:
        """The slow part: OCR the HUD regions. Touches no shared state, so it is thread-safe."""
        # Crops are passed RAW: the parse_* functions preprocess exactly once.
        # (Preprocessing here too thresholded the image twice and garbled text.)
        player_img = capture_player_name_frame_from_image(frame, base_dir=self.base_dir, preprocess=False)
        hole_img = capture_hole_number_frame_from_image(frame, base_dir=self.base_dir, preprocess=False)
        hud_img = capture_hud_frame_from_image(frame, base_dir=self.base_dir, preprocess=False)
        return HudReading(
            player_name=parse_player_name(player_img),
            hole_number=parse_hole_number(hole_img),
            shot_data=parse_shot_tiles(hud_img),
        )

    def publish(self, reading: HudReading) -> None:
        """Emit events for whatever changed since the last reading."""
        if reading.player_name and reading.player_name != self._last_player:
            self._last_player = reading.player_name
            self.emit(PlayerEvent(timestamp=datetime.now(), player_name=reading.player_name))

        if reading.hole_number and reading.hole_number != self._last_hole:
            self._last_hole = reading.hole_number
            self.emit(HoleEvent(timestamp=datetime.now(), hole_number=reading.hole_number))

        if reading.shot_data:
            self._emit_shot_event(reading.shot_data)

    def _emit_shot_event(self, data: Dict[str, Any]) -> None:
        event = ShotEvent(
            source_device="OCR",
            timestamp=datetime.now(),
            ball_speed=data.get("ball_speed"),
            launch_angle=data.get("launch_angle"),
            azimuth=data.get("azimuth"),
            spin_rate=data.get("spin_rate") or data.get("spin"),
            spin_axis=data.get("spin_axis"),
            total_spin=data.get("total_spin"),
            club_speed=data.get("club_speed"),
            carry_distance=data.get("carry") or data.get("carry_distance"),
            total_distance=data.get("total") or data.get("total_distance"),
            curve=data.get("curve"),
            direction=data.get("direction"),
            apex=data.get("apex"),
            metadata={
                "raw": data.get("raw"),
                "hole_number": self._last_hole,
                "player_name": self._last_player,
            },
        )
        self.emit(event)
