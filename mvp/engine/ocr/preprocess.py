# mvp/engine/ocr/preprocess.py
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Basic denoise + grayscale + adaptive threshold for OCR.
    Expects a BGR image. Apply it ONCE: running it on an already-thresholded
    image destroys the text (parsing.py applies it, so callers pass raw crops).
    """
    try:
        if image.ndim == 3 and image.shape[2] == 4:
            image = image[:, :, :3]

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.medianBlur(gray, 3)
        return cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2,
        )
    except Exception:
        logger.exception("preprocess_for_ocr failed")
        return image
