# mvp/engine/handicap/registry.py

"""
Modern formula registry for SimCore22 handicap system.

Supports:
    - Built-in formulas
    - Admin overrides
    - Safe lookup
    - Future JSON/DB persistence
"""

from __future__ import annotations

from typing import Dict, Optional

from mvp.engine.handicap.formula_engine import Formula


# ------------------------------------------------------------
# Built-in formulas (default set)
# ------------------------------------------------------------

_BUILTIN_FORMULAS: Dict[str, Formula] = {
    "SimCore Default": Formula(
        name="SimCore Default",
        expression=(
            "old_index + (score_relative_to_par / 4.0) "
            "- (round_quality / 10.0) "
            "+ (penalties * 0.2)"
        ),
    ),
}


# ------------------------------------------------------------
# Admin overrides (in-memory for now)
# ------------------------------------------------------------

_OVERRIDE_FORMULAS: Dict[str, Formula] = {}


# ------------------------------------------------------------
# Registry API
# ------------------------------------------------------------

def register_formula(name: str, expression: str, description: str = "") -> Formula:
    """
    Register or override a formula at runtime (admin feature).
    """
    formula = Formula(name=name, expression=expression, description=description)
    _OVERRIDE_FORMULAS[name] = formula
    return formula


def get_formula(name: str) -> Formula:
    """
    Retrieve a formula by name.
    Priority:
        1. Admin overrides
        2. Built-in formulas
        3. Fallback to SimCore Default
    """
    if name in _OVERRIDE_FORMULAS:
        return _OVERRIDE_FORMULAS[name]

    if name in _BUILTIN_FORMULAS:
        return _BUILTIN_FORMULAS[name]

    return _BUILTIN_FORMULAS["SimCore Default"]


def list_formulas(include_overrides: bool = True) -> Dict[str, Formula]:
    """
    Return a dict of all formulas, optionally including overrides.
    """
    if include_overrides:
        merged = {**_BUILTIN_FORMULAS, **_OVERRIDE_FORMULAS}
        return merged
    return dict(_BUILTIN_FORMULAS)


def reset_overrides() -> None:
    """
    Clear all admin overrides.
    """
    _OVERRIDE_FORMULAS.clear()
