import asyncio
import json
from datetime import datetime


from simcore22.engine import engine_loop, round_log
from simcore22.engine.engine_loop import EngineRuntime
from simcore22.engine.models.events import ShotEvent


def _runtime(**kwargs):
    return EngineRuntime("127.0.0.1", 921, ocr_enabled=False, console_commands=False, **kwargs)


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

def _card(verified):
    return {
        "course_name": "Mammoth Dunes",
        "holes_on_card": 18,
        "round_complete": True,
        "par": {1: 4, 2: 3},
        "stroke_index": {1: 11, 2: 9},
        # different case than the session's "Jeff": matching must ignore case
        "players": [{"name": "JEFF", "strokes": {1: 5, 2: 3}, "out": None, "in": None,
                     "total": 8, "gross": 8, "verified": verified}],
    }


def _two_player_round(play, reason, card=None):
    runtime = _runtime()

    async def go():
        await play(runtime, "Jeff", [(1, 4, 3, 4), (2, 3, 2, 3)])
        await play(runtime, "Sam", [(1, 4, 5, 6), (2, 3, 3, 4)])
        await runtime._finalize_round(reason=reason, card=card)

    asyncio.run(go())
    return runtime


def test_finishing_a_round_logs_one_line_per_player(sandbox, logged_rounds, play):
    _two_player_round(play, "round_end_event")

    by_player = {r["player"]: r for r in logged_rounds()}
    assert set(by_player) == {"Jeff", "Sam"}
    assert by_player["Jeff"]["round_id"] == by_player["Sam"]["round_id"]  # same session

    jeff = by_player["Jeff"]
    assert jeff["round_status"] == "completed"
    assert jeff["finalize_reason"] == "round_end_event"
    assert jeff["score_source"] == "shot_tally"
    assert jeff["holes_played"] == 2
    assert jeff["handicap_was_default"] is True
    assert jeff["handicap_index_used"] == engine_loop.DEFAULT_STARTING_INDEX
    assert jeff["shot_devices"] == ["FAKE"]
    assert len(jeff["shots"]) == 5   # only HIS 3 + 2 shots, not Sam's
    assert len(by_player["Sam"]["shots"]) == 8
    assert jeff["hole_scores"][0] == {
        "hole": 1, "par": 4, "par_assumed": False, "score_used": 4,
        "gross_score": 4, "shot_tally": 3, "counted": True,
    }
    assert jeff["stats"]["gross_score"] == 7


def test_verified_scorecard_replaces_the_tally_and_is_recorded_as_the_source(sandbox, logged_rounds, play):
    _two_player_round(play, "scorecard", card=_card(verified=True))

    by_player = {r["player"]: r for r in logged_rounds()}
    jeff, sam = by_player["Jeff"], by_player["Sam"]

    assert jeff["round_status"] == "completed"
    assert jeff["score_source"] == "scorecard_ocr_verified"
    assert [h["score_used"] for h in jeff["hole_scores"]] == [5, 3]  # GSPro's numbers, not ours (4, 3)
    assert jeff["stats"]["gross_score"] == 8
    assert jeff["course"] == "Mammoth Dunes"
    assert jeff["scorecard_ocr"]["matched_row"]["verified"] is True
    assert jeff["scorecard_ocr"]["players_on_card"] == ["JEFF"]
    assert sam["score_source"] == "shot_tally"  # Sam isn't on the card


def test_unverified_scorecard_row_is_not_trusted(sandbox, logged_rounds, play):
    _two_player_round(play, "scorecard", card=_card(verified=False))

    jeff = next(r for r in logged_rounds() if r["player"] == "Jeff")
    assert jeff["score_source"] == "shot_tally"
    assert [h["score_used"] for h in jeff["hole_scores"]] == [4, 3]  # untouched
    assert jeff["scorecard_ocr"]["matched_row"] is None
    assert jeff["scorecard_ocr"]["players_on_card"] == ["JEFF"]  # still kept for calibration


def test_a_logging_failure_never_interrupts_scoring(sandbox, play, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(round_log, "append_round", boom)
    _two_player_round(play, "round_end_event")  # must not raise

    summary = json.loads((sandbox / "state" / "round_summary.json").read_text())
    assert summary["player"] in {"Jeff", "Sam"}
    admin = json.loads((sandbox / "state" / "admin_snapshot.json").read_text())
    assert {p["name"] for p in admin["players"]} == {"Jeff", "Sam"}  # both players, not just the last
