import pytest

from brandpulse.indicators.formula_engine import FormulaEvaluationError, evaluate_formula


def test_formula_engine_uses_numeric_context_and_functions():
    assert evaluate_formula("100 * ln(1 + review_count) / m", {"review_count": 100, "m": 300}) == pytest.approx(1.5383735)


@pytest.mark.parametrize("expression", [
    '__import__("os")',
    "review_count / 0",
    "unknown_field + 1",
])
def test_formula_engine_rejects_unsafe_or_missing_inputs(expression):
    with pytest.raises(FormulaEvaluationError):
        evaluate_formula(expression, {"review_count": 10})
