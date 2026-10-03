# simcore22/engine/leaderboard/leaderboard.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from simcore22.engine.engine import SessionState

ASSUMED_PAR = 4  # for a hole whose par isn't known yet (no scorecard / score event)


@dataclass
class PlayerLeaderboardRow:
    player_name: str
    team_name: str
    gross_score: int
    net_score: int
    points: float
    thru: int
    handicap_index: int
    par_played: int = 0    # par of the holes counted in `thru`
    vs_par: int = 0        # gross_score - par_played


class Leaderboard:
    """
    In-memory leaderboard built from engine SessionState.

      - gross_score: sum of the scores (or shot counts) of holes played
      - thru: number of holes with a score or at least one shot
      - vs_par: gross against the par of those holes (par assumed 4 until known)
      - net_score: gross_score - handicap_index
      - points: placeholder (0.0) until league scoring formats exist
    """

    def __init__(self) -> None:
        self._rows: Dict[str, PlayerLeaderboardRow] = {}

    def update_from_session(self, session_state: SessionState) -> None:
        rows: Dict[str, PlayerLeaderboardRow] = {}

        for player_name, round_state in session_state.players.items():
            gross_total = 0
            par_played = 0
            holes_played = 0

            for h in round_state.holes.values():
                if h.gross_score is not None:
                    gross_total += h.gross_score
                elif h.strokes > 0:
                    gross_total += h.strokes
                else:
                    continue  # seen on the HUD, nothing hit yet
                holes_played += 1
                par_played += h.par if h.par is not None else ASSUMED_PAR

            if holes_played == 0:
                continue

            handicap_index = getattr(round_state, "handicap_index", 0) or 0
            team_name = getattr(round_state, "team_name", "") or ""

            rows[player_name] = PlayerLeaderboardRow(
                player_name=player_name,
                team_name=team_name,
                gross_score=gross_total,
                net_score=gross_total - int(handicap_index),
                points=0.0,  # placeholder for now
                thru=holes_played,
                handicap_index=int(handicap_index),
                par_played=par_played,
                vs_par=gross_total - par_played,
            )

        self._rows = rows

    def get_standings(self) -> List[PlayerLeaderboardRow]:
        """
        Return players sorted by net_score, then gross_score.
        """
        return sorted(
            self._rows.values(),
            key=lambda r: (r.net_score, r.gross_score),
        )

    def to_dict(self) -> List[Dict[str, object]]:
        """JSON-serializable standings, for the web API / live leaderboard."""
        return [
            {
                "position": pos,
                "player_name": row.player_name,
                "team_name": row.team_name,
                "gross_score": row.gross_score,
                "net_score": row.net_score,
                "vs_par": row.vs_par,
                "points": row.points,
                "thru": row.thru,
                "handicap_index": row.handicap_index,
            }
            for pos, row in enumerate(self.get_standings(), start=1)
        ]
