# simcore22/engine/state_writer.py
"""
Writes the JSON files the on-screen leaderboards and viewers read:
state/leaderboard.json, state/round_summary.json, state/admin_snapshot.json.

They are OVERWRITTEN as play happens (git-ignored; examples/state/ shows their
shape). The permanent record of finished rounds is data/rounds.jsonl.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# <project root>/state, regardless of which folder the engine was started from
STATE_DIR = str(Path(__file__).resolve().parents[2] / "state")
LEADERBOARD_FILE = os.path.join(STATE_DIR, "leaderboard.json")
ROUND_SUMMARY_FILE = os.path.join(STATE_DIR, "round_summary.json")
ADMIN_SNAPSHOT_FILE = os.path.join(STATE_DIR, "admin_snapshot.json")
ENGINE_STATUS_FILE = os.path.join(STATE_DIR, "engine_status.json")


def _ensure_state_dir() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)


def _write_json(path: str, data: Dict[str, Any]) -> None:
    """
    Write via a temp file + rename so a viewer never reads a half-written file.
    On Windows the rename fails if a viewer has the file open at that instant,
    so retry briefly (it's open for microseconds).
    """
    _ensure_state_dir()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, path)  # last attempt: let a persistent problem surface


def read_state(path: str, attempts: int = 5) -> Optional[Dict[str, Any]]:
    """
    Read one of the state files for a viewer. Returns None if it doesn't exist
    yet, or is being replaced at this very moment (Windows briefly denies access
    during the swap): just try again on the next poll.
    """
    for _ in range(attempts):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.02)
    return None


def write_engine_status(status: Dict[str, Any]) -> None:
    """
    Heartbeat for the web UI: whether the engine is running, what it can see,
    what round is in progress. Rewritten every few seconds; a reader treats a
    stale "updated_at" as "engine not running".
    """
    _write_json(ENGINE_STATUS_FILE, status)


def write_leaderboard_state(
    course_name: str,
    league_name: Optional[str],
    week: Optional[int],
    format_name: str,
    players: List[Dict[str, Any]],
) -> None:
    """
    players: list of dicts like:
    {
        "name": "Alex",
        "thru": 5,
        "gross": 20,
        "net": 14,
        "vs_par": -1,
        "points": 12,
        "points_needed": 24,
        "simcore_index": 10.0,
        "outdoor_hcp": 12.0,
    }
    """
    _write_json(LEADERBOARD_FILE, {
        "course_name": course_name,
        "format": format_name,
        "league_name": league_name,
        "week": week,
        "players": players,
    })


def write_round_summary_state(summary: Dict[str, Any]) -> None:
    """
    summary: full dict from analyze_round or similar, plus player/course metadata, e.g.:

    {
        "player": "Alex",
        "course": "Test Course",
        "holes": 9,
        "gross": 38,
        "score_vs_par": 2,
        "net": 28,
        "simcore_index": 10.0,
        "ball_flight": {...},
        "scoring": {...},
        "league": {...},
        ...
    }
    """
    _write_json(ROUND_SUMMARY_FILE, summary)


def write_admin_snapshot_state(
    league_name: str,
    week: int,
    players: List[Dict[str, Any]],
    teams: List[Dict[str, Any]],
) -> None:
    """
    players: list of dicts like:
    {
        "name": "Alex",
        "outdoor_ghin": 12.0,
        "simcore_index_start": 10.0,
        "simcore_index_current": 10.0,
        "practice_score": 40,
        "week_scores": [38, None, ...],
        "total_individual_points": 19,
        "points_per_round": [19],
        "team_points": 10,
    }

    teams: list of dicts like:
    {
        "name": "Team A",
        "points": 29,
    }
    """
    _write_json(ADMIN_SNAPSHOT_FILE, {
        "league_name": league_name,
        "week": week,
        "players": players,
        "teams": teams,
    })
