# mvp/engine/ocr/preprocess.py
import logging
from typing import Callable

import cv2
import numpy as np
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

logger = logging.getLogger(__name__)

OCRFunc = Callable[[np.ndarray], str]


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Basic denoise + grayscale + adaptive threshold for OCR.
    Expects BGR image.
    """
    try:
        if image.ndim == 3 and image.shape[2] == 4:
            image = image[:, :, :3]

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.medianBlur(gray, 3)
        thresh = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2,
        )
        return thresh
    except Exception:
        logger.exception("preprocess_for_ocr failed")
        return image


def simple_ocr(img: np.ndarray, config: str = "--psm 7") -> str:
    """
    Minimal OCR helper for debugging or fallback use.
    Not used by the main OCR pipeline.
    """
    try:
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        text = pytesseract.image_to_string(thresh, config=config)
        return text.strip()
    except Exception:
        logger.exception("simple_ocr failed")
        return ""
