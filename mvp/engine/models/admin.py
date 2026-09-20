# mvp/engine/models/admin.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class RoundResult:
    """
    Admin-facing view of a single player's round.

    This is the "Excel-style" row with everything an admin cares about.
    """

    player_name: str
    team_name: str
    round_number: int
    date: datetime
    course_name: str
    tee_box: str

    gross_score: int
    net_score: int
    points_needed: float
    points_won: float
    league_points_total: float

    simcore_index_before: int
    simcore_index_after: int
    formula_used: str

    fir: float
    gir: float
    avg_putts: float
    penalties: int
    score_relative_to_par: int

    metadata: Dict[str, str] = field(default_factory=dict)
