# simcore22/engine/scorecard_watch.py
"""Notices GSPro's end-of-round scorecard on screen and hands it over exactly once."""
import asyncio
import inspect
import logging
import time
from typing import Awaitable, Callable, Union

import numpy as np

from simcore22.engine.ocr.scorecard import read_scorecard_from_image
from simcore22.engine.ocr.scorecard_reader import looks_like_scorecard_panel

logger = logging.getLogger(__name__)

CardHandler = Callable[[dict, np.ndarray], Union[None, Awaitable[None]]]


class ScorecardWatcher:
    """
    Fed every good frame. When GSPro's end-of-round scorecard is on screen it
    reads it once and calls `on_final_card(card, frame)`.

    Cheap test first (looks_like_scorecard_panel, milliseconds): only a big
    light panel in the middle of the screen is worth the ~5s full read, and it
    must be there on two polls in a row (the card may animate in). A panel that
    turns out not to be a scorecard (bright sky) is not re-read for a few
    seconds. The read runs in a worker thread so the engine keeps processing
    events. A scorecard WITHOUT the PLAY AGAIN! button is a mid-round view and
    is ignored. After a card is handled it is not read again until it has left
    the screen.
    """

    RETRY_AFTER_NON_CARD_S = 5.0

    def __init__(self, on_final_card: CardHandler):
        self.on_final_card = on_final_card
        self._handled = False        # this on-screen card was already processed
        self._present_polls = 0      # consecutive polls with a card-like panel
        self._absent_polls = 0       # consecutive polls without one (after handling)
        self._retry_after = 0.0      # monotonic time before re-reading a non-card

    async def check(self, frame: np.ndarray) -> None:
        present = looks_like_scorecard_panel(frame)

        if self._handled:
            self._absent_polls = 0 if present else self._absent_polls + 1
            if self._absent_polls >= 3:
                self._handled = False
                self._present_polls = 0
            return

        if not present:
            self._present_polls = 0
            return

        self._present_polls += 1
        if self._present_polls < 2 or time.monotonic() < self._retry_after:
            return

        card = await asyncio.to_thread(read_scorecard_from_image, frame)
        if not card or not card.get("players"):
            self._retry_after = time.monotonic() + self.RETRY_AFTER_NON_CARD_S
            return

        self._handled = True
        self._absent_polls = 0
        if not card.get("round_complete"):
            logger.info("A scorecard is on screen without PLAY AGAIN! - "
                        "treating it as a mid-round view and ignoring it.")
            return

        logger.info("End-of-round scorecard detected.")
        result = self.on_final_card(card, frame)
        if inspect.isawaitable(result):
            await result
