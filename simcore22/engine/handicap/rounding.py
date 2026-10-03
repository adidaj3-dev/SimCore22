# simcore22/engine/handicap/rounding.py

"""
Rounding utilities for SimCore22 handicap calculations.

These functions are intentionally simple and predictable:
    - round_two_decimals: safe float rounding
    - simcore_round_index: core SimCore rule for index rounding
"""

from __future__ import annotations


def round_two_decimals(value) -> float:
    """
    Safely round a numeric value to two decimal places.
    Returns 0.0 on invalid input.
    """
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def simcore_round_index(value) -> int:
    """
    Core SimCore rule for handicap index rounding:
        - Convert to float
        - Round to nearest whole number
        - Return integer
    Returns 0 on invalid input.
    """
    try:
        return int(round(float(value)))
    except Exception:
        return 0
