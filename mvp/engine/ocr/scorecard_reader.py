# mvp/engine/ocr/scorecard_reader.py
"""
Reads a GSPro scorecard screenshot into structured data.

Instead of fixed pixel boxes, it finds the table from the text itself:

  1. OCR the whole card once to locate the row labels (HOLE / PAR / INDEX /
     DISTANCE / player names) and the hole-number header.
  2. Fit the column grid to the header numbers. GSPro columns are evenly spaced
     (1-9, OUT, 10-18, IN, TOT), so a missed header digit doesn't matter.
  3. OCR each cell individually (upscaled, digits only). Circled scores
     (white on red) are handled by auto-inverting light-on-dark cells.
  4. Use the OUT / IN / TOT columns as checksums. A player whose hole scores
     don't add up to the totals is flagged `verified=False`.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pytesseract

from . import tesseract_setup  # noqa: F401  (configures pytesseract)

logger = logging.getLogger(__name__)

# Standard 18-hole GSPro layout: 9 holes, OUT, 9 holes, IN, TOT
_COLUMN_KEYS: List[str] = (
    [str(n) for n in range(1, 10)] + ["OUT"] + [str(n) for n in range(10, 19)] + ["IN", "TOT"]
)
_ROW_LABELS = {"HOLE", "PAR", "INDEX", "DISTANCE"}
_WORK_WIDTH = 2000  # scorecard is analysed at this width
_POOL = ThreadPoolExecutor(max_workers=8)


@dataclass
class PlayerCard:
    name: str
    strokes: Dict[int, int] = field(default_factory=dict)   # hole -> gross strokes
    out_total: Optional[int] = None
    in_total: Optional[int] = None
    total: Optional[int] = None
    verified: bool = False  # hole scores match the printed OUT/IN/TOT

    @property
    def gross(self) -> int:
        return sum(self.strokes.values())


@dataclass
class ScorecardData:
    course_name: Optional[str] = None
    par: Dict[int, int] = field(default_factory=dict)
    stroke_index: Dict[int, int] = field(default_factory=dict)
    distance: Dict[int, int] = field(default_factory=dict)
    players: List[PlayerCard] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "course_name": self.course_name,
            "par": self.par,
            "stroke_index": self.stroke_index,
            "distance": self.distance,
            "players": [
                {
                    "name": p.name,
                    "strokes": p.strokes,
                    "out": p.out_total,
                    "in": p.in_total,
                    "total": p.total,
                    "gross": p.gross,
                    "verified": p.verified,
                }
                for p in self.players
            ],
        }


@dataclass
class _Word:
    text: str
    x: float   # centre
    y: float   # centre
    w: float
    h: float
    conf: float


class ScorecardReadError(RuntimeError):
    """The image doesn't look like a GSPro scorecard."""


# ---------------------------------------------------------------- OCR helpers

def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        img = img[:, :, :3]
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _ocr_words(gray: np.ndarray, psm: int = 11, min_conf: float = 30) -> List[_Word]:
    data = pytesseract.image_to_data(
        gray, config=f"--psm {psm}", output_type=pytesseract.Output.DICT
    )
    words: List[_Word] = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        conf = float(data["conf"][i])
        if conf < min_conf:
            continue
        w, h = float(data["width"][i]), float(data["height"][i])
        words.append(
            _Word(text, data["left"][i] + w / 2, data["top"][i] + h / 2, w, h, conf)
        )
    return words


def _read_number(cell: np.ndarray, lo: int, hi: int) -> Optional[int]:
    """
    OCR one table cell as an integer in [lo, hi]. Tries a few binarisations
    and returns the value most of them agree on.
    """
    if cell.size == 0:
        return None

    cell = cv2.resize(cell, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    cell = cv2.copyMakeBorder(cell, 12, 12, 12, 12, cv2.BORDER_REPLICATE)

    _, otsu = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Tesseract wants dark text on a light background. If the border of the
    # cell is dark (e.g. white digit inside a red circle), flip it.
    border = np.concatenate([otsu[0, :], otsu[-1, :], otsu[:, 0], otsu[:, -1]])
    if border.mean() < 127:
        otsu = cv2.bitwise_not(otsu)

    def attempt(image: np.ndarray, psm: int) -> Optional[int]:
        text = pytesseract.image_to_string(
            image, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789"
        ).strip()
        if text.isdigit() and lo <= int(text) <= hi:
            return int(text)
        return None

    # Fast path: one clean read. Only fall back to voting when it fails.
    first = attempt(otsu, 7)
    if first is not None:
        return first

    # Circled score (white digit on a dark disc on a light card): Otsu leaves a
    # black disc with a white digit. Invert, then flood the outside so the digit
    # is black on an all-white background.
    disc = cv2.bitwise_not(otsu)
    if disc[0, 0] == 0:
        cv2.floodFill(disc, None, (0, 0), 255)
    for psm in (10, 7):
        value = attempt(disc, psm)
        if value is not None:
            return value

    votes: Dict[int, int] = {}
    for image, psm in ((otsu, 10), (cell, 7), (cell, 10), (cv2.bitwise_not(otsu), 7)):
        value = attempt(image, psm)
        if value is not None:
            votes[value] = votes.get(value, 0) + 1
    return max(votes, key=votes.get) if votes else None


# ------------------------------------------------------------- table geometry

def _fit_line(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Least-squares y = a + b*x. Returns (a, b)."""
    xs = np.array([p[0] for p in points])
    ys = np.array([p[1] for p in points])
    if len(points) < 2 or np.ptp(xs) == 0:
        return float(ys.mean()), 0.0
    b, a = np.polyfit(xs, ys, 1)
    return float(a), float(b)


def _find_label(words: List[_Word], label: str) -> Optional[_Word]:
    cands = [w for w in words if w.text.upper().strip(":") == label]
    if not cands:
        return None
    # Row labels live in the left third of the card
    return min(cands, key=lambda w: w.x)


def _fit_columns(
    words: List[_Word], hole_label: _Word, width: int
) -> Tuple[float, float, float]:
    """
    Fit column centres: x(k) = x0 + k * pitch for column index k in
    _COLUMN_KEYS. Returns (x0, pitch, slope) where slope is how much the rows
    drift in y per pixel of x (non-zero only for tilted photos).
    """
    # Header sits at, or slightly above, the HOLE label (rising to the right on
    # a tilted photo). The PAR row is below it, so keep only the upper band.
    y_top = hole_label.y - 0.045 * width
    y_bot = hole_label.y + 0.012 * width
    obs: List[Tuple[int, float, float]] = []  # (column idx, x, y)
    for w in words:
        if w.x <= hole_label.x + hole_label.w or not (y_top <= w.y <= y_bot):
            continue
        key = w.text.upper()
        if key in _COLUMN_KEYS:
            obs.append((_COLUMN_KEYS.index(key), w.x, w.y))
    if len(obs) < 4:
        raise ScorecardReadError(
            f"Only found {len(obs)} header cells - is a GSPro scorecard on screen?"
        )

    # Robust fit x = x0 + k*pitch: repeatedly drop the worst outlier
    while True:
        ks = np.array([o[0] for o in obs], dtype=float)
        xs = np.array([o[1] for o in obs])
        pitch, x0 = np.polyfit(ks, xs, 1)
        resid = np.abs(xs - (x0 + pitch * ks))
        if len(obs) <= 4 or resid.max() < 0.2 * pitch:
            break
        obs.pop(int(resid.argmax()))

    _, slope = _fit_line([(o[1], o[2]) for o in obs])
    return float(x0), float(pitch), float(slope)


# ------------------------------------------------------------------- main API

def read_scorecard(frame: np.ndarray, read_distance: bool = False) -> ScorecardData:
    """
    Parse a full-screen (or cropped) GSPro scorecard image (BGR array).

    Distances are skipped by default - they aren't needed for scoring and
    are the slowest row to read.
    """
    gray_full = _to_gray(frame)
    scale = _WORK_WIDTH / gray_full.shape[1]
    gray = cv2.resize(
        gray_full, None, fx=scale, fy=scale,
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )
    height, width = gray.shape

    words = _ocr_words(gray)
    labels = {name: _find_label(words, name) for name in _ROW_LABELS}
    if labels["HOLE"] is None or labels["PAR"] is None:
        raise ScorecardReadError("Couldn't find the HOLE / PAR rows - not a scorecard?")

    x0, pitch, slope = _fit_columns(words, labels["HOLE"], width)
    hole_lbl = labels["HOLE"]

    def col_x(key: str) -> float:
        return x0 + pitch * _COLUMN_KEYS.index(key)

    def read_row(label_y: float, lo: int, hi: int, keys: List[str], half_h: float) -> Dict[str, Optional[int]]:
        """Read one table row. label_y is where the row's label text sits."""
        crops = []
        for key in keys:
            cx = col_x(key)
            cy = label_y + slope * (cx - hole_lbl.x)  # follow any tilt
            x1, x2 = max(int(cx - 0.42 * pitch), 0), int(cx + 0.42 * pitch)
            y1, y2 = max(int(cy - half_h), 0), int(cy + half_h)
            crops.append(gray[y1:y2, x1:x2])
        # tesseract runs as a subprocess, so threads give a real speed-up
        values = list(_POOL.map(lambda crop: _read_number(crop, lo, hi), crops))
        return dict(zip(keys, values))

    # Row pitch = distance between consecutive labelled rows
    ys = sorted(l.y for l in labels.values() if l is not None)
    row_pitch = float(np.median(np.diff(ys))) if len(ys) > 1 else 0.035 * width
    half_h = 0.5 * row_pitch

    hole_keys = [k for k in _COLUMN_KEYS if k.isdigit()]
    data = ScorecardData()

    # Course name: text to the left of the word SCORECARD, top of the card
    title = next((w for w in words if w.text.upper() == "SCORECARD"), None)
    if title:
        parts = [
            w for w in words
            if abs(w.y - title.y) < 0.02 * width and w.x < title.x - title.w and w.conf > 50
        ]
        name = " ".join(w.text for w in sorted(parts, key=lambda w: w.x))
        data.course_name = name.title() or None

    par_row = read_row(labels["PAR"].y, 3, 6, hole_keys, half_h)
    data.par = {int(k): v for k, v in par_row.items() if v is not None}

    if labels["INDEX"] is not None:
        idx_row = read_row(labels["INDEX"].y, 1, 18, hole_keys, half_h)
        data.stroke_index = {int(k): v for k, v in idx_row.items() if v is not None}

    if read_distance and labels["DISTANCE"] is not None:
        dist_row = read_row(labels["DISTANCE"].y, 30, 800, hole_keys, half_h)
        data.distance = {int(k): v for k, v in dist_row.items() if v is not None}

    # Player rows: alphabetic words in the label column, below the last known row
    last_label = max((l for l in labels.values() if l is not None), key=lambda l: l.y)
    label_col_right = col_x("1") - 0.5 * pitch
    # Everything from "ROUND SETTINGS" down is the footer, not a player row
    footer = next((w for w in words if w.text.upper() == "ROUND" and w.y > last_label.y), None)
    y_limit = footer.y - 0.5 * row_pitch if footer else height
    name_words = [
        w for w in words
        if last_label.y + 0.5 * row_pitch < w.y < y_limit
        and w.x < label_col_right
        and re.fullmatch(r"[A-Za-z0-9_.\-']{2,}", w.text)
        and w.conf > 40
        and w.text.upper() not in _ROW_LABELS
    ]
    name_words.sort(key=lambda w: w.y)

    rows: List[List[_Word]] = []
    for w in name_words:
        if rows and abs(rows[-1][0].y - w.y) < 0.6 * row_pitch:
            rows[-1].append(w)
        else:
            rows.append([w])

    for row in rows:
        name = " ".join(w.text for w in sorted(row, key=lambda w: w.x))
        label_y = float(np.mean([w.y for w in row]))
        cells = read_row(label_y, 1, 12, hole_keys, half_h)
        totals = read_row(label_y, 1, 200, ["OUT", "IN", "TOT"], half_h)

        card = PlayerCard(name=name)
        card.strokes = {int(k): v for k, v in cells.items() if v is not None}
        card.out_total, card.in_total, card.total = totals["OUT"], totals["IN"], totals["TOT"]
        card.verified = _verify(card)
        if len(card.strokes) < 3:  # a real player row has scores; this was stray text
            continue
        data.players.append(card)

    return data


def _verify(card: PlayerCard) -> bool:
    """True when every hole was read and the printed totals agree."""
    if len(card.strokes) != 18:
        return False
    front = sum(card.strokes[h] for h in range(1, 10))
    back = sum(card.strokes[h] for h in range(10, 19))
    if card.out_total is not None and card.out_total != front:
        return False
    if card.in_total is not None and card.in_total != back:
        return False
    if card.total is not None and card.total != front + back:
        return False
    # At least one printed total must have matched, otherwise we proved nothing
    return any(t is not None for t in (card.out_total, card.in_total, card.total))
