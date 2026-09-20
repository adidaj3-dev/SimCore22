# mvp/engine/handicap/admin_override.py

"""
Admin override utilities for SimCore22 handicap system.

Supports:
    - Manual SimCore index override
    - Manual outdoor index override
    - Recording override history
    - Optional metadata (admin notes, reason codes, etc.)
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from mvp.engine.handicap.history import record_change
from mvp.engine.handicap.rounding import round_two_decimals, simcore_round_index


def apply_admin_override(
    player_id: str,
    current_simcore: float,
    current_outdoor: float,
    simcore_override: Optional[float] = None,
    outdoor_override: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply admin override to SimCore and/or outdoor index.

    Returns:
        {
            "simcore_index": float,
            "outdoor_index": float,
            "simcore_manual_override": bool,
            "outdoor_manual_override": bool,
        }
    """

    # ------------------------------------------------------------
    # Determine new values
    # ------------------------------------------------------------
    new_simcore = (
        simcore_round_index(simcore_override)
        if simcore_override is not None
        else simcore_round_index(current_simcore)
    )

    new_outdoor = (
        round_two_decimals(outdoor_override)
        if outdoor_override is not None
        else round_two_decimals(current_outdoor)
    )

    # ------------------------------------------------------------
    # Record history (only if SimCore index changed)
    # ------------------------------------------------------------
    if new_simcore != current_simcore:
        record_change(
            player_id=player_id,
            old_index=int(current_simcore),
            new_index=int(new_simcore),
            formula="Admin Override",
            metadata=metadata or {},
        )

    # ------------------------------------------------------------
    # Return updated values
    # ------------------------------------------------------------
    return {
        "simcore_index": float(new_simcore),
        "outdoor_index": float(new_outdoor),
        "simcore_manual_override": simcore_override is not None,
        "outdoor_manual_override": outdoor_override is not None,
    }
