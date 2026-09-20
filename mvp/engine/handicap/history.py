# mvp/engine/handicap/history.py

"""
Handicap history tracking for SimCore22.

Stores a rolling log of handicap index changes with:
    - player_id
    - old_index
    - new_index
    - delta
    - formula
    - timestamp
    - optional metadata (round summary, course, etc.)

This is intentionally simple for MVP but structured for future persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any


# ------------------------------------------------------------
# Dataclass for history entries
# ------------------------------------------------------------

@dataclass
class HandicapHistoryEntry:
    player_id: str
    old_index: int
    new_index: int
    delta: int
    formula: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------
# In-memory rolling history
# ------------------------------------------------------------

_MAX_HISTORY = 500
_HANDICAP_HISTORY: List[HandicapHistoryEntry] = []


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def record_change(
    player_id: str,
    old_index: int,
    new_index: int,
    formula: str,
    metadata: Dict[str, Any] | None = None,
) -> None:
    """
    Record a handicap index change safely.
    """

    if not isinstance(old_index, int) or not isinstance(new_index, int):
        return

    entry = HandicapHistoryEntry(
        player_id=player_id,
        old_index=old_index,
        new_index=new_index,
        delta=new_index - old_index,
        formula=formula or "Unknown",
        metadata=metadata or {},
    )

    _HANDICAP_HISTORY.append(entry)

    # Keep history bounded
    if len(_HANDICAP_HISTORY) > _MAX_HISTORY:
        _HANDICAP_HISTORY.pop(0)


def get_history() -> List[HandicapHistoryEntry]:
    """
    Return the full in-memory history list.
    """
    return list(_HANDICAP_HISTORY)


def get_history_for_player(player_id: str) -> List[HandicapHistoryEntry]:
    """
    Return all history entries for a specific player.
    """
    return [h for h in _HANDICAP_HISTORY if h.player_id == player_id]


def clear_history() -> None:
    """
    Clear all history (admin/debug).
    """
    _HANDICAP_HISTORY.clear()
