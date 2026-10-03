# mvp/engine/ocr/hud_crops.py
"""Cut the HUD regions (player name, hole number, shot tiles) out of a game frame."""
from pathlib import Path
from typing import Any

import numpy as np

from .layout import load_hud_layout
from .preprocess import preprocess_for_ocr


def _crop(frame: Any, region: str, base_dir: Path | None, preprocess: bool) -> np.ndarray:
    if not isinstance(frame, np.ndarray):
        raise TypeError("frame must be a numpy.ndarray (BGR)")
    height, width = frame.shape[:2]
    rect = getattr(load_hud_layout(base_dir=base_dir), region)
    x1, y1, x2, y2 = rect.to_pixels(width, height)
    crop = frame[y1:y2, x1:x2]
    return preprocess_for_ocr(crop) if preprocess else crop


def capture_hud_frame_from_image(frame: Any, base_dir: Path | None = None, preprocess: bool = True) -> np.ndarray:
    return _crop(frame, "hud", base_dir, preprocess)


def capture_player_name_frame_from_image(frame: Any, base_dir: Path | None = None, preprocess: bool = True) -> np.ndarray:
    return _crop(frame, "player_name", base_dir, preprocess)


def capture_hole_number_frame_from_image(frame: Any, base_dir: Path | None = None, preprocess: bool = True) -> np.ndarray:
    return _crop(frame, "hole_number", base_dir, preprocess)
