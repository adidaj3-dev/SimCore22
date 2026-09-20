import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable

from mvp.engine.ocr.course_cache import CourseMetadataCache
from mvp.engine.models.events import (
    PlayerEvent,
    HoleEvent,
    ScoreEvent,
    RoundStartEvent,
    RoundEndEvent
)

logger = logging.getLogger(__name__)


class RoundInitializer:
    """
    Handles round start/reset logic for OCR-only mode.
    Ensures the engine, UI, and OCR pipeline begin each round cleanly.
    """

    def __init__(
        self,
        layout_dir: str,
        monitor_index: int = 1,
        emit_callback: Optional[Callable[[object], Awaitable[None]]] = None
    ):
        self.layout_dir = Path(layout_dir)
        self.monitor_index = monitor_index
        self.emit = emit_callback

        self.cache = CourseMetadataCache()
        self.round_active = False
        self.current_hole = None
        self.current_player = None

    # ---------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------

    async def start_new_round(self, player_name: str = "Player 1"):
        """
        Fully resets the round state and emits a RoundStartEvent.
        """

        logger.info("=== INITIALIZING NEW ROUND ===")

        # Reset state
        self.round_active = True
        self.current_hole = 1
        self.current_player = player_name

        # Load course metadata (OCRs scorecard once if needed)
        scorecard_layout = str(self.layout_dir / "gspro_scorecard.json")
        metadata = self.cache.get_metadata(scorecard_layout, self.monitor_index)

        logger.info(f"Loaded course metadata: {metadata.get('course_name', 'Unknown')}")

        # Emit events
        if self.emit:
            await self.emit(RoundStartEvent(course=metadata.get("course_name", "Unknown")))
            await self.emit(PlayerEvent(name=player_name))
            await self.emit(HoleEvent(hole=1))

        logger.info("Round initialized successfully.")

    async def end_round(self):
        """
        Ends the round and emits a RoundEndEvent.
        """

        if not self.round_active:
            logger.warning("end_round() called but no round is active.")
            return

        logger.info("=== ENDING ROUND ===")

        if self.emit:
            await self.emit(RoundEndEvent())

        # Reset internal state
        self.round_active = False
        self.current_hole = None
        self.current_player = None

        logger.info("Round ended successfully.")

    # ---------------------------------------------------------
    # HOLE ADVANCEMENT
    # ---------------------------------------------------------

    async def advance_hole(self):
        """
        Moves to the next hole and emits a HoleEvent.
        """

        if not self.round_active:
            logger.warning("advance_hole() called but no round is active.")
            return

        self.current_hole += 1

        if self.current_hole > 18:
            await self.end_round()
            return

        logger.info(f"Advancing to hole {self.current_hole}")

        if self.emit:
            await self.emit(HoleEvent(hole=self.current_hole))

    # ---------------------------------------------------------
    # SCORE HANDLING
    # ---------------------------------------------------------

    async def record_score(self, strokes: int):
        """
        Records a score for the current hole and emits a ScoreEvent.
        """

        if not self.round_active:
            logger.warning("record_score() called but no round is active.")
            return

        if self.emit:
            await self.emit(ScoreEvent(hole=self.current_hole, strokes=strokes))

        logger.info(f"Recorded score for hole {self.current_hole}: {strokes}")

        # Automatically advance to next hole
        await self.advance_hole()
