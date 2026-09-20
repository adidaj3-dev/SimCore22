# mvp/engine/models/league.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class LeagueConfig:
    league_id: str

    # Handicap update schedule
    rounds_per_update: int = 2                 # e.g. update every 2 rounds
    include_practice_round: bool = False       # round 0 ignored by default
    update_enabled: bool = True                # only True for leagues

    # Formula selection
    handicap_formula_name: str = "SimCore Default"

    # Tee box adjustments
    tee_adjustment_policy: str = "simple"      # "none", "simple", "custom"
    tee_adjustment_map: Dict[str, int] = field(default_factory=lambda: {
        "forward": -2,
        "middle": 0,
        "back": +2,
    })

    # Course factors (optional)
    slope: float = 113.0
    rating: float = 72.0


@dataclass
class LeagueState:
    league_id: str
    current_round_number: int = 0
    rounds_completed: Dict[str, int] = field(default_factory=dict)

    def mark_round_completed(self, player_name: str) -> None:
        self.rounds_completed[player_name] = (
            self.rounds_completed.get(player_name, 0) + 1
        )
