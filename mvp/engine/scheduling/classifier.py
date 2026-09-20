# mvp/engine/scheduling/classifier.py

from __future__ import annotations

from datetime import datetime

from mvp.engine.models.schedule import ScheduleConfig, is_in_window


def classify_round_by_time(now: datetime, schedule: ScheduleConfig) -> str:
    """
    Classify the current round type based on the current time and schedule.

    Returns one of:
        - "league"
        - "tournament"
        - "practice"
        - "one_off"
    """

    if is_in_window(now, schedule.league_windows):
        return "league"

    if is_in_window(now, schedule.tournament_windows):
        return "tournament"

    if is_in_window(now, schedule.practice_windows):
        return "practice"

    return "one_off"
