"""
Round-length handling in the scorecard reader: 9-hole cards, cards with only
some holes played, the end-of-round marker, checksum failures.

Uses synthetic cards (tests/synthetic_scorecard.py). They prove the logic, NOT
accuracy on real GSPro cards - the layout for 9-hole cards is an assumption
until a real 9-hole screenshot confirms it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from synthetic_scorecard import FONTS_AVAILABLE, render_scorecard  # noqa: E402

from mvp.engine.ocr.scorecard_reader import (  # noqa: E402
    PlayerCard,
    _verify,
    looks_like_scorecard_panel,
    read_scorecard,
)
from mvp.engine.ocr.tesseract_setup import find_tesseract  # noqa: E402

needs_render = pytest.mark.skipif(
    find_tesseract() is None or not FONTS_AVAILABLE, reason="needs Tesseract and Windows fonts"
)

FULL = dict(zip(range(1, 19), [4, 3, 4, 4, 4, 3, 5, 2, 4, 3, 4, 4, 2, 3, 4, 2, 3, 4]))
NINE = {h: FULL[h] for h in range(1, 10)}


def _row(card, name):
    return next(p for p in card["players"] if p["name"] == name)


# ----------------------------------------------------------- checksum logic

def test_verify_accepts_a_nine_hole_card_checked_against_out():
    assert _verify(PlayerCard("A", NINE, out_total=33))


def test_verify_accepts_a_partly_played_card_if_the_printed_total_matches():
    assert _verify(PlayerCard("A", {1: 4, 2: 3, 3: 5}, out_total=12))


def test_verify_rejects_a_wrong_printed_total():
    assert not _verify(PlayerCard("A", NINE, out_total=34))


def test_verify_rejects_a_gap_in_the_holes_read():
    gappy = {h: v for h, v in NINE.items() if h != 5}  # a cell we couldn't read
    assert not _verify(PlayerCard("A", gappy, out_total=sum(gappy.values())))


def test_verify_needs_at_least_one_printed_total():
    assert not _verify(PlayerCard("A", NINE))
    assert not _verify(PlayerCard("A", {}))


def test_verify_checks_front_and_back_nine_separately():
    assert _verify(PlayerCard("A", FULL, out_total=33, in_total=29, total=62))
    assert not _verify(PlayerCard("A", FULL, out_total=33, in_total=30, total=62))


# ------------------------------------------------ the on-screen panel check

def test_panel_detector_ignores_dark_gameplay_and_sees_a_light_card():
    import numpy as np

    gameplay = np.full((1080, 1920, 3), 60, np.uint8)
    card = gameplay.copy()
    card[200:900, 100:1800] = 235
    assert not looks_like_scorecard_panel(gameplay)
    assert looks_like_scorecard_panel(card)


# --------------------------------------------- reading rendered scorecards

@needs_render
def test_full_18_hole_card_with_two_players():
    over = {h: s + 1 for h, s in FULL.items()}
    card = read_scorecard(render_scorecard(18, [("JOESLAT", FULL), ("SAM", over)])).to_dict()

    assert card["holes_on_card"] == 18
    assert card["round_complete"] is True
    assert card["course_name"] == "Test Links"
    for name, scores in (("JOESLAT", FULL), ("SAM", over)):
        row = _row(card, name)
        assert row["strokes"] == scores
        assert row["verified"] is True


@needs_render
@pytest.mark.parametrize("label_total", [True, False])
def test_nine_hole_card_is_read_and_verified(label_total):
    card = read_scorecard(render_scorecard(9, [("JOESLAT", NINE)], label_total=label_total)).to_dict()

    assert card["holes_on_card"] == 9
    assert card["round_complete"] is True
    row = _row(card, "JOESLAT")
    assert row["strokes"] == NINE
    assert row["out"] == 33
    assert row["verified"] is True


@needs_render
def test_eighteen_column_card_where_only_nine_holes_were_played():
    card = read_scorecard(render_scorecard(18, [("JOESLAT", NINE)])).to_dict()

    row = _row(card, "JOESLAT")
    assert row["strokes"] == NINE  # back nine blank, not misread as scores
    assert row["verified"] is True


@needs_render
def test_card_without_play_again_is_not_the_end_of_round_card():
    card = read_scorecard(render_scorecard(18, [("JOESLAT", FULL)], play_again=False)).to_dict()
    assert card["round_complete"] is False


@needs_render
def test_a_wrong_printed_total_makes_the_row_untrusted():
    card = read_scorecard(render_scorecard(9, [("JOESLAT", NINE)], out_override=99)).to_dict()
    row = _row(card, "JOESLAT")
    assert row["strokes"] == NINE   # the holes themselves read fine...
    assert row["verified"] is False  # ...but the checksum disagrees, so don't trust it
