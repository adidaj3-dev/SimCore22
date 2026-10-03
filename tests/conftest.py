import sys
from datetime import datetime

import pytest

from mvp.engine import engine, round_log, state_writer
from mvp.engine.models.events import HoleEvent, PlayerEvent, ScoreEvent, ShotEvent


@pytest.fixture(scope="session")
def live_desktop():
    """
    Tests that open real windows and screenshot them need a visible desktop.
    A locked or sleeping screen captures as solid black (the same symptom as a
    game in exclusive fullscreen), so skip those tests instead of failing them.
    """
    if sys.platform != "win32":
        pytest.skip("window capture is Windows-only")
    import mss
    import numpy as np

    with mss.MSS() as screen:
        shot = np.array(screen.grab(screen.monitors[1]))[:, :, :3]
    if float(shot.max(axis=2).mean()) < 2:
        pytest.skip("the screen is locked or asleep - unlock it and rerun to test window capture")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """
    Point every output at tmp_path and start from an empty session, so engine
    tests never touch the real data/ or state/ folders or leak into each other.
    """
    state_dir = tmp_path / "state"
    monkeypatch.setattr(round_log, "DEFAULT_PATH", tmp_path / "data" / "rounds.jsonl")
    monkeypatch.setattr(state_writer, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(state_writer, "LEADERBOARD_FILE", str(state_dir / "leaderboard.json"))
    monkeypatch.setattr(state_writer, "ROUND_SUMMARY_FILE", str(state_dir / "round_summary.json"))
    monkeypatch.setattr(state_writer, "ADMIN_SNAPSHOT_FILE", str(state_dir / "admin_snapshot.json"))
    monkeypatch.setattr(engine, "_session_state", engine.SessionState())
    monkeypatch.setattr(engine, "_handicap_book", {})
    return tmp_path


@pytest.fixture
def logged_rounds(sandbox):
    """Callable returning everything written to the (sandboxed) round log so far."""
    return lambda: round_log.read_rounds(sandbox / "data" / "rounds.jsonl")


@pytest.fixture
def play():
    """
    async play(runtime, player, holes): feed one player's holes through the
    engine exactly as live events would arrive.
    holes: [(hole_number, par, number_of_shots_hit, confirmed_gross_score_or_None)]
    A gross score of None = the hole was started but never finished.
    """

    async def _play(runtime, player, holes):
        engine.handle_player_event(PlayerEvent(timestamp=datetime.now(), player_name=player))
        for number, par, n_shots, gross in holes:
            engine.handle_hole_event(HoleEvent(timestamp=datetime.now(), hole_number=number))
            for i in range(n_shots):
                await runtime._handle_shot_event(ShotEvent(
                    source_device="FAKE", timestamp=datetime.now(),
                    ball_speed=140 + i, carry_distance=200 + 10 * i, azimuth=-2.0,
                ))
            if gross is not None:
                engine.handle_score_event(ScoreEvent(
                    timestamp=datetime.now(), player_name=player,
                    hole_number=number, gross_score=gross, par=par,
                ))

    return _play
