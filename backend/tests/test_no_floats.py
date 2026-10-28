"""backend/tests/test_no_floats.py — stops floats and stray rounding from reaching calculation code (02 M1, ADR-0024).

The calculation code is apps/core/numbers.py and every app's calculations.py (the pure sums, mirrored in
TypeScript). This test reads each file as Python's own parser sees it (the `ast` module, a tree of the
code) and fails on the ways a shilling gets lost that mypy can't see:
- a float written in the code: Decimal(0.35) is already 0.34999…, and mypy accepts it;
- the name `float`: float(text), or a value typed as one;
- the built-in round(): it sends a half to the even number, so round(Decimal("458.5")) is 458, not 459;
- importing math, cmath, statistics or builtins: their sums work in floats, and builtins.round is round();
- outside numbers.py, any other way to round: .quantize() without a rounding= also sends a half to the
  even number, and a ROUND_* mode names a rule of its own. round_money is the one rounding rule (rule 3).
Comments and strings are not code, so "0.5" in a comment or a docstring is fine.

ruff has no rule for this, so it is a test (the card allows either). It sits in backend/tests/ because it
reads every app's files. A new calculations.py, or a calculations/ package, is checked with no change here.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APPS = BACKEND / "apps"
NUMBERS = APPS / "core" / "numbers.py"

FLOAT_MODULES = {"math", "cmath", "statistics", "builtins"}
ROUNDING_METHODS = {"quantize", "to_integral", "to_integral_value", "to_integral_exact"}


def calculation_files() -> list[Path]:
    # numbers.py, and every calculations.py or file inside a calculations/ package, at any depth.
    found = {
        path
        for path in APPS.rglob("*.py")
        if path.name == "calculations.py" or "calculations" in path.relative_to(APPS).parts[:-1]
    }
    return [NUMBERS, *sorted(found)]


def float_problems(source: str, may_round: bool = False) -> list[str]:
    # may_round: only numbers.py, the home of round_money, may call quantize() and name a ROUND_* mode.
    problems = []
    for node in ast.walk(ast.parse(source)):
        # 0.5, 1e3 and 2j are each a number the parser reads as a float (or a complex, built from floats).
        if isinstance(node, ast.Constant) and isinstance(node.value, float | complex):
            problems.append(f"line {node.lineno}: the float {node.value!r}")
        # A plain name, as in float(x), x: float or round(x). A method that happens to be called round
        # (value.round()) is an attribute, not this name, so it is not caught.
        elif isinstance(node, ast.Name) and node.id in {"float", "round"}:
            problems.append(f"line {node.lineno}: {node.id}")
        elif isinstance(node, ast.Import | ast.ImportFrom):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            problems += [f"line {node.lineno}: import {m}" for m in modules if m.split(".")[0] in FLOAT_MODULES]
        elif not may_round and isinstance(node, ast.Attribute) and node.attr in ROUNDING_METHODS:
            problems.append(f"line {node.lineno}: .{node.attr}()")
        # Both forms: ROUND_HALF_EVEN imported by name, and decimal.ROUND_HALF_EVEN.
        elif not may_round and (
            (isinstance(node, ast.Name) and node.id.startswith("ROUND_"))
            or (isinstance(node, ast.Attribute) and node.attr.startswith("ROUND_"))
        ):
            problems.append(f"line {node.lineno}: a rounding mode")
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
        "import math",
        "from statistics import mean",
        "from builtins import round as r",  # round() under another name
    ],
)
def test_float_check_finds_floats(code: str) -> None:
    assert float_problems(code) != []


@pytest.mark.parametrize(
    "code",
    [
        "total = amount.quantize(CENT)",  # no rounding=: a half goes to the even number
        "whole = amount.to_integral_value()",
        "total = amount.quantize(CENT, rounding=ROUND_HALF_EVEN)",
        "mode = decimal.ROUND_DOWN",
    ],
)
def test_rounding_check_finds_other_rounding(code: str) -> None:
    assert float_problems(code) != []
    # numbers.py may: round_money and _fit live there.
    assert float_problems(code, may_round=True) == []


def test_float_check_passes_exact_code() -> None:
    code = '''
"""A docstring may say 0.5, float or round()."""
# So may a comment: 0.35 * 1310, round(458.5).
total = round_money(Decimal("0.35") * 1310, step)
bags = int(Decimal("1335.5") // 50)
shown = value.round()
'''
    assert float_problems(code) == []


def test_no_floats_in_calculation_code() -> None:
    # Never passes on nothing: numbers.py must exist, whatever calculations.py exist beside it.
    assert NUMBERS.is_file()

    found = {
        str(path.relative_to(BACKEND)): float_problems(path.read_text(encoding="utf-8"), may_round=path == NUMBERS)
        for path in calculation_files()
    }

    assert {path: problems for path, problems in found.items() if problems} == {}
