# simcore22/tools/capture_screenshot.py
"""
Save one frame of the GSPro window (picture only - no title bar, borders or
other windows) as gspro_capture.png. This is the image ocr_calibration.py and
gspro_hud_autocrop_helper.py work from, and it's exactly what the engine's
OCR sees, so boxes you draw on it line up.

    python -m simcore22.tools.capture_screenshot
"""
import time

import cv2

from simcore22.engine import config
from simcore22.engine.ocr.capture_windows import capture_game_frame
from simcore22.engine.ocr.window_capture import GameWindowNotFound, looks_black


def main() -> int:
    target = f"window '{config.CAPTURE_WINDOW_TITLE}'" if config.CAPTURE_WINDOW_TITLE else "the monitor"
    print(f"Capturing {target} in 3 seconds... (bring GSPro to the front)")
    time.sleep(3)

    try:
        frame = capture_game_frame(config.CAPTURE_WINDOW_TITLE, config.CAPTURE_MONITOR_INDEX)
    except GameWindowNotFound as exc:
        print(f"Couldn't capture: {exc}")
        return 1

    if looks_black(frame):
        print("The capture is all black: GSPro is likely in exclusive fullscreen.")
        print("Switch it to Windowed / Borderless in its display settings and try again.")
        return 1

    cv2.imwrite("gspro_capture.png", frame)
    h, w = frame.shape[:2]
    print(f"Saved gspro_capture.png ({w}x{h})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
