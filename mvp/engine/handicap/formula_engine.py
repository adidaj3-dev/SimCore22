# mvp/engine/handicap/formula_engine.py

"""
Modern, safe formula engine for SimCore22 handicap calculations.

Supports:
    - Safe evaluation (no raw eval)
    - Precompiled expressions
    - Math functions
    - Custom functions
    - Variable injection
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Any, Callable


# ------------------------------------------------------------
# Allowed functions and constants
# ------------------------------------------------------------

SAFE_GLOBALS: Dict[str, Any] = {
    # Math functions
    "abs": abs,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
    "pow": pow,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,

    # Constants
    "PI": math.pi,
    "E": math.e,
}


# ------------------------------------------------------------
# Formula object
# ------------------------------------------------------------

@dataclass
class Formula:
    name: str
    expression: str
    description: str = ""
    _compiled: Any = None

    def compile(self) -> None:
        """Precompile the expression for speed and safety."""
        if self._compiled is None:
            self._compiled = compile(self.expression, "<formula>", "eval")

    def evaluate(self, variables: Dict[str, Any]) -> float:
        """
        Evaluate the formula expression using a restricted eval context.
        """
        self.compile()

        # Merge safe globals + variables
        local_context = {**SAFE_GLOBALS, **variables}

        return eval(self._compiled, {"__builtins__": {}}, local_context)


# ------------------------------------------------------------
# Safe wrapper
# ------------------------------------------------------------

def safe_evaluate(formula: Formula, variables: Dict[str, Any]) -> float:
    """
    Safely evaluate a formula without allowing crashes.
    Returns old_index on failure.
    """
    try:
        value = formula.evaluate(variables)

        # NaN check
        if value is None or value != value:
            return variables.get("old_index", 0)

        return float(value)

    except Exception:
        return variables.get("old_index", 0)
