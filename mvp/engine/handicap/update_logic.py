# mvp/engine/handicap/update_logic.py

from __future__ import annotations

from mvp.engine.models.league import LeagueConfig, LeagueState


def should_update_handicap(
    player_name: str,
    config: LeagueConfig,
    state: LeagueState,
    round_type: str,
) -> bool:
    """
    Decide whether a player's handicap should be updated after a completed round,
    based on league configuration, state, and round type.

    Only league rounds are eligible for handicap updates.
    """

    # Only league rounds affect league handicap
    if round_type != "league":
        return False

    # Handicap updates only apply if enabled
    if not config.update_enabled:
        return False

    # Practice round (round 0)
    if state.current_round_number == 0 and not config.include_practice_round:
        return False

    completed = state.rounds_completed.get(player_name, 0)

    # Update every N rounds (only after at least one completed round)
    return completed > 0 and completed % config.rounds_per_update == 0
