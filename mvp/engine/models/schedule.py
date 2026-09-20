# mvp/engine/models/schedule.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple


TimeWindow = Tuple[datetime, datetime]


@dataclass
class ScheduleConfig:
    """
    Defines when leagues, tournaments, and practice/one-off play occur.

    Each window is a (start_datetime, end_datetime) tuple.
    """
    league_windows: List[TimeWindow] = field(default_factory=list)
    tournament_windows: List[TimeWindow] = field(default_factory=list)
    practice_windows: List[TimeWindow] = field(default_factory=list)


def is_in_window(now: datetime, windows: List[TimeWindow]) -> bool:
    for start, end in windows:
        if start <= now <= end:
            return True
    return False
