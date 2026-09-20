# mvp/engine/ocr/layout.py
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


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


@dataclass
class ScorecardLayout:
    scorecard: RelativeRect


def load_hud_layout(base_dir: Path | None = None) -> HUDLayout:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent / "layouts"

    path = base_dir / "gspro_hud.json"
    data = json.loads(path.read_text())

    def rr(obj):
        return RelativeRect(
            x1=obj["x1"], y1=obj["y1"], x2=obj["x2"], y2=obj["y2"]
        )

    return HUDLayout(
        player_name=rr(data["player_name"]),
        hole_number=rr(data["hole_number"]),
        hud=rr(data["hud"]),
    )


def load_scorecard_layout(base_dir: Path | None = None) -> ScorecardLayout:
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent / "layouts"

    path = base_dir / "gspro_scorecard.json"
    data = json.loads(path.read_text())

    def rr(obj):
        return RelativeRect(
            x1=obj["x1"], y1=obj["y1"], x2=obj["x2"], y2=obj["y2"]
        )

    return ScorecardLayout(scorecard=rr(data["scorecard"]))
