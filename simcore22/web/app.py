# simcore22/web/app.py
"""
The web server: a JSON API plus the two front ends (live leaderboard, admin portal).

It only READS what the engine writes (state/*.json, data/rounds.jsonl, saved
scorecard screenshots) - it never talks to the engine directly, so the engine and
the UI can run, crash and restart independently. `demo=True` swaps those files for
the built-in fictional league (see demo.py).

Players and admins log in (accounts live in data/simcore22.db, see league/). The live
leaderboard pages stay open on purpose: they are what the bay TVs show. By default the server
listens on this PC only (127.0.0.1); to let phones and bay screens reach it use
--host 0.0.0.0 on a trusted venue network, and put it behind https before exposing it further.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from simcore22 import __version__
from simcore22.engine import round_log, state_writer
from simcore22.league import standings
from simcore22.league.db import Database
from simcore22.league.demo_seed import DemoVenue
from simcore22.league.errors import LeagueError
from simcore22.web import auth, data
from simcore22.web.demo import DemoLeague
from simcore22.web.league_api import build_router

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
ENGINE_STALE_AFTER_S = 15  # the engine rewrites its status every 3s; older than this = not running


class RevalidatingStatic(StaticFiles):
    """Static files that browsers re-check on every load (a cheap 304 when unchanged), so an
    update to the portal shows up immediately instead of after a hard refresh."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


NO_CACHE = {"Cache-Control": "no-cache"}


class Source(Protocol):
    """Where the UI gets its data: the real files, or the demo league."""

    mode: str

    def rounds(self) -> List[Dict[str, Any]]: ...
    def leaderboard(self) -> Dict[str, Any]: ...
    def engine_status(self) -> Optional[Dict[str, Any]]: ...
    def signature(self) -> Tuple: ...
    def scorecard_path(self, name: str) -> Optional[Path]: ...


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    # read_state retries the brief moment the engine is swapping the file
    return state_writer.read_state(str(path))


class FileSource:
    """The real thing: files written by the engine."""

    mode = "live"

    def __init__(self, rounds_path: Path, leaderboard_path: Path, engine_status_path: Path, scorecards_dir: Path):
        self.rounds_path = Path(rounds_path)
        self.leaderboard_path = Path(leaderboard_path)
        self.engine_status_path = Path(engine_status_path)
        self.scorecards_dir = Path(scorecards_dir)

    def rounds(self) -> List[Dict[str, Any]]:
        return round_log.read_rounds(self.rounds_path)

    def leaderboard(self) -> Dict[str, Any]:
        board = _read_json(self.leaderboard_path)
        if board is None:
            return {"players": [], "league_name": None, "course_name": None, "week": None, "format": None,
                    "updated_at": None}
        board.setdefault("updated_at", _mtime_iso(self.leaderboard_path))
        return board

    def engine_status(self) -> Optional[Dict[str, Any]]:
        return _read_json(self.engine_status_path)

    def signature(self) -> Tuple:
        return tuple(_mtime(p) for p in (self.leaderboard_path, self.engine_status_path, self.rounds_path))

    def scorecard_path(self, name: str) -> Optional[Path]:
        safe = Path(name).name  # no directory parts: only files inside the scorecards folder
        candidate = self.scorecards_dir / safe
        return candidate if safe.lower().endswith(".png") and candidate.is_file() else None


class DemoSource:
    mode = "demo"

    def __init__(self, league: Optional[DemoLeague] = None):
        self.league = league or DemoLeague()

    def rounds(self):
        return self.league.rounds()

    def leaderboard(self):
        return self.league.leaderboard()

    def engine_status(self):
        return self.league.engine_status()

    def signature(self):
        return self.league.signature()

    def scorecard_path(self, name: str) -> Optional[Path]:
        return None  # the fictional league has no screenshots


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _mtime_iso(path: Path) -> Optional[str]:
    m = _mtime(path)
    return datetime.fromtimestamp(m).astimezone().isoformat(timespec="seconds") if m else None


def _engine_view(status: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The engine status plus a computed `online` flag (it must have reported recently)."""
    if not status:
        return {"online": False, "known": False}
    age = (datetime.now().astimezone() - data.parse_time(status.get("updated_at"))).total_seconds()
    return {**status, "known": True, "age_seconds": max(0, int(age)),
            "online": bool(status.get("running")) and age <= ENGINE_STALE_AFTER_S}


def _board_view(board: Dict[str, Any]) -> Dict[str, Any]:
    return {**board, "players": data.rank_players(board.get("players") or [])}


class LeagueSource:
    """One league's live board, built from the hand-entered rounds, shaped like a `Source` so the
    same event stream serves it. The engine status still comes from the real source."""

    def __init__(self, app: FastAPI, league_id: int):
        self.app, self.league_id = app, league_id
        self.mode = app.state.source.mode

    def _sync(self) -> None:
        if self.app.state.demo_venue is not None:
            self.app.state.demo_venue.sync()

    def leaderboard(self) -> Dict[str, Any]:
        self._sync()
        with self.app.state.db.connect() as conn:
            board = standings.live_board(conn, self.league_id)
        if self.app.state.demo_venue is not None:
            board["demo"] = True
        return board

    def engine_status(self) -> Optional[Dict[str, Any]]:
        return self.app.state.source.engine_status()

    def signature(self) -> Tuple:
        self._sync()
        # the data revision, plus the minute so rounds age out of "tonight" on their own
        return (self.app.state.db.revision(), int(time.time() // 60))


async def event_stream(source: Source, interval: float = 0.5, max_events: Optional[int] = None) -> AsyncIterator[str]:
    """
    Server-sent events: send the current state immediately, then again whenever the
    underlying files change. A comment line every ~15s keeps idle connections open.
    """
    sent, last_sig, idle = 0, None, 0.0
    while max_events is None or sent < max_events:
        sig = source.signature()
        if sig != last_sig:
            last_sig, idle = sig, 0.0
            payload = {
                "leaderboard": _board_view(source.leaderboard()),
                "engine": _engine_view(source.engine_status()),
                "rounds_signature": list(sig),
            }
            yield f"event: update\ndata: {json.dumps(payload)}\n\n"
            sent += 1
        else:
            idle += interval
            if idle >= 15:
                idle = 0.0
                yield ": keep-alive\n\n"
        if max_events is not None and sent >= max_events:
            break
        await asyncio.sleep(interval)


def create_app(*, demo: bool = False, source: Optional[Source] = None, rounds_path: Optional[Path] = None,
               leaderboard_path: Optional[Path] = None, engine_status_path: Optional[Path] = None,
               scorecards_dir: Optional[Path] = None, db: Optional[Database] = None,
               local_hosts: frozenset = auth.LOOPBACK) -> FastAPI:
    """`db` is the accounts/rounds database (default: data/simcore22.db, or a throwaway one in demo mode).
    `local_hosts` are the client addresses allowed to do first-time admin setup."""
    demo_venue: Optional[DemoVenue] = None
    if source is None:
        if demo:
            source = DemoSource()
        else:
            source = FileSource(
                rounds_path or round_log.DEFAULT_PATH,
                leaderboard_path or state_writer.LEADERBOARD_FILE,
                engine_status_path or state_writer.ENGINE_STATUS_FILE,
                scorecards_dir or Path(round_log.DEFAULT_PATH).parent / "scorecards",
            )
    if isinstance(source, DemoSource):
        demo_venue = DemoVenue(source.league)
        db = demo_venue.db
    elif db is None:
        db = Database(Path(rounds_path or round_log.DEFAULT_PATH).parent / "simcore22.db")

    app = FastAPI(title="SimCore22", version=__version__, description="Live leaderboard, player accounts and venue admin API")
    app.state.source = source
    app.state.db = db
    app.state.demo_venue = demo_venue
    app.state.local_hosts = local_hosts
    app.include_router(build_router())

    @app.exception_handler(LeagueError)
    async def league_error(_request: Request, exc: LeagueError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    admin_only = [Depends(auth.require_admin)]

    # ---------------------------------------------------------------- pages

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app")

    @app.get("/live", include_in_schema=False)
    def live_page():
        return FileResponse(STATIC_DIR / "live.html", headers=NO_CACHE)

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        return FileResponse(STATIC_DIR / "admin.html", headers=NO_CACHE)

    @app.get("/app", include_in_schema=False)
    def player_page():
        return FileResponse(STATIC_DIR / "app.html", headers=NO_CACHE)

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(STATIC_DIR / "login.html", headers=NO_CACHE)

    # ------------------------------------------------------------------ API

    @app.get("/api/health", tags=["system"])
    def health():
        return {"ok": True, "version": __version__, "mode": source.mode}

    @app.get("/api/engine", tags=["system"])
    def engine_status():
        """Is the engine running, and what can it see (capture, current round)?"""
        return {**_engine_view(source.engine_status()), "mode": source.mode}

    @app.get("/api/leaderboard", tags=["live"])
    def leaderboard():
        """Current standings, ranked by score to par."""
        return {**_board_view(source.leaderboard()), "mode": source.mode}

    @app.get("/api/stream", tags=["live"])
    async def stream(
        max_events: Optional[int] = Query(None, ge=1, le=1000, description="stop after N events (diagnostics)"),
        league: Optional[int] = Query(None, description="a league id: stream its hand-entered live board instead of the screen-capture board"),
    ):
        """Server-sent events: the leaderboard and engine status, pushed as they change."""
        feed: Source = source
        if league is not None:
            with db.connect() as conn:
                if conn.execute("SELECT 1 FROM leagues WHERE id = ?", (league,)).fetchone() is None:
                    raise HTTPException(404, "No such league")
            feed = LeagueSource(app, league)
        return StreamingResponse(
            event_stream(feed, max_events=max_events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/summary", tags=["admin"], dependencies=admin_only)
    def summary():
        """Headline numbers for the admin overview."""
        return {**data.venue_summary(data.collapse(source.rounds())), "mode": source.mode}

    @app.get("/api/rounds", tags=["admin"], dependencies=admin_only)
    def rounds(
        status: Optional[str] = Query(None, description="completed | ended_early | abandoned | snapshot"),
        player: Optional[str] = None,
        q: Optional[str] = Query(None, description="free-text filter (player, course, status)"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        """Finished rounds, newest first (a checkpoint is replaced by its final record)."""
        rows = data.filter_rounds(data.collapse(source.rounds()), status=status, player=player, query=q)
        return {"total": len(rows), "offset": offset, "rounds": rows[offset:offset + limit]}

    @app.get("/api/rounds/{round_id}/{player}", tags=["admin"], dependencies=admin_only)
    def round_detail(round_id: str, player: str):
        """One player's round in full: hole-by-hole scorecard, stats, shots, where the scores came from."""
        for record in data.collapse(source.rounds()):
            if record.get("round_id") == round_id and str(record.get("player", "")).lower() == player.lower():
                return data.detail(record)
        raise HTTPException(404, "Round not found")

    @app.get("/api/players", tags=["admin"], dependencies=admin_only)
    def players():
        """One profile per player: rounds, average to par, handicap, recent trend."""
        return {"players": data.players(data.collapse(source.rounds()))}

    @app.get("/api/scorecards/{name}", tags=["admin"], dependencies=admin_only)
    def scorecard_image(name: str):
        """The screenshot of GSPro's end-of-round scorecard that a round was read from."""
        path = source.scorecard_path(name)
        if path is None:
            raise HTTPException(404, "No such scorecard image")
        return FileResponse(path, media_type="image/png")

    app.mount("/static", RevalidatingStatic(directory=STATIC_DIR), name="static")
    return app


def create_app_from_env() -> FastAPI:
    """uvicorn factory entry: SIMCORE_DEMO=1 serves the demo league."""
    return create_app(demo=os.environ.get("SIMCORE_DEMO") == "1")
