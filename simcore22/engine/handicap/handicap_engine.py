# simcore22/engine/handicap/handicap_engine.py

from __future__ import annotations


from simcore22.engine.handicap.rounding import round_two_decimals, simcore_round_index
from simcore22.engine.handicap.validators import validate_round_data
from simcore22.engine.handicap.registry import get_formula
from simcore22.engine.handicap.history import record_change as history_record_change
from simcore22.engine.handicap.stats_extractor import extract_stats_from_round

from simcore22.engine.engine import SessionState


def safe_index(value):
    """Ensure index is always a valid integer between 0 and 54."""
    try:
        v = int(round(float(value)))
        return max(0, min(54, v))
    except Exception:
        return 0


class HandicapEngine:
    """
    Modernized handicap engine for SimCore22.
    Consumes engine SessionState instead of ingestion dicts.
    """

    def __init__(self):
        pass

    # ------------------------------------------------------------
    # Initial index
    # ------------------------------------------------------------

    def initial_index(self, outdoor_index: float) -> int:
        return safe_index(outdoor_index)

    def projected_outdoor_index(self, simcore_index: int) -> float:
        return round_two_decimals(simcore_index)

    # ------------------------------------------------------------
    # Compute handicap from engine state
    # ------------------------------------------------------------

    def compute_handicap_for_player(self, player_name: str, session_state: SessionState) -> int:
        """
        Extract stats from engine state and compute new handicap.
        """
        if player_name not in session_state.players:
            return 0

        round_state = session_state.players[player_name]

        # Extract stats from RoundState → HoleState
        stats = extract_stats_from_round(round_state)

        # Validate stats (ensures required fields exist)
        stats = validate_round_data(stats)

        # Use formula engine
        formula = get_formula("SimCore Default")

        variables = {
            "old_index": round_two_decimals(stats.get("old_index", 0)),
            "sim_index": round_two_decimals(stats.get("old_index", 0)),
            "score_relative_to_par": round_two_decimals(stats.get("score_relative_to_par", 0)),
            "round_quality": round_two_decimals(stats.get("round_quality_score", 0)),
            "fir": round_two_decimals(stats.get("fir", 0)),
            "gir": round_two_decimals(stats.get("gir", 0)),
            "penalties": round_two_decimals(stats.get("penalties", 0)),
            "avg_putts": round_two_decimals(stats.get("avg_putts", 0)),
        }

        from simcore22.engine.handicap.formula_engine import safe_evaluate
        raw_value = safe_evaluate(formula, variables)
        rounded_value = round_two_decimals(raw_value)

        return safe_index(simcore_round_index(rounded_value))

    # ------------------------------------------------------------
    # Apply handicap update
    # ------------------------------------------------------------

    def update_player_handicap(self, player_name: str, session_state: SessionState) -> int:
        """
        Compute and record a new handicap index for a player.
        """
        new_index = self.compute_handicap_for_player(player_name, session_state)

        # Record history
        old_index = session_state.players[player_name].__dict__.get("handicap_index", 0)
        history_record_change(player_name, old_index, new_index, "SimCore Default")

        # Store updated index in engine state
        session_state.players[player_name].handicap_index = new_index

        return new_index
