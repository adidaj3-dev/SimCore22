# mvp/engine/ocr/scorecard.py
import logging
from pathlib import Path
from typing import Dict, Any

import cv2

from .capture import capture_scorecard_frame_from_image
from .preprocess import preprocess_for_ocr
from .preprocess import simple_ocr

logger = logging.getLogger(__name__)


def read_scorecard_from_image(
    frame,
    base_dir: Path | None = None,
) -> Dict[str, Any]:
    """
    Very simple placeholder scorecard reader.
    You can expand this to parse per-hole par/yardage later.
    """
    img = capture_scorecard_frame_from_image(frame, base_dir=base_dir, preprocess=True)
    text = simple_ocr(img, config="--psm 6")
    return {
        "course_name": "Unknown Course",
        "raw_text": text,
    }
