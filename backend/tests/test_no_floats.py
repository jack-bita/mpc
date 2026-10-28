"""backend/tests/test_no_floats.py — stops floats and round() from reaching calculation code (02 M1, ADR-0024).

The calculation code is apps/core/numbers.py and every app's calculations.py (the pure sums, mirrored in
TypeScript). This test reads each file as Python's own parser sees it (the `ast` module, a tree of the
code) and fails on the three ways a shilling gets lost that mypy can't see:
- a float written in the code: Decimal(0.35) is already 0.34999…, and mypy accepts it;
- the name `float`: float(text), or a value typed as one;
- the built-in round(): it sends a half to the even number, so round(Decimal("458.5")) is 458, not 459.
Comments and strings are not code, so "0.5" in a comment or a docstring is fine.

ruff has no rule for this, so it is a test (the card allows either). It sits in backend/tests/ because it
reads every app's files. A new calculations.py is checked with no change here.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
NUMBERS = BACKEND / "apps" / "core" / "numbers.py"


def calculation_files() -> list[Path]:
    return [NUMBERS, *sorted((BACKEND / "apps").glob("*/calculations.py"))]


def float_problems(source: str) -> list[str]:
    problems = []
    for node in ast.walk(ast.parse(source)):
        # 0.5, 1e3 and 2j are each a number the parser reads as a float (or a complex, built from floats).
        if isinstance(node, ast.Constant) and isinstance(node.value, float | complex):
            problems.append(f"line {node.lineno}: the float {node.value!r}")
        # A plain name, as in float(x), x: float or round(x). A method that happens to be called round
        # (value.round()) is an attribute, not this name, so it is not caught.
        elif isinstance(node, ast.Name) and node.id in {"float", "round"}:
            problems.append(f"line {node.lineno}: {node.id}")
    return problems


@pytest.mark.parametrize(
    "code",
    [
        'price = Decimal(0.35) * Decimal("1310")',
        "big = 1e3",
        "odd = 2j",
        "kg = float(text)",
        "total = round(amount)",
        "def total(kg: float) -> Decimal: ...",
    ],
)
def test_float_check_finds_floats(code: str) -> None:
    assert float_problems(code) != []


def test_float_check_passes_exact_code() -> None:
    code = '''
"""A docstring may say 0.5, float or round()."""
# So may a comment: 0.35 * 1310, round(458.5).
CENT = Decimal("0.01")
total = (Decimal("0.35") * 1310).quantize(CENT, rounding=ROUND_HALF_UP)
bags = int(Decimal("1335.5") // 50)
shown = value.round()
'''
    assert float_problems(code) == []


def test_no_floats_in_calculation_code() -> None:
    files = calculation_files()
    # Never passes on nothing: numbers.py is always in the list, whatever calculations.py exist.
    assert NUMBERS in files

    found = {str(path.relative_to(BACKEND)): float_problems(path.read_text(encoding="utf-8")) for path in files}

    assert {path: problems for path, problems in found.items() if problems} == {}
