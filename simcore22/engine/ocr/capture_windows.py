import logging
import cv2
import mss
import numpy as np

from .window_capture import capture_window_frame

logger = logging.getLogger(__name__)


def _grab_monitor(monitor_index: int = 1) -> np.ndarray:
    """
    Capture a full frame from the given monitor index using MSS.
    Returns a BGR numpy array.
    """
    with mss.MSS() as sct:
        monitors = sct.monitors  # index 0 = all screens combined, 1 = primary

        # Validate index
        if monitor_index < 0 or monitor_index >= len(monitors):
            raise ValueError(
                f"Monitor index {monitor_index} not found. "
                f"Available indexes: 0 to {len(monitors)-1}"
            )

        mon = monitors[monitor_index]

        try:
            img = sct.grab(mon)
        except Exception:
            logger.exception(f"Failed to grab monitor {monitor_index}")
            raise

        frame = np.array(img)  # BGRA
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame


def capture_full_hud_frame_from_monitor(monitor_index: int = 1) -> np.ndarray:
    """
    Whole-monitor capture. Only correct if GSPro fills that monitor exactly;
    prefer capture_game_frame().
    """
    try:
        return _grab_monitor(monitor_index)
    except Exception:
        logger.exception("Failed to capture frame from monitor")
        raise


def capture_game_frame(window_title: str = "", monitor_index: int = 1) -> np.ndarray:
    """
    The frame the OCR layouts are measured against.

    With a window title: just that window's drawable area (borders, title bar
    and screen position don't matter). Raises GameWindowNotFound if it isn't
    open - callers treat that as "wait", not as an error. Without a title:
    the whole monitor, as before.
    """
    if window_title:
        return capture_window_frame(window_title)
    return capture_full_hud_frame_from_monitor(monitor_index)