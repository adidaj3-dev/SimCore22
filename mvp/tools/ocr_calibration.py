# mvp/tools/ocr_calibration.py
"""
Draw the HUD regions on a real GSPro frame and save them as the OCR layout.

    python -m mvp.tools.capture_screenshot     # first: saves gspro_capture.png
    python -m mvp.tools.ocr_calibration

You'll be asked to drag a box (then press ENTER) for each region:
  player_name  - the player's name, top-left of the HUD
  hole_number  - the hole number
  hud          - the block of shot-stat tiles (ball speed, carry, spin, ...)
Press C to skip/cancel a region. Boxes are saved as FRACTIONS of the picture
in mvp/engine/ocr/layouts/gspro_hud.json, so they keep working if GSPro runs
at a different size.
"""
import json
from pathlib import Path

import cv2

LAYOUT_FILE = Path(__file__).resolve().parents[1] / "engine" / "ocr" / "layouts" / "gspro_hud.json"
REGIONS = [
    ("player_name", "the PLAYER NAME"),
    ("hole_number", "the HOLE NUMBER"),
    ("hud", "the block of SHOT STAT TILES"),
]
MAX_VIEW_WIDTH = 1400  # shrink big captures so the selection window fits the screen


def main() -> int:
    img = cv2.imread("gspro_capture.png")
    if img is None:
        print("Could not find gspro_capture.png. Run: python -m mvp.tools.capture_screenshot")
        return 1

    h, w = img.shape[:2]
    view_scale = min(1.0, MAX_VIEW_WIDTH / w)
    view = cv2.resize(img, None, fx=view_scale, fy=view_scale) if view_scale < 1 else img
    print(f"Image is {w}x{h}.")

    layout = {}
    for key, label in REGIONS:
        x, y, bw, bh = cv2.selectROI(f"Drag a box around {label}, then press ENTER", view)
        cv2.destroyAllWindows()
        if bw == 0 or bh == 0:
            print(f"  skipped {key}")
            continue
        # back to full-size pixels, then to fractions of the picture
        x1, y1 = x / view_scale, y / view_scale
        x2, y2 = (x + bw) / view_scale, (y + bh) / view_scale
        layout[key] = {
            "x1": round(x1 / w, 4), "y1": round(y1 / h, 4),
            "x2": round(x2 / w, 4), "y2": round(y2 / h, 4),
        }
        print(f"  {key}: {layout[key]}")

    if not layout:
        print("Nothing selected; layout unchanged.")
        return 0

    # keep any region you skipped as it was
    current = json.loads(LAYOUT_FILE.read_text()) if LAYOUT_FILE.exists() else {}
    current.update(layout)
    answer = input(f"\nSave these to {LAYOUT_FILE.name}? [y/N] ").strip().lower()
    if answer == "y":
        LAYOUT_FILE.write_text(json.dumps(current, indent=2) + "\n")
        print("Saved.")
    else:
        print("Not saved. Layout unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
