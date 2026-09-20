# mvp/engine/leaderboard/leaderboard.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from mvp.engine.engine import SessionState


@dataclass
class PlayerLeaderboardRow:
    player_name: str
    team_name: str
    gross_score: int
    net_score: int
    points: float
    thru: int
    handicap_index: int


class Leaderboard:
    """
    Simple in-memory leaderboard built from engine SessionState.

    For MVP:
      - gross_score: sum of strokes/gross_score across holes
      - net_score: gross_score - handicap_index
      - points: placeholder (0.0) for now
      - thru: number of holes with a recorded score
    """

    def __init__(self) -> None:
        self._rows: Dict[str, PlayerLeaderboardRow] = {}

    def update_from_session(self, session_state: SessionState) -> None:
        rows: Dict[str, PlayerLeaderboardRow] = {}

        for player_name, round_state in session_state.players.items():
            holes = list(round_state.holes.values())
            if not holes:
                continue

            gross_total = 0
            holes_played = 0

            for h in holes:
                if h.gross_score is not None:
                    gross_total += h.gross_score
                    holes_played += 1
                elif h.strokes is not None:
                    gross_total += h.strokes
                    holes_played += 1

            handicap_index = getattr(round_state, "handicap_index", 0) or 0
            net_score = gross_total - int(handicap_index)

            team_name = getattr(round_state, "team_name", "") or ""

            row = PlayerLeaderboardRow(
                player_name=player_name,
                team_name=team_name,
                gross_score=gross_total,
                net_score=net_score,
                points=0.0,  # placeholder for now
                thru=holes_played,
                handicap_index=int(handicap_index),
            )
            rows[player_name] = row

        self._rows = rows

    def get_standings(self) -> List[PlayerLeaderboardRow]:
        """
        Return players sorted by net_score, then gross_score.
        """
        return sorted(
            self._rows.values(),
            key=lambda r: (r.net_score, r.gross_score),
        )
