# mvp/engine/state_writer.py

import json
import os
from typing import Any, Dict, List

STATE_DIR = "state"
LEADERBOARD_FILE = os.path.join(STATE_DIR, "leaderboard.json")
ROUND_SUMMARY_FILE = os.path.join(STATE_DIR, "round_summary.json")
ADMIN_SNAPSHOT_FILE = os.path.join(STATE_DIR, "admin_snapshot.json")


def _ensure_state_dir() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)


def write_leaderboard_state(
    course_name: str,
    league_name: str,
    week: int,
    format_name: str,
    players: List[Dict[str, Any]],
) -> None:
    """
    players: list of dicts like:
    {
        "name": "Jeff",
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
    _ensure_state_dir()
    data: Dict[str, Any] = {
        "course_name": course_name,
        "format": format_name,
        "league_name": league_name,
        "week": week,
        "players": players,
    }
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(data, f, indent=2)


def write_round_summary_state(summary: Dict[str, Any]) -> None:
    """
    summary: full dict from analyze_round or similar, plus player/course metadata, e.g.:

    {
        "player": "Jeff",
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
    _ensure_state_dir()
    with open(ROUND_SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)


def write_admin_snapshot_state(
    league_name: str,
    week: int,
    players: List[Dict[str, Any]],
    teams: List[Dict[str, Any]],
) -> None:
    """
    players: list of dicts like:
    {
        "name": "Jeff",
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
    _ensure_state_dir()
    data: Dict[str, Any] = {
        "league_name": league_name,
        "week": week,
        "players": players,
        "teams": teams,
    }
    with open(ADMIN_SNAPSHOT_FILE, "w") as f:
        json.dump(data, f, indent=2)
