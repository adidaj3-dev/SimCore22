"""
How a round starts, ends, quits, saves and resets. The behaviors:

  * the end-of-round scorecard (and nothing else) completes a round - an
    18-hole round is NOT cut off at hole 9, and every round is logged, not
    just the first
  * a player can stop at any time (`end`) and keep their data and stats
  * `save` checkpoints without ending the round
  * walking away saves the round as abandoned
  * only completed rounds can change a handicap
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from simcore22.engine import engine, scorecard_watch
from simcore22.engine.engine_loop import EngineRuntime
from simcore22.engine.ocr.tesseract_setup import find_tesseract
from simcore22.engine.models.events import (
    HoleEvent, PlayerEvent, RoundEndEvent, ScoreEvent, ShotEvent,
)


def _runtime(**kwargs):
    return EngineRuntime(ocr_enabled=False, console_commands=False, **kwargs)


def _card(name="JEFF", strokes=None, verified=True, complete=True):
    strokes = strokes or {1: 4, 2: 3}
    return {
        "course_name": "Mammoth Dunes", "holes_on_card": 18, "round_complete": complete,
        "par": {1: 4, 2: 3}, "stroke_index": {1: 11, 2: 9},
        "players": [{"name": name, "strokes": strokes, "out": None, "in": None,
                     "total": sum(strokes.values()), "gross": sum(strokes.values()), "verified": verified}],
    }


# ----------------------------------------------------- when a round ends

def test_an_18_hole_round_is_not_cut_off_at_hole_9(sandbox, logged_rounds):
    """The old code finalized at 9 holes even in an 18-hole round."""
    runtime = _runtime()

    async def go():
        loop_task = asyncio.create_task(runtime._engine_loop())
        emit = runtime.dispatcher.emit
        emit(PlayerEvent(timestamp=datetime.now(), player_name="Jeff"))
        for hole in range(1, 19):
            emit(HoleEvent(timestamp=datetime.now(), hole_number=hole))
            for _ in range(4):
                emit(ShotEvent(source_device="FAKE", timestamp=datetime.now(), ball_speed=140.0, carry_distance=200.0))
            emit(ScoreEvent(timestamp=datetime.now(), player_name="Jeff", hole_number=hole, gross_score=4, par=4))
        await asyncio.sleep(0.8)  # let the engine drain every event
        assert logged_rounds() == []  # holes 9 and 18 came and went; no round ended
        runtime.rounds.finalize(reason="scorecard", card=_card(strokes={h: 4 for h in range(1, 19)}))
        loop_task.cancel()

    asyncio.run(go())

    (record,) = logged_rounds()
    assert record["holes_played"] == 18
    assert record["round_status"] == "completed"


def test_every_round_is_logged_not_just_the_first(sandbox, logged_rounds, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        runtime.rounds.finalize(reason="round_end_event")
        await play(runtime, "Jeff", [(1, 4, 4, 5), (2, 3, 3, 3)])  # same player, next round
        runtime.rounds.finalize(reason="round_end_event")

    asyncio.run(go())

    first, second = logged_rounds()
    assert first["round_id"] != second["round_id"]
    assert first["stats"]["gross_score"] == 7
    assert second["stats"]["gross_score"] == 8  # round 1's scores did not leak into round 2
    assert len(second["shots"]) == 7            # nor its shots


def test_the_current_player_carries_into_the_next_round(sandbox, play):
    """The HUD only reports a name when it CHANGES; forgetting it would orphan the next round's shots."""
    runtime = _runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4)])
        runtime.rounds.finalize(reason="round_end_event")
        # next round: HUD shows hole 1 again but does NOT re-announce the player
        engine.handle_hole_event(HoleEvent(timestamp=datetime.now(), hole_number=1))
        await runtime._handle_shot_event(ShotEvent(source_device="FAKE", timestamp=datetime.now(), ball_speed=140.0))

    asyncio.run(go())
    assert engine.get_session_state().players["Jeff"].holes[1].strokes == 1


# ----------------------------------------------- the scorecard as the signal

def _bright_panel():
    return np.full((600, 800, 3), 235, np.uint8)


def _dark_scene():
    return np.full((600, 800, 3), 50, np.uint8)


def _watch_scorecard_reads(monkeypatch, card):
    reads = []

    def fake_read(frame):
        reads.append(1)
        return dict(card)

    monkeypatch.setattr(scorecard_watch, "read_scorecard_from_image", fake_read)
    return reads


def test_the_end_of_round_scorecard_finishes_the_round_once(sandbox, logged_rounds, play, monkeypatch):
    runtime = _runtime()
    reads = _watch_scorecard_reads(monkeypatch, _card())

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        await runtime.scorecard_watcher.check(_bright_panel())  # 1st poll: could be animating in
        assert reads == []
        await runtime.scorecard_watcher.check(_bright_panel())  # 2nd poll: read it
        assert len(reads) == 1
        for _ in range(3):                                   # card stays on screen
            await runtime.scorecard_watcher.check(_bright_panel())
        assert len(reads) == 1                               # ...but is not read again
        for _ in range(3):                                   # card closed
            await runtime.scorecard_watcher.check(_dark_scene())
        await play(runtime, "Jeff", [(1, 4, 2, 4)])          # next round starts
        for _ in range(2):                                   # next end-of-round card
            await runtime.scorecard_watcher.check(_bright_panel())

    asyncio.run(go())

    assert len(reads) == 2
    rounds = logged_rounds()
    assert [r["round_status"] for r in rounds] == ["completed", "completed"]
    assert rounds[0]["finalize_reason"] == "scorecard"
    assert rounds[0]["scorecard_ocr"]["image_file"] is None or rounds[0]["scorecard_ocr"]["image_file"].endswith(".png")


@pytest.mark.skipif(find_tesseract() is None, reason="Tesseract not installed")
def test_the_real_gspro_scorecard_photo_ends_and_logs_a_round_end_to_end(sandbox, logged_rounds):
    """Nothing mocked: real image -> panel check -> OCR -> finish round -> log + saved image."""
    runtime = _runtime()
    frame = cv2.imread("simcore22/engine/ocr/samples/scorecard.png")

    async def go():
        await runtime.scorecard_watcher.check(frame)
        await runtime.scorecard_watcher.check(frame)

    asyncio.run(go())

    (record,) = logged_rounds()
    assert record["player"] == "JOESLAT"
    assert record["round_status"] == "completed"
    assert record["score_source"] == "scorecard_ocr_verified"
    assert record["holes_played"] == 18
    assert record["stats"]["gross_score"] == 62
    assert record["course"] == "Mammoth Dunes"
    saved = Path(record["scorecard_ocr"]["image_file"])
    assert saved.exists() and saved.parent == sandbox / "data" / "scorecards"


def test_a_scorecard_without_play_again_is_a_mid_round_peek_and_is_ignored(sandbox, logged_rounds, play, monkeypatch):
    runtime = _runtime()
    _watch_scorecard_reads(monkeypatch, _card(complete=False))

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4)])
        for _ in range(3):
            await runtime.scorecard_watcher.check(_bright_panel())

    asyncio.run(go())
    assert logged_rounds() == []                       # the round did not end
    assert engine.get_session_state().players["Jeff"].holes[1].strokes == 3  # and nothing was reset


def test_a_bright_screen_that_isnt_a_scorecard_is_not_reread_every_second(sandbox, play, monkeypatch):
    runtime = _runtime()
    reads = []
    monkeypatch.setattr(scorecard_watch, "read_scorecard_from_image", lambda frame: reads.append(1) or {})

    async def go():
        for _ in range(8):  # bright sky for 8 polls
            await runtime.scorecard_watcher.check(_bright_panel())

    asyncio.run(go())
    assert len(reads) == 1  # tried once, then backed off


def test_a_round_is_recorded_from_the_scorecard_even_if_live_tracking_saw_nothing(sandbox, logged_rounds):
    """HUD OCR uncalibrated -> no player/hole/shot events at all. The card alone still gives the round."""
    runtime = _runtime()
    runtime.rounds.finalize(reason="scorecard", card=_card(name="JOESLAT", strokes={1: 4, 2: 3}))

    (record,) = logged_rounds()
    assert record["player"] == "JOESLAT"
    assert record["score_source"] == "scorecard_ocr_verified"
    assert record["holes_played"] == 2
    assert record["stats"]["gross_score"] == 7


def test_an_unreadable_scorecard_with_no_other_data_records_nothing(sandbox, logged_rounds):
    runtime = _runtime()
    results = runtime.rounds.finalize(reason="scorecard", card=_card(verified=False))
    assert results == []
    assert logged_rounds() == []


# --------------------------------------------- quitting early / saving

def test_ending_early_keeps_the_data_and_skips_the_unfinished_hole(sandbox, logged_rounds, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3), (3, 5, 4, 5)])
        await play(runtime, "Jeff", [(4, 4, 2, None)])  # started hole 4, hit twice, then quit
        return await runtime.handle_command("end")

    message = asyncio.run(go())

    assert "Jeff (3 holes)" in message
    (record,) = logged_rounds()
    assert record["round_status"] == "ended_early"
    assert record["finalize_reason"] == "manual_end"
    assert record["holes_played"] == 3
    hole4 = record["hole_scores"][3]
    assert hole4["hole"] == 4 and hole4["counted"] is False and hole4["shot_tally"] == 2
    assert record["stats"]["gross_score"] == 12          # holes 1-3 only
    assert record["stats"]["gross_vs_par"] == 0          # 4+3+5 against par 4+3+5
    assert len(record["shots"]) == 11                    # every shot is kept, including the unfinished hole's


def test_after_ending_early_the_next_round_starts_clean(sandbox, logged_rounds, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4)])
        await runtime.handle_command("end")
        await play(runtime, "Jeff", [(1, 4, 5, 6)])
        await runtime.handle_command("end")

    asyncio.run(go())
    first, second = logged_rounds()
    assert (first["stats"]["gross_score"], second["stats"]["gross_score"]) == (4, 6)
    assert runtime.rounds.shots == []


def test_end_with_no_round_in_progress_says_so(sandbox, logged_rounds):
    runtime = _runtime()
    assert "nothing to end" in asyncio.run(runtime.handle_command("end")).lower()
    assert logged_rounds() == []


def test_a_round_end_event_from_any_source_ends_the_round(sandbox, logged_rounds, play):
    """The console isn't the only way: a future admin portal / API feed can emit the same event."""
    runtime = _runtime()

    async def go():
        loop_task = asyncio.create_task(runtime._engine_loop())
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        runtime.dispatcher.emit(RoundEndEvent(timestamp=datetime.now(), reason="manual_end"))
        await asyncio.sleep(0.5)
        loop_task.cancel()

    asyncio.run(go())
    (record,) = logged_rounds()
    assert record["round_status"] == "ended_early"


def test_save_checkpoints_the_round_without_ending_it(sandbox, logged_rounds, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        saved = await runtime.handle_command("save")
        assert "Checkpoint saved" in saved
        assert engine.get_session_state().players["Jeff"].holes[2].gross_score == 3  # still in progress
        await play(runtime, "Jeff", [(3, 5, 4, 5)])
        await runtime.handle_command("end")

    asyncio.run(go())

    snapshot, final = logged_rounds()
    assert snapshot["round_status"] == "snapshot" and snapshot["finalize_reason"] == "manual_save"
    assert final["round_status"] == "ended_early"
    assert snapshot["round_id"] == final["round_id"]       # same round: take the latest line per round_id
    assert (snapshot["holes_played"], final["holes_played"]) == (2, 3)


def test_walking_away_saves_the_round_as_abandoned(sandbox, logged_rounds, play):
    runtime = _runtime(idle_timeout_minutes=0.01)  # 0.6 seconds, so the test doesn't wait 20 minutes

    async def go():
        loop_task = asyncio.create_task(runtime._engine_loop())
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        runtime.rounds.touch()
        await asyncio.sleep(3.5)  # the loop checks once a second
        loop_task.cancel()

    asyncio.run(go())
    (record,) = logged_rounds()
    assert record["round_status"] == "abandoned"
    assert record["finalize_reason"] == "idle_timeout"


def test_an_empty_bay_never_logs_anything_however_long_it_sits_idle(sandbox, logged_rounds):
    runtime = _runtime(idle_timeout_minutes=0.01)

    async def go():
        loop_task = asyncio.create_task(runtime._engine_loop())
        await asyncio.sleep(2.5)
        loop_task.cancel()

    asyncio.run(go())
    assert logged_rounds() == []


# ------------------------------------------------------------- handicaps

def _league_runtime():
    runtime = _runtime()
    now = datetime.now()
    runtime.rounds.schedule_config.league_windows = [(now - timedelta(hours=1), now + timedelta(hours=1))]
    runtime.rounds.league_state.current_round_number = 1   # round 0 is the practice round
    runtime.rounds.league_config.rounds_per_update = 1
    return runtime


def test_a_completed_league_round_updates_the_handicap_and_it_carries_over(sandbox, logged_rounds, play):
    runtime = _league_runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        runtime.rounds.finalize(reason="round_end_event")

    asyncio.run(go())

    (record,) = logged_rounds()
    assert record["round_type"] == "league"
    new_index = record["handicap_index_after"]
    assert isinstance(new_index, int)
    assert engine._handicap_book["jeff"] == new_index
    assert engine.get_or_create_round_state("Jeff").handicap_index == new_index  # next round starts from it


def test_an_early_ended_league_round_does_not_change_the_handicap(sandbox, logged_rounds, play):
    runtime = _league_runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        await runtime.handle_command("end")

    asyncio.run(go())

    (record,) = logged_rounds()
    assert record["round_type"] == "league"
    assert record["handicap_index_after"] is None
    assert engine._handicap_book == {}


# ---------------------------------------------------------- robustness

def test_unknown_par_does_not_crash_the_stats(sandbox, logged_rounds, play):
    """Tally-only rounds have no par (only a ScoreEvent or the card provide it)."""
    runtime = _runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, None), (2, 3, 2, None)])
        runtime.rounds.finalize(reason="round_end_event")

    asyncio.run(go())
    (record,) = logged_rounds()
    assert all(h["par_assumed"] for h in record["hole_scores"])
    assert record["stats"]["gross_score"] == 5


def test_one_players_failure_does_not_lose_the_others_or_block_the_next_round(sandbox, logged_rounds, play, monkeypatch):
    runtime = _runtime()
    real = runtime.rounds._compute_player

    def flaky(player_name, round_state, status):
        if player_name == "Sam":
            raise RuntimeError("bad data")
        return real(player_name, round_state, status)

    monkeypatch.setattr(runtime.rounds, "_compute_player", flaky)

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4)])
        await play(runtime, "Sam", [(1, 4, 5, 6)])
        runtime.rounds.finalize(reason="round_end_event")

    asyncio.run(go())
    assert [r["player"] for r in logged_rounds()] == ["Jeff"]
    assert runtime.rounds.shots == []                       # reset happened regardless
    assert not engine.get_session_state().players.get("Sam", None) or \
        not engine.get_session_state().players["Sam"].holes


# -------------------------------------------------------------- console

def test_console_help_status_and_unknown_commands(sandbox, play):
    runtime = _runtime()

    async def go():
        assert "No round in progress" in await runtime.handle_command("status")
        await play(runtime, "Jeff", [(1, 4, 3, 4)])
        status = await runtime.handle_command("status")
        assert "Jeff: 1 holes" in status and "3 shots" in status
        assert "end" in (await runtime.handle_command("help")) and "save" in (await runtime.handle_command("?"))
        assert "Unknown command" in await runtime.handle_command("frobnicate")

    asyncio.run(go())
