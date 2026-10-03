# simcore22/engine/ocr/layout.py
"""
Where the HUD regions sit on the GSPro picture, as FRACTIONS of the picture
(so they keep working at any window size). Edit with:

    python -m simcore22.tools.ocr_calibration

The scorecard needs no layout: scorecard_reader.py finds its own table.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

LAYOUT_DIR = Path(__file__).resolve().parent / "layouts"


@dataclass
class RelativeRect:
    x1: float
    y1: float
    x2: float
    y2: float

    def to_pixels(self, width: int, height: int) -> Tuple[int, int, int, int]:
        return (
            int(self.x1 * width),
            int(self.y1 * height),
            int(self.x2 * width),
            int(self.y2 * height),
        )


@dataclass
class HUDLayout:
    player_name: RelativeRect
    hole_number: RelativeRect
    hud: RelativeRect


def _rect(obj: dict) -> RelativeRect:
    return RelativeRect(x1=obj["x1"], y1=obj["y1"], x2=obj["x2"], y2=obj["y2"])


def load_hud_layout(base_dir: Path | None = None) -> HUDLayout:
    path = (base_dir or LAYOUT_DIR) / "gspro_hud.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return HUDLayout(
        player_name=_rect(data["player_name"]),
        hole_number=_rect(data["hole_number"]),
        hud=_rect(data["hud"]),
    )
