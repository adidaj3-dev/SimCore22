# mvp/engine/ocr/reader.py
import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .capture import (
    capture_player_name_frame_from_image,
    capture_hole_number_frame_from_image,
)
from .parsing import parse_player_name, parse_hole_number

logger = logging.getLogger(__name__)


def _ensure_frame(frame: Any) -> np.ndarray:
    if isinstance(frame, np.ndarray):
        return frame
    raise TypeError("frame must be a numpy.ndarray (BGR)")


def read_current_player_name(
    frame: Any,
    base_dir: Path | None = None,
) -> Optional[str]:
    try:
        img = _ensure_frame(frame)
        crop = capture_player_name_frame_from_image(img, base_dir=base_dir, preprocess=True)
        return parse_player_name(crop)
    except Exception:
        logger.exception("Failed to read current player name")
        return None


def read_current_hole_number(
    frame: Any,
    base_dir: Path | None = None,
) -> Optional[int]:
    try:
        img = _ensure_frame(frame)
        crop = capture_hole_number_frame_from_image(img, base_dir=base_dir, preprocess=True)
        return parse_hole_number(crop)
    except Exception:
        logger.exception("Failed to read current hole number")
        return None
