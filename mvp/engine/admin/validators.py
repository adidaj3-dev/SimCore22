# mvp/engine/admin/validators.py
"""
Validates a handicap formula expression before it's registered.

formula_engine.Formula.evaluate() already runs with no builtins, so a bad
formula can't do real damage - but we still want a clear error *before*
registering it, instead of discovering a typo mid-round. This walks the
parsed expression and rejects anything that isn't plain arithmetic over the
known variable/function names.
"""
from __future__ import annotations

import ast

from mvp.engine.handicap.formula_engine import SAFE_GLOBALS

# Names a formula is allowed to reference. Keep in sync with the `variables`
# dict that HandicapEngine.compute_handicap_for_player builds.
ALLOWED_NAMES = set(SAFE_GLOBALS) | {
    "old_index",
    "sim_index",
    "score_relative_to_par",
    "round_quality",
    "fir",
    "gir",
    "penalties",
    "avg_putts",
}

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load,
    ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.FloorDiv, ast.USub, ast.UAdd,
)


class FormulaValidationError(ValueError):
    pass


def validate_formula_expression(expression: str) -> None:
    """Raise FormulaValidationError if `expression` isn't a safe formula."""
    if not expression or not expression.strip():
        raise FormulaValidationError("Formula expression cannot be empty.")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaValidationError(f"Invalid syntax: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaValidationError(
                f"'{type(node).__name__}' is not allowed in a formula "
                "(only arithmetic over known variables/functions)."
            )
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise FormulaValidationError("Only numeric constants are allowed.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_GLOBALS:
                raise FormulaValidationError("Only the built-in math functions may be called.")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            raise FormulaValidationError(
                f"Unknown name '{node.id}'. Allowed: {', '.join(sorted(ALLOWED_NAMES))}"
            )

    # Make sure it actually evaluates with representative values.
    from mvp.engine.handicap.formula_engine import Formula

    sample = {name: 1.0 for name in ALLOWED_NAMES if name not in SAFE_GLOBALS}
    try:
        Formula(name="__validate__", expression=expression).evaluate(sample)
    except Exception as exc:
        raise FormulaValidationError(f"Formula does not evaluate: {exc}") from exc
