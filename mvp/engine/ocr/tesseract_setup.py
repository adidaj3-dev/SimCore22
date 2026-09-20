# mvp/engine/ocr/tesseract_setup.py
"""
One place that finds tesseract.exe and points pytesseract at it.

Import this module (or call configure_tesseract()) before any OCR call. It
replaces the hard-coded C:\\Program Files\\... path that used to be copied into
preprocess.py and parsing.py.
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import pytesseract

logger = logging.getLogger(__name__)

_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

_configured: Optional[str] = None


def find_tesseract() -> Optional[str]:
    """Return the path to tesseract.exe, or None if it can't be found."""
    env = os.environ.get("TESSERACT_CMD")
    if env and Path(env).exists():
        return env

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    local = os.environ.get("LOCALAPPDATA")
    candidates = list(_CANDIDATES)
    if local:
        candidates.append(str(Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe"))

    for path in candidates:
        if Path(path).exists():
            return path
    return None


def configure_tesseract() -> str:
    """Point pytesseract at tesseract.exe. Raises a clear error if it's missing."""
    global _configured
    if _configured:
        return _configured

    path = find_tesseract()
    if path is None:
        raise RuntimeError(
            "Tesseract OCR is not installed. Install it with:\n"
            "    winget install tesseract-ocr.tesseract\n"
            "or set the TESSERACT_CMD environment variable to tesseract.exe."
        )

    pytesseract.pytesseract.tesseract_cmd = path
    _configured = path
    logger.info("Using Tesseract at %s", path)
    return path


# Configure on import so `import tesseract_setup` is enough.
try:
    configure_tesseract()
except RuntimeError as exc:  # keep imports working; OCR calls will fail loudly
    logger.warning("%s", exc)
