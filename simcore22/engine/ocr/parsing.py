# simcore22/engine/ocr/parsing.py
import logging
from typing import Dict, Any, Optional

import numpy as np
import pytesseract

from . import tesseract_setup  # noqa: F401  (finds tesseract.exe)
from .preprocess import preprocess_for_ocr

logger = logging.getLogger(__name__)


def _ocr_text(img: np.ndarray, config: str) -> str:
    try:
        text = pytesseract.image_to_string(img, config=config)
        return text.strip()
    except Exception:
        logger.exception("OCR failed")
        return ""


def parse_player_name(img: np.ndarray) -> Optional[str]:
    img_p = preprocess_for_ocr(img)
    text = _ocr_text(img_p, "--psm 7")
    return text or None


def parse_hole_number(img: np.ndarray) -> Optional[int]:
    img_p = preprocess_for_ocr(img)
    text = _ocr_text(img_p, "--psm 7")
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def parse_shot_tiles(img: np.ndarray) -> Dict[str, Any]:
    """
    Placeholder: parse HUD tiles into structured shot data.
    For now, returns an empty dict or fake data if needed.
    """
    # You can wire real tile parsing here later.
    return {}
