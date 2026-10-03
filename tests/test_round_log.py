import asyncio
import json
from datetime import datetime

import numpy as np
import pytest

from mvp.engine import engine, engine_loop, round_log, state_writer
from mvp.engine.engine_loop import EngineRuntime
from mvp.engine.models.events import HoleEvent, PlayerEvent, ScoreEvent, ShotEvent


# --------------------------------------------------------------- the file itself

def test_append_and_read_roundtrip(tmp_path):
    path = tmp_path / "rounds.jsonl"
    round_log.append_round({"player": "Jeff", "gross": 72}, path)
    round_log.append_round({"player": "Sam", "gross": 80}, path)

    rounds = round_log.read_rounds(path)
    assert [r["player"] for r in rounds] == ["Jeff", "Sam"]  # oldest first
    assert all(r["schema_version"] == round_log.SCHEMA_VERSION for r in rounds)
    assert all("logged_at" in r for r in rounds)
    assert len(path.read_text().splitlines()) == 2  # one line per record


def test_missing_file_reads_as_empty(tmp_path):
    assert round_log.read_rounds(tmp_path / "nope.jsonl") == []


def test_serializes_dataclasses_datetimes_bytes_and_sets(tmp_path):
    path = tmp_path / "rounds.jsonl"
    shot = ShotEvent(source_device="Falcon", timestamp=datetime(2026, 10, 3, 12, 0, 0),
                     ball_speed=150.5, metadata={"raw": b"\x01\xff", "tags": {"b", "a"}})
    round_log.append_round({"shots": [shot]}, path)

    (record,) = round_log.read_rounds(path)
    saved = record["shots"][0]
    assert saved["ball_speed"] == 150.5
    assert saved["timestamp"] == "2026-10-03T12:00:00"
    assert saved["metadata"]["raw"] == "01ff"
    assert saved["metadata"]["tags"] == ["a", "b"]


def test_append_never_rewrites_earlier_lines(tmp_path):
    path = tmp_path / "rounds.jsonl"
    round_log.append_round({"n": 1}, path)
    first_line = path.read_bytes()
    round_log.append_round({"n": 2}, path)
    assert path.read_bytes().startswith(first_line)


def test_truncated_last_line_is_skipped_but_earlier_rounds_survive(tmp_path):
    path = tmp_path / "rounds.jsonl"
    round_log.append_round({"player": "Jeff"}, path)
    round_log.append_round({"player": "Sam"}, path)
    with open(path, "a", encoding="utf-8") as f:  # simulate a crash mid-write
        f.write('{"schema_version":1,"player":"Ty')

    assert [r["player"] for r in round_log.read_rounds(path)] == ["Jeff", "Sam"]


# ------------------------------------------------- the engine writing to it

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point every output at tmp_path and start from an empty session."""
    log_path = tmp_path / "data" / "rounds.jsonl"
    state_dir = tmp_path / "state"
    monkeypatch.setattr(round_log, "DEFAULT_PATH", log_path)
    monkeypatch.setattr(state_writer, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(state_writer, "LEADERBOARD_FILE", str(state_dir / "leaderboard.json"))
    monkeypatch.setattr(state_writer, "ROUND_SUMMARY_FILE", str(state_dir / "round_summary.json"))
    monkeypatch.setattr(state_writer, "ADMIN_SNAPSHOT_FILE", str(state_dir / "admin_snapshot.json"))
    monkeypatch.setattr(engine, "_session_state", engine.SessionState())
    return tmp_path


async def _play(runtime, player, holes):
    """holes: [(hole_number, par, number_of_shots_hit, confirmed_gross_score)]"""
    engine.handle_player_event(PlayerEvent(timestamp=datetime.now(), player_name=player))
    for number, par, n_shots, gross in holes:
        engine.handle_hole_event(HoleEvent(timestamp=datetime.now(), hole_number=number))
        for i in range(n_shots):
            await runtime._handle_shot_event(ShotEvent(
                source_device="FAKE", timestamp=datetime.now(),
                ball_speed=140 + i, carry_distance=200 + 10 * i, azimuth=-2.0,
            ))
        engine.handle_score_event(ScoreEvent(
            timestamp=datetime.now(), player_name=player,
            hole_number=number, gross_score=gross, par=par,
        ))


def _finish_two_player_round(card=None, reason="hole_count"):
    runtime = EngineRuntime("127.0.0.1", 921, ocr_enabled=False)

    async def go():
        await _play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        await _play(runtime, "Sam", [(1, 4, 5, 6), (2, 3, 3, 4)])
        await runtime._finalize_round(reason=reason)

    asyncio.run(go())
    return runtime


def test_finishing_a_round_logs_one_line_per_player(sandbox):
    _finish_two_player_round()

    rounds = round_log.read_rounds(sandbox / "data" / "rounds.jsonl")
    by_player = {r["player"]: r for r in rounds}
    assert set(by_player) == {"Jeff", "Sam"}
    assert by_player["Jeff"]["round_id"] == by_player["Sam"]["round_id"]  # same session

    jeff = by_player["Jeff"]
    assert jeff["finalize_reason"] == "hole_count"
    assert jeff["score_source"] == "shot_tally"
    assert jeff["holes_played"] == 2
    assert jeff["handicap_was_default"] is True
    assert jeff["handicap_index_used"] == engine_loop.DEFAULT_STARTING_INDEX
    assert jeff["shot_devices"] == ["FAKE"]
    assert len(jeff["shots"]) == 5   # only HIS 3 + 2 shots, not Sam's
    assert len(by_player["Sam"]["shots"]) == 8
    assert jeff["hole_scores"][0] == {"hole": 1, "par": 4, "score_used": 4, "gross_score": 4, "shot_tally": 3}
    assert jeff["stats"]["gross_score"] == 7


def _card(verified):
    return {
        "course_name": "Mammoth Dunes",
        "par": {1: 4, 2: 3},
        "stroke_index": {1: 11, 2: 9},
        # different case than the session's "Jeff": matching must ignore case
        "players": [{"name": "JEFF", "strokes": {1: 5, 2: 3}, "out": None, "in": None,
                     "total": 8, "gross": 8, "verified": verified}],
    }


def _with_scorecard(monkeypatch, card):
    monkeypatch.setattr("mvp.engine.ocr.capture_windows.capture_game_frame",
                        lambda *a, **k: np.zeros((10, 10, 3), np.uint8))
    monkeypatch.setattr(engine_loop, "read_scorecard_from_image", lambda frame: card)


def test_verified_scorecard_replaces_the_tally_and_is_recorded_as_the_source(sandbox, monkeypatch):
    _with_scorecard(monkeypatch, _card(verified=True))
    _finish_two_player_round()

    by_player = {r["player"]: r for r in round_log.read_rounds(sandbox / "data" / "rounds.jsonl")}
    jeff, sam = by_player["Jeff"], by_player["Sam"]

    assert jeff["score_source"] == "scorecard_ocr_verified"
    assert [h["score_used"] for h in jeff["hole_scores"]] == [5, 3]  # GSPro's numbers, not ours (4, 3)
    assert jeff["stats"]["gross_score"] == 8
    assert jeff["course"] == "Mammoth Dunes"
    assert jeff["scorecard_ocr"]["matched_row"]["verified"] is True
    assert jeff["scorecard_ocr"]["players_on_card"] == ["JEFF"]
    assert sam["score_source"] == "shot_tally"  # Sam isn't on the card


def test_unverified_scorecard_row_is_not_trusted(sandbox, monkeypatch):
    _with_scorecard(monkeypatch, _card(verified=False))
    _finish_two_player_round()

    jeff = next(r for r in round_log.read_rounds(sandbox / "data" / "rounds.jsonl") if r["player"] == "Jeff")
    assert jeff["score_source"] == "shot_tally"
    assert [h["score_used"] for h in jeff["hole_scores"]] == [4, 3]  # untouched
    assert jeff["scorecard_ocr"]["matched_row"] is None
    assert jeff["scorecard_ocr"]["players_on_card"] == ["JEFF"]  # still kept for calibration


def test_a_logging_failure_never_interrupts_scoring(sandbox, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(round_log, "append_round", boom)
    _finish_two_player_round()  # must not raise

    summary = json.loads((sandbox / "state" / "round_summary.json").read_text())
    assert summary["player"] in {"Jeff", "Sam"}
    assert (sandbox / "state" / "admin_snapshot.json").exists()
