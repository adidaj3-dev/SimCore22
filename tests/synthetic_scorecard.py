"""
Draws GSPro-style scorecards for tests: dark title band, dark HOLE header row,
light table, circled (red) birdies, dark-square bogeys, PLAY AGAIN! button,
ROUND SETTINGS footer.

These are CLEANER than a real screen (no glare, no camera tilt), so they prove
the logic (layouts, partial rounds, checksums) - not OCR accuracy on real
cards. The only real GSPro card we have is simcore22/engine/ocr/samples/scorecard.png.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = Path(r"C:\Windows\Fonts")
FONTS_AVAILABLE = (_FONT_DIR / "arial.ttf").exists() and (_FONT_DIR / "arialbd.ttf").exists()

W, H = 2000, 1100
PARS = [4, 4, 5, 3, 4, 4, 5, 3, 4, 4, 5, 4, 3, 4, 5, 3, 4, 5]
INDEX = [11, 9, 3, 15, 5, 13, 1, 17, 7, 12, 4, 8, 18, 14, 6, 16, 10, 2]
YARDS = [362, 360, 467, 162, 395, 279, 517, 156, 390, 296, 477, 353, 109, 280, 448, 139, 364, 488]


def _font(size: int, bold: bool = False):
    return ImageFont.truetype(str(_FONT_DIR / ("arialbd.ttf" if bold else "arial.ttf")), size)


def _centered(draw, xy: Tuple[float, float], text: str, font, fill):
    draw.text(xy, text, font=font, fill=fill, anchor="mm")


def render_scorecard(
    holes: int = 18,
    players: Sequence[Tuple[str, Dict[int, int]]] = (("JOESLAT", {}),),
    course: str = "TEST LINKS",
    play_again: bool = True,
    label_total: bool = True,       # 9-hole card: does the header label the TOT column?
    out_override: Optional[int] = None,  # print a WRONG OUT total (to test checksum failure)
) -> np.ndarray:
    """
    holes=18: columns 1-9, OUT, 10-18, IN, (unlabelled total) - like the real card.
    holes=9 : columns 1-9, OUT, [TOT].
    `players` is [(name, {hole: strokes})]; a player may have played only some holes.
    Returns a BGR array.
    """
    img = Image.new("RGB", (W, H), (45, 50, 55))
    d = ImageDraw.Draw(img)

    if holes == 18:
        labels = [str(n) for n in range(1, 10)] + ["OUT"] + [str(n) for n in range(10, 19)] + ["IN", ""]
        x0, pitch = 420, 72
    else:
        labels = [str(n) for n in range(1, 10)] + ["OUT"] + (["TOT"] if label_total else [])
        x0, pitch = 430, 120

    def col(i):
        return x0 + i * pitch

    def hole_col(n):  # column index of hole n
        return (n - 1) if n <= 9 else n  # holes 10-18 sit after OUT

    # title band, header band, light table
    d.rectangle((60, 100, 1940, 230), fill=(20, 20, 20))
    d.text((115, 140), course, font=_font(44, True), fill="white")
    d.text((850, 135), "SCORECARD", font=_font(44, True), fill="white")
    if play_again:
        d.rounded_rectangle((1250, 120, 1520, 200), 20, fill=(40, 42, 48))
        d.text((1290, 135), "PLAY AGAIN!", font=_font(34, True), fill="white")
    d.rounded_rectangle((1560, 115, 1830, 205), 25, fill=(30, 100, 220))
    d.text((1600, 135), "STATISTICS", font=_font(34, True), fill="white")
    d.rectangle((60, 230, 1940, 330), fill=(35, 35, 35))
    d.rectangle((60, 330, 1940, 900), fill=(238, 238, 238))
    d.text((120, 265), "HOLE", font=_font(32, True), fill="white")
    for i, label in enumerate(labels):
        if label:
            _centered(d, (col(i), 282), label, _font(34, True), "white")

    ink = (70, 70, 70)
    shown = range(1, holes + 1)
    for row_y, name, values in (
        (410, "PAR", PARS), (490, "INDEX", INDEX), (570, "DISTANCE", YARDS),
    ):
        d.text((125, row_y - 18), name, font=_font(30), fill=ink)
        for n in shown:
            _centered(d, (col(hole_col(n)), row_y), str(values[n - 1]), _font(34), ink)

    for p, (pname, scores) in enumerate(players):
        y = 670 + p * 90
        d.text((130, y - 18), pname, font=_font(32), fill=ink)
        for n, strokes in scores.items():
            cx, par = col(hole_col(n)), PARS[n - 1]
            if strokes < par:      # birdie or better: white digit on a red disc
                d.ellipse((cx - 26, y - 26, cx + 26, y + 26), fill=(170, 30, 40))
                _centered(d, (cx, y), str(strokes), _font(34, True), "white")
            elif strokes > par:    # over par: white digit on a dark square
                d.rectangle((cx - 24, y - 24, cx + 24, y + 24), fill=(50, 50, 55))
                _centered(d, (cx, y), str(strokes), _font(34, True), "white")
            else:
                _centered(d, (cx, y), str(strokes), _font(34), ink)
        out = sum(v for n, v in scores.items() if n <= 9)
        back = sum(v for n, v in scores.items() if n >= 10)
        if scores:
            _centered(d, (col(9), y), str(out_override if out_override is not None else out), _font(34), ink)
            if holes == 18:
                if back:
                    _centered(d, (col(19), y), str(back), _font(34), ink)
                _centered(d, (col(20), y), str(out + back), _font(34), ink)
            elif label_total:
                _centered(d, (col(10), y), str(out), _font(34), ink)

    d.rectangle((60, 930, 1940, 980), fill=(30, 30, 30))
    d.text((90, 938), "ROUND SETTINGS", font=_font(30, True), fill="white")
    d.rectangle((60, 980, 1940, 1060), fill=(238, 238, 238))
    d.text((90, 1005), "GAME TYPE: STROKE PLAY     STIMP: 11     TEES: White", font=_font(26), fill=ink)

    return np.array(img)[:, :, ::-1].copy()  # RGB -> BGR
