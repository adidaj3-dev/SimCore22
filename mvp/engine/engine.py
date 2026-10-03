# mvp/engine/engine.py
"""
Live session state and the handlers that update it.

engine_loop routes each event (player, hole, shot, score) to a handler here;
the handlers keep one in-memory SessionState -> RoundState (per player) ->
HoleState (per hole). Nothing is persisted: finished rounds are written out by
engine_loop (state/*.json and data/rounds.jsonl), and handicaps survive between
rounds only in `_handicap_book` until a database exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

from mvp.engine.models.events import ShotEvent, PlayerEvent, HoleEvent, ScoreEvent

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# In-memory state models
# -------------------------------------------------------------------

@dataclass
class HoleState:
    hole_number: int
    par: Optional[int] = None
    strokes: int = 0
    gross_score: Optional[int] = None

    # Filled in by scorecard OCR / future putting detection. None/False means
    # "not observed yet", not "zero" - analyzer.py treats them accordingly.
    putts: int = 0
    fairway_hit: bool = False
    green_in_reg: bool = False
    proximity: Optional[float] = None
    sand: bool = False
    up_and_down_attempt: bool = False
    up_and_down_success: bool = False


@dataclass
class RoundState:
    player_name: str
    holes: Dict[int, HoleState] = field(default_factory=dict)
    current_hole: Optional[int] = None

    # Set once a handicap has been computed for this player (see
    # handicap_engine.HandicapEngine). None means "never computed" - callers
    # should fall back to a configured starting index, not treat it as 0.
    handicap_index: Optional[int] = None
    team_name: Optional[str] = None


@dataclass
class SessionState:
    players: Dict[str, RoundState] = field(default_factory=dict)
    current_player: Optional[str] = None
    current_hole: Optional[int] = None


# Global MVP state
_session_state = SessionState()

# Handicaps survive the end of a round (in memory only - they are lost when the
# engine restarts, which is what a database will fix). Keyed by lower-cased name.
_handicap_book: Dict[str, int] = {}


# -------------------------------------------------------------------
# Session helpers
# -------------------------------------------------------------------

def get_or_create_round_state(name: str) -> RoundState:
    """The player's RoundState in this session, created (with their known handicap) if new."""
    players = _session_state.players
    if name not in players:
        players[name] = RoundState(
            player_name=name,
            handicap_index=_handicap_book.get(name.strip().lower()),
        )
    return players[name]


def find_player(name: str) -> Optional[RoundState]:
    """Existing RoundState for `name`, ignoring case (HUD and scorecard may differ)."""
    wanted = name.strip().lower()
    return next(
        (rs for pname, rs in _session_state.players.items() if pname.strip().lower() == wanted),
        None,
    )


def reset_session() -> None:
    """
    Start a fresh round. Keeps what must carry over: each player's handicap, and
    who is currently playing (the HUD only reports a name when it CHANGES, so
    forgetting the current player would leave the next round's shots unclaimed).
    Hole progress and scores are cleared.
    """
    global _session_state
    for name, round_state in _session_state.players.items():
        if round_state.handicap_index is not None:
            _handicap_book[name.strip().lower()] = round_state.handicap_index

    fresh = SessionState()
    current = _session_state.current_player
    if current:
        old = _session_state.players.get(current)
        fresh.players[current] = RoundState(
            player_name=current,
            handicap_index=_handicap_book.get(current.strip().lower()),
            team_name=old.team_name if old else None,
        )
        fresh.current_player = current
    _session_state = fresh


# -------------------------------------------------------------------
# Public engine API
# -------------------------------------------------------------------

def handle_player_event(event: PlayerEvent) -> None:
    """
    Update current player in session state.
    """
    name = event.player_name.strip()
    if not name:
        return

    round_state = get_or_create_round_state(name)
    _session_state.current_player = name

    if round_state.current_hole is None and _session_state.current_hole is not None:
        round_state.current_hole = _session_state.current_hole

    logger.info("Player: %s", name)


def handle_hole_event(event: HoleEvent) -> None:
    """
    Update current hole in session state.
    """
    hole = event.hole_number
    if hole <= 0:
        return

    _session_state.current_hole = hole

    if _session_state.current_player:
        round_state = get_or_create_round_state(_session_state.current_player)
        round_state.current_hole = hole
        if hole not in round_state.holes:
            round_state.holes[hole] = HoleState(hole_number=hole)

    logger.info("Hole: %d", hole)


def handle_shot_event(event: ShotEvent) -> None:
    """
    Update engine state with a new shot.
    """
    player = _session_state.current_player
    hole = _session_state.current_hole

    # Stamp the shot with who hit it and where (the round log and the
    # per-player stats are built from these).
    if player:
        event.metadata["player_name"] = player
    if hole:
        event.metadata["hole_number"] = hole

    if not player or not hole:
        logger.warning("Shot arrived before a player/hole was known; not counted: %s", event)
        return

    round_state = get_or_create_round_state(player)
    round_state.current_hole = hole

    hole_state = round_state.holes.setdefault(hole, HoleState(hole_number=hole))
    hole_state.strokes += 1

    logger.info(
        "Shot: player=%s hole=%d stroke=%d ball_speed=%s",
        player, hole, hole_state.strokes, event.ball_speed,
    )


def handle_score_event(event: ScoreEvent) -> None:
    """
    Update scorecard / scoring state for a player/hole.
    """
    player = event.player_name.strip()
    hole = event.hole_number

    if not player or hole <= 0:
        return

    round_state = get_or_create_round_state(player)
    hole_state = round_state.holes.setdefault(hole, HoleState(hole_number=hole))

    hole_state.gross_score = event.gross_score
    if event.par is not None:
        hole_state.par = event.par

    logger.info("Score: player=%s hole=%d gross=%s par=%s", player, hole, hole_state.gross_score, hole_state.par)


def get_session_state() -> SessionState:
    """
    Read-only access to current session state (for dashboard, API, etc.).
    """
    return _session_state
