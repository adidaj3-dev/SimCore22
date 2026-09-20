# mvp/engine/ocr/capture.py
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .layout import load_hud_layout, load_scorecard_layout
from .preprocess import preprocess_for_ocr

logger = logging.getLogger(__name__)


def _ensure_frame(frame: Any) -> np.ndarray:
    if isinstance(frame, np.ndarray):
        return frame
    raise TypeError("frame must be a numpy.ndarray (BGR)")


def capture_hud_frame_from_image(
    frame: Any,
    base_dir: Path | None = None,
    preprocess: bool = True,
) -> np.ndarray:
    img = _ensure_frame(frame)
    h, w = img.shape[:2]
    layout = load_hud_layout(base_dir=base_dir)
    x1, y1, x2, y2 = layout.hud.to_pixels(w, h)
    crop = img[y1:y2, x1:x2]
    return preprocess_for_ocr(crop) if preprocess else crop


def capture_player_name_frame_from_image(
    frame: Any,
    base_dir: Path | None = None,
    preprocess: bool = True,
) -> np.ndarray:
    img = _ensure_frame(frame)
    h, w = img.shape[:2]
    layout = load_hud_layout(base_dir=base_dir)
    x1, y1, x2, y2 = layout.player_name.to_pixels(w, h)
    crop = img[y1:y2, x1:x2]
    return preprocess_for_ocr(crop) if preprocess else crop


def capture_hole_number_frame_from_image(
    frame: Any,
    base_dir: Path | None = None,
    preprocess: bool = True,
) -> np.ndarray:
    img = _ensure_frame(frame)
    h, w = img.shape[:2]
    layout = load_hud_layout(base_dir=base_dir)
    x1, y1, x2, y2 = layout.hole_number.to_pixels(w, h)
    crop = img[y1:y2, x1:x2]
    return preprocess_for_ocr(crop) if preprocess else crop


def capture_scorecard_frame_from_image(
    frame: Any,
    base_dir: Path | None = None,
    preprocess: bool = True,
) -> np.ndarray:
    img = _ensure_frame(frame)
    h, w = img.shape[:2]
    layout = load_scorecard_layout(base_dir=base_dir)
    x1, y1, x2, y2 = layout.scorecard.to_pixels(w, h)
    crop = img[y1:y2, x1:x2]
    return preprocess_for_ocr(crop) if preprocess else crop
