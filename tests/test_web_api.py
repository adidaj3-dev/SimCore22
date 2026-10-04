"""
The web API. The important tests here are CONTRACT tests: rounds made by the real
engine must come out correctly through the API, so the engine's log format and the
UI can't drift apart without a test failing.
"""
import asyncio
import json
from datetime import datetime, timedelta

import cv2
import pytest

from simcore22.engine import state_writer
from simcore22.engine.engine_loop import EngineRuntime
from simcore22.engine.ocr.tesseract_setup import find_tesseract
from simcore22.web.app import DemoSource, FileSource, create_app, event_stream
from simcore22.web.demo import DemoLeague
from web_helpers import admin_client


BASE = 1_790_000_000.0  # a realistic date: Windows can't convert 1970-era timestamps to local time


def _runtime():
    return EngineRuntime(ocr_enabled=False, console_commands=False)


@pytest.fixture
def client(sandbox):
    app = create_app(
        rounds_path=sandbox / "data" / "rounds.jsonl",
        leaderboard_path=sandbox / "state" / "leaderboard.json",
        engine_status_path=sandbox / "state" / "engine_status.json",
        scorecards_dir=sandbox / "data" / "scorecards",
    )
    return admin_client(app)


# ---------------------------------------------- real engine -> API (contract)

def test_a_round_made_by_the_real_engine_appears_in_the_rounds_api(client, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Alex", [(1, 4, 3, 4), (2, 3, 2, 3), (3, 5, 1, None)])
        return await runtime.handle_command("end")

    asyncio.run(go())

    body = client.get("/api/rounds").json()
    assert body["total"] == 1
    (row,) = body["rounds"]
    assert (row["player"], row["round_status"], row["holes_played"]) == ("Alex", "ended_early", 2)
    assert (row["gross"], row["vs_par"], row["verified"]) == (7, 0, False)

    detail = client.get(f"/api/rounds/{row['round_id']}/Alex").json()
    assert [(h["hole"], h["score"], h["counted"]) for h in detail["holes"]] == [(1, 4, True), (2, 3, True), (3, 1, False)]
    assert detail["shots"]["count"] == 6


def test_a_checkpoint_then_the_final_record_shows_as_one_round(client, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Alex", [(1, 4, 3, 4)])
        await runtime.handle_command("save")
        await play(runtime, "Alex", [(2, 3, 2, 3)])
        await runtime.handle_command("end")

    asyncio.run(go())
    rows = client.get("/api/rounds").json()["rounds"]
    assert len(rows) == 1 and rows[0]["holes_played"] == 2 and rows[0]["round_status"] == "ended_early"


def test_filters_and_paging(client, play):
    runtime = _runtime()

    async def go():
        for name in ("Alex", "Sam", "Jordan"):
            await play(runtime, name, [(1, 4, 3, 4)])
            await runtime.handle_command("end")

    asyncio.run(go())
    assert client.get("/api/rounds").json()["total"] == 3
    assert [r["player"] for r in client.get("/api/rounds?player=sam").json()["rounds"]] == ["Sam"]
    assert client.get("/api/rounds?status=completed").json()["total"] == 0
    page = client.get("/api/rounds?limit=2&offset=2").json()
    assert page["total"] == 3 and len(page["rounds"]) == 1


def test_players_and_summary_endpoints(client, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Alex", [(1, 4, 3, 4), (2, 3, 2, 3)])
        await runtime.handle_command("end")

    asyncio.run(go())
    (profile,) = client.get("/api/players").json()["players"]
    assert profile["player"] == "Alex" and profile["rounds"] == 1
    summary = client.get("/api/summary").json()
    assert summary["total_rounds"] == 1 and summary["rounds_7d"] == 1 and summary["mode"] == "live"


def test_an_unknown_round_is_a_404(client):
    assert client.get("/api/rounds/nope/Nobody").status_code == 404


def test_an_empty_venue_returns_empty_lists_not_errors(client):
    assert client.get("/api/rounds").json() == {"total": 0, "offset": 0, "rounds": []}
    assert client.get("/api/players").json() == {"players": []}
    assert client.get("/api/summary").json()["total_rounds"] == 0
    assert client.get("/api/leaderboard").json()["players"] == []


# ------------------------------------------------------------- live leaderboard

def test_the_leaderboard_api_ranks_what_the_engine_published(client, play):
    runtime = _runtime()

    async def go():
        await play(runtime, "Steady", [(1, 4, 4, 4), (2, 4, 4, 4), (3, 4, 4, 4)])
        await play(runtime, "Early", [(1, 4, 5, 5)])           # one bogey
        await play(runtime, "Hot", [(1, 4, 3, 3), (2, 4, 4, 4)])  # a birdie, then par

    asyncio.run(go())
    players = client.get("/api/leaderboard").json()["players"]
    assert [(p["name"], p["rank"], p["vs_par"], p["thru"]) for p in players] == [
        ("Hot", 1, -1, 2), ("Steady", 2, 0, 3), ("Early", 3, 1, 1),
    ]


# ----------------------------------------------------------- engine heartbeat

def test_the_engine_is_online_while_its_status_is_fresh(client):
    _runtime()._write_status()
    status = client.get("/api/engine").json()
    assert status["online"] is True and status["known"] is True and status["age_seconds"] <= 5


def test_a_stale_status_means_the_engine_is_not_running(client):
    old = (datetime.now().astimezone() - timedelta(seconds=120)).isoformat(timespec="seconds")
    state_writer.write_engine_status({"running": True, "updated_at": old})
    status = client.get("/api/engine").json()
    assert status["online"] is False and status["age_seconds"] >= 120


def test_a_cleanly_stopped_engine_is_offline_immediately(client):
    _runtime().shutdown()  # writes running: false
    assert client.get("/api/engine").json()["online"] is False


def test_no_status_file_means_unknown(client):
    assert client.get("/api/engine").json()["known"] is False


# ------------------------------------------------------ scorecard screenshots

@pytest.mark.skipif(find_tesseract() is None, reason="Tesseract not installed")
def test_the_saved_scorecard_screenshot_is_served_and_nothing_else_is(client, sandbox):
    runtime = _runtime()
    frame = cv2.imread("simcore22/engine/ocr/samples/scorecard.png")

    async def go():
        await runtime.scorecard_watcher.check(frame)
        await runtime.scorecard_watcher.check(frame)

    asyncio.run(go())

    (row,) = client.get("/api/rounds").json()["rounds"]
    assert row["verified"] is True and row["image"].endswith(".png")
    assert "\\" not in row["image"] and "/" not in row["image"]

    served = client.get(f"/api/scorecards/{row['image']}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert served.content[:8] == b"\x89PNG\r\n\x1a\n"

    # nothing outside the scorecards folder can be reached, and only .png files
    (sandbox / "secret.txt").write_text("private")
    assert client.get("/api/scorecards/..%2f..%2fsecret.txt").status_code == 404
    assert client.get("/api/scorecards/..%5c..%5csecret.txt").status_code == 404
    assert client.get("/api/scorecards/nope.png").status_code == 404


# --------------------------------------------------------------------- demo

def test_demo_mode_is_labelled_everywhere():
    demo = admin_client(create_app(demo=True))
    assert demo.get("/api/health").json()["mode"] == "demo"
    assert demo.get("/api/leaderboard").json()["demo"] is True
    assert demo.get("/api/engine").json()["demo"] is True
    assert all(r["demo"] for r in demo.get("/api/rounds?limit=500").json()["rounds"])
    assert all(p["demo"] for p in demo.get("/api/players").json()["players"])


def test_the_demo_league_has_history_players_and_a_live_board():
    demo = admin_client(create_app(demo=True))
    assert demo.get("/api/rounds").json()["total"] > 100
    assert len(demo.get("/api/players").json()["players"]) == 16
    board = demo.get("/api/leaderboard").json()
    assert len(board["players"]) >= 8 and board["league_name"]
    summary = demo.get("/api/summary").json()
    assert summary["rounds_7d"] > 0 and summary["verified_rate_30d"] > 0.5


def test_the_demo_is_repeatable_so_a_pitch_looks_the_same_every_time():
    a, b = DemoLeague(seed=22, clock=lambda: BASE), DemoLeague(seed=22, clock=lambda: BASE)
    assert a.leaderboard()["players"] == b.leaderboard()["players"]
    assert [r["hole_scores"] for r in a.rounds()] == [r["hole_scores"] for r in b.rounds()]


def test_the_demo_board_plays_itself_out_and_then_starts_over():
    now = [BASE]
    league = DemoLeague(seed=22, clock=lambda: now[0])
    thru = lambda: sum(p["thru"] for p in league.leaderboard()["players"])  # noqa: E731

    start = league.leaderboard()
    now[0] += 40
    assert thru() > sum(p["thru"] for p in start["players"])   # the round progresses

    now[0] = BASE + league._cycle - 5                          # near the end of the night
    final = league.leaderboard()
    assert final["round_complete"] is True and all(p["thru"] == 9 for p in final["players"])

    now[0] = BASE + 0.5                                          # the same moment in the first night...
    early = league.leaderboard()["players"]
    now[0] = BASE + league._cycle + 0.5                          # ...and one full night later: it loops
    assert league.leaderboard()["players"] == early


def test_demo_data_never_touches_real_files(sandbox):
    DemoSource().rounds()
    admin_client(create_app(demo=True)).get("/api/rounds")
    assert not (sandbox / "data").exists() and not (sandbox / "state").exists()


# ------------------------------------------------------------ live push stream

class _CountingSource:
    """A source whose data changes every time it is looked at."""
    mode = "test"

    def __init__(self):
        self.n = 0

    def signature(self):
        self.n += 1
        return (self.n,)

    def leaderboard(self):
        return {"players": [{"name": "A", "vs_par": 0, "thru": self.n, "gross": 4}]}

    def engine_status(self):
        return {"running": True, "updated_at": datetime.now().astimezone().isoformat()}

    def rounds(self):
        return []

    def scorecard_path(self, name):
        return None


def test_the_stream_pushes_state_immediately_and_again_when_it_changes():
    async def collect():
        return [chunk async for chunk in event_stream(_CountingSource(), interval=0.01, max_events=2)]

    chunks = asyncio.run(collect())
    assert len(chunks) == 2
    payloads = []
    for chunk in chunks:
        assert chunk.startswith("event: update\ndata: ") and chunk.endswith("\n\n")
        payloads.append(json.loads(chunk.split("data: ", 1)[1]))
    assert payloads[0]["leaderboard"]["players"][0]["rank"] == 1       # ranked server-side
    assert payloads[0]["engine"]["online"] is True
    assert payloads[0]["leaderboard"]["players"][0]["thru"] != payloads[1]["leaderboard"]["players"][0]["thru"]


def test_an_unchanged_state_is_not_resent():
    class Still(_CountingSource):
        def signature(self):
            return (1,)

    async def collect():
        sent = []
        async for chunk in event_stream(Still(), interval=0.01, max_events=1):
            sent.append(chunk)
        return sent

    assert len(asyncio.run(collect())) == 1


def test_the_stream_endpoint_serves_server_sent_events():
    demo = admin_client(create_app(demo=True))
    response = demo.get("/api/stream?max_events=1")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    assert response.text.startswith("event: update")


# ------------------------------------------------------------------- sources

def test_file_source_ignores_path_tricks_in_scorecard_names(tmp_path):
    folder = tmp_path / "scorecards"
    folder.mkdir()
    (folder / "ok.png").write_bytes(b"png")
    (tmp_path / "outside.png").write_bytes(b"png")
    source = FileSource(tmp_path / "r.jsonl", tmp_path / "l.json", tmp_path / "e.json", folder)
    assert source.scorecard_path("ok.png") == folder / "ok.png"
    assert source.scorecard_path("../outside.png") is None   # only the file-name part is used
    assert source.scorecard_path("ok.txt") is None
