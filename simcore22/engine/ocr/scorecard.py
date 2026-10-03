# simcore22/engine/ocr/scorecard.py
import logging
from typing import Any, Dict

from .scorecard_reader import ScorecardReadError, read_scorecard

logger = logging.getLogger(__name__)


def read_scorecard_from_image(frame) -> Dict[str, Any]:
    """
    Read a GSPro scorecard screenshot (BGR array) into a plain dict:
    course name, par / stroke index per hole, and each player's hole scores.
    Returns {} if the image isn't a scorecard.
    """
    try:
        return read_scorecard(frame).to_dict()
    except ScorecardReadError as exc:
        logger.warning("Not a readable scorecard: %s", exc)
        return {}
