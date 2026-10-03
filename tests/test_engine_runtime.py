"""The running engine: safe defaults, status heartbeat, saving work when stopped."""
import asyncio
import json

import pytest

from simcore22.engine import config
from simcore22.engine.engine_loop import EngineRuntime


def _runtime(**kwargs):
    return EngineRuntime(ocr_enabled=False, console_commands=False, **kwargs)


# --------------------------------------------------------- the feed is opt-in

def test_no_launch_monitor_feed_is_started_by_default():
    """The old default connected to port 921 - GSPro's own server port."""
    assert config.FEED_PORT is None
    assert _runtime().foresight_listener is None


def test_a_configured_feed_port_creates_the_listener_without_starting_it():
    runtime = _runtime(feed_port=12345)
    assert runtime.foresight_listener is not None
    assert (runtime.foresight_listener.host, runtime.foresight_listener.port) == ("127.0.0.1", 12345)


def test_the_engine_refuses_to_connect_to_gspro_connect(sandbox):
    """GSPro accepts ONE client on that port; taking it would knock FSX off GSPro."""
    with pytest.raises(ValueError, match="GSPro Connect"):
        _runtime(feed_port=config.GSPRO_CONNECT_PORT)


# ------------------------------------------- the leaderboard doesn't invent a league

def test_the_published_board_does_not_invent_a_league_name_or_week(sandbox, play):
    runtime = _runtime()
    asyncio.run(play(runtime, "Alex", [(1, 4, 3, 4)]))
    board = json.loads((sandbox / "state" / "leaderboard.json").read_text(encoding="utf-8"))
    assert board["league_name"] is None and board["week"] is None   # not "Default League", not "Week 1"


def test_a_configured_league_name_is_shown(sandbox, play, monkeypatch):
    monkeypatch.setattr(config, "LEAGUE_NAME", "Thursday Night League")
    runtime = _runtime()
    asyncio.run(play(runtime, "Alex", [(1, 4, 3, 4)]))
    board = json.loads((sandbox / "state" / "leaderboard.json").read_text(encoding="utf-8"))
    assert board["league_name"] == "Thursday Night League"


# ------------------------------------------------------ status heartbeat file

def test_status_snapshot_describes_the_engine_and_the_round(sandbox, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Alex", [(1, 4, 3, 4), (2, 3, 2, None)])

    asyncio.run(go())
    status = runtime.status_snapshot()

    assert status["running"] is True
    assert status["feed"]["configured"] is False
    assert status["capture"]["state"] == "disabled"           # OCR is off in this test
    assert status["round"]["in_progress"] is True
    assert status["round"]["players"] == [{"name": "Alex", "holes": 2, "current_hole": 2}]
    assert status["round"]["shots"] == 5
    assert status["round"]["idle_timeout_minutes"] == config.ROUND_IDLE_TIMEOUT_MINUTES


def test_an_idle_engine_reports_no_round(sandbox):
    status = _runtime().status_snapshot()
    assert status["round"]["in_progress"] is False
    assert status["round"]["players"] == []


def test_the_status_file_is_written_for_the_web_ui(sandbox):
    runtime = _runtime()
    runtime._write_status()
    written = json.loads((sandbox / "state" / "engine_status.json").read_text(encoding="utf-8"))
    assert written["running"] is True and written["pid"] > 0 and "updated_at" in written


# --------------------------------------------------- stopping the engine

def test_stopping_the_engine_saves_the_round_in_progress(sandbox, logged_rounds, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Alex", [(1, 4, 3, 4), (2, 3, 2, 3), (3, 5, 1, None)])

    asyncio.run(go())
    runtime.shutdown()

    (record,) = logged_rounds()
    assert record["round_status"] == "ended_early"
    assert record["finalize_reason"] == "engine_stopped"
    assert record["holes_played"] == 2          # the unfinished 3rd hole is kept but not counted
    status = json.loads((sandbox / "state" / "engine_status.json").read_text(encoding="utf-8"))
    assert status["running"] is False


def test_stopping_an_idle_engine_logs_nothing_and_does_not_fail(sandbox, logged_rounds):
    _runtime().shutdown()
    assert logged_rounds() == []
