from typing import Dict, Any
from simcore22.engine.handicap.registry import (
    register_formula,
    get_formula,
    list_formulas,
)
from .validators import validate_formula_expression


class FormulaAdminAPI:
    """
    Admin API for managing handicap formulas.
    """

    def create_formula(self, name: str, expression: str, description: str = "") -> Dict[str, Any]:
        validate_formula_expression(expression)
        register_formula(name, expression, description)
        return {"status": "ok", "message": f"Formula '{name}' created."}

    def get_formula(self, name: str) -> Dict[str, Any]:
        formula = get_formula(name)
        return {
            "name": formula.name,
            "expression": formula.expression,
            "description": formula.description,
        }

    def list_formulas(self):
        return {"formulas": list_formulas()}

    def test_formula(self, name: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        formula = get_formula(name)
        result = formula.evaluate(variables)
        return {"formula": name, "result": result}