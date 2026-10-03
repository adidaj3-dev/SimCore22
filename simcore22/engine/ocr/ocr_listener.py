# simcore22/engine/ocr/ocr_listener.py
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Any, Dict

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


class OCRHudListener:
    """
    Polls HUD frames, runs OCR, and emits engine events.
    This version assumes you provide frames (e.g., from a capture loop).
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
        self._running = False

        self._last_player: Optional[str] = None
        self._last_hole: Optional[int] = None

    async def process_frame(self, frame: np.ndarray):
        """
        Call this from your capture loop with the latest HUD frame.
        """
        # Crops are passed RAW: the parse_* functions preprocess exactly once.
        # (Preprocessing here too thresholded the image twice and garbled text.)
        try:
            # Player
            player_img = capture_player_name_frame_from_image(
                frame, base_dir=self.base_dir, preprocess=False
            )
            player_name = parse_player_name(player_img)
            if player_name and player_name != self._last_player:
                self._last_player = player_name
                self.emit(
                    PlayerEvent(
                        timestamp=datetime.now(),
                        player_name=player_name,
                    )
                )

            # Hole
            hole_img = capture_hole_number_frame_from_image(
                frame, base_dir=self.base_dir, preprocess=False
            )
            hole_number = parse_hole_number(hole_img)
            if hole_number and hole_number != self._last_hole:
                self._last_hole = hole_number
                self.emit(
                    HoleEvent(
                        timestamp=datetime.now(),
                        hole_number=hole_number,
                    )
                )

            # Shot tiles
            hud_img = capture_hud_frame_from_image(
                frame, base_dir=self.base_dir, preprocess=False
            )
            shot_data: Dict[str, Any] = parse_shot_tiles(hud_img)

            if shot_data:
                self._emit_shot_event(shot_data)

        except Exception:
            logger.exception("OCRHudListener.process_frame failed")

    def _emit_shot_event(self, data: Dict[str, Any]):
        ts = datetime.now()
        event = ShotEvent(
            source_device="OCR",
            timestamp=ts,
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
