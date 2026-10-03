from pathlib import Path

import cv2
import pytest

from mvp.engine.ocr.scorecard_reader import (
    PlayerCard,
    ScorecardReadError,
    _verify,
    read_scorecard,
)
from mvp.engine.ocr.tesseract_setup import find_tesseract

SAMPLE = Path("mvp/engine/ocr/samples/scorecard.png")

needs_tesseract = pytest.mark.skipif(find_tesseract() is None, reason="Tesseract not installed")


@needs_tesseract
def test_reads_sample_scorecard():
    """Phone photo of a real GSPro scorecard (tilted, with circled scores)."""
    card = read_scorecard(cv2.imread(str(SAMPLE))).to_dict()

    assert card["course_name"] == "Mammoth Dunes"
    assert [card["par"][h] for h in range(1, 19)] == [4, 4, 5, 3, 4, 4, 5, 3, 4, 4, 5, 4, 3, 4, 5, 3, 4, 5]
    assert [card["stroke_index"][h] for h in range(1, 19)] == [11, 9, 3, 15, 5, 13, 1, 17, 7, 12, 4, 8, 18, 14, 6, 16, 10, 2]

    (player,) = card["players"]
    assert player["name"] == "JOESLAT"
    assert [player["strokes"][h] for h in range(1, 19)] == [4, 3, 4, 4, 4, 3, 5, 2, 4, 3, 4, 4, 2, 3, 4, 2, 3, 4]
    assert (player["out"], player["in"], player["total"]) == (33, 29, 62)
    assert player["verified"] is True


@needs_tesseract
def test_non_scorecard_image_is_rejected():
    hud = cv2.imread("mvp/engine/ocr/samples/hud.png")
    with pytest.raises(ScorecardReadError):
        read_scorecard(hud)


def test_verify_catches_a_misread_hole():
    strokes = dict(zip(range(1, 19), [4, 3, 4, 4, 4, 3, 5, 2, 4, 3, 4, 4, 2, 3, 4, 2, 3, 4], strict=True))
    good = PlayerCard("A", strokes, out_total=33, in_total=29, total=62)
    assert _verify(good)

    strokes[8] = 3  # OCR read a 2 as a 3 -> sums no longer match the printed totals
    bad = PlayerCard("A", strokes, out_total=33, in_total=29, total=62)
    assert not _verify(bad)


def test_verify_needs_a_printed_total_to_prove_anything():
    strokes = dict(zip(range(1, 19), [4] * 18, strict=True))
    assert not _verify(PlayerCard("A", strokes))
