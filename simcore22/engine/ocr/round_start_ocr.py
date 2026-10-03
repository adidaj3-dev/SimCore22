# simcore22/engine/ocr/round_start_ocr.py
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from simcore22.engine.models.events import (
    PlayerEvent,
    HoleEvent,
    RoundStartEvent,
    RoundEndEvent,
)
from .course_cache import CourseMetadataCache

logger = logging.getLogger(__name__)


class RoundStartOCR:
    """
    High-level orchestrator that:
      - Loads course metadata (once)
      - Emits initial round events
    """

    def __init__(
        self,
        layout_dir: str,
        emit_callback: Callable[[Any], None],   # synchronous (EventDispatcher.emit)
    ):
        self.layout_dir = Path(layout_dir)
        self.emit = emit_callback
        self.cache = CourseMetadataCache()
        self.round_active = False

    async def start_round(self, player_name: str = "Player 1"):
        logger.info("=== STARTING OCR-ONLY ROUND ===")

        # Placeholder metadata; you can wire real scorecard OCR here later
        raw_data = {"course_name": "Unknown Course"}
        metadata = self.cache.get_metadata(raw_data["course_name"], raw_data)
        course_name = metadata.get("course_name", "Unknown Course")

        now = datetime.now()

        # emit() is synchronous - don't await it
        self.emit(RoundStartEvent(timestamp=now, course_name=course_name))
        self.emit(PlayerEvent(timestamp=now, player_name=player_name))
        self.emit(HoleEvent(timestamp=now, hole_number=1))

        self.round_active = True
        logger.info("OCR-only round initialized successfully.")

    async def end_round(self, reason: str = "completed"):
        if not self.round_active:
            return

        now = datetime.now()
        self.emit(RoundEndEvent(timestamp=now, reason=reason))

        self.round_active = False
