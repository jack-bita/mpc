"""backend/tests/test_vectors.py — runs the shared answer book, shared/test-vectors/*.json, in Python (03 §8).

Some sums are done twice: offline on a counter device, in TypeScript, and again on the server, in Python.
If the two differ by one shilling, the sale is flagged as a total mismatch (ADR-0024). So the right answers
are written once, in JSON files, and both languages must pass the very same files: pytest here, Vitest from
UI-1 on. Each case's `name` becomes its test id, so a failure names the case.

This runner lives in backend/tests/, outside `apps`: later files will hold other apps' calculations (sales,
from SALE-1), and a test inside apps/core/tests may import only core (ADR-0035). No database: the
calculations are pure.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from apps.core import numbers

# The repo's shared/ folder, beside backend/: this file is backend/tests/test_vectors.py, two folders down.
VECTORS = Path(__file__).resolve().parents[2] / "shared" / "test-vectors"

# Every vector file a test has loaded, by its path inside VECTORS. cases_in() adds to it while pytest
# collects this module, before any test runs; test_every_vector_file_is_run then compares it with the
# folder, so a file that no test loads turns CI red: an answer book nobody runs would check nothing.
# Every vector test lives in this module, so the record is complete once the module is loaded.
LOADED: set[str] = set()


def _bare_number(text: str) -> Any:
    # json calls this for a number written without quotes (2.5, 2, NaN). Python would read 2.5 as a float,
    # and the exact answer would be lost before any test ran. Every number in the files is text, so a bare
    # one is a mistake in the file. A bare whole number is refused too: one rule, and TypeScript reads
    # every JSON number as a float.
    raise ValueError(f"{text} is a bare number: write it as text, in quotes.")


def read_cases(text: str) -> list[dict[str, Any]]:
    data = json.loads(text, parse_float=_bare_number, parse_int=_bare_number, parse_constant=_bare_number)
    cases: list[dict[str, Any]] = data["cases"]
    # Each name becomes a test id. pytest would quietly rename a second "zero" to "zero1", and a failure
    # could then point at the wrong case.
    names = [case["name"] for case in cases]
    if len(names) != len(set(names)):
        raise ValueError(f"Two cases share a name: {sorted({n for n in names if names.count(n) > 1})}.")
    return cases


def cases_in(file_name: str) -> list[Any]:
    # One pytest case per vector, named by the vector's `name`.
    LOADED.add(file_name)
    text = (VECTORS / file_name).read_text(encoding="utf-8")
    return [pytest.param(case, id=case["name"]) for case in read_cases(text)]


def test_every_vector_file_is_run() -> None:
    # rglob: a file in a subfolder counts too.
    assert {path.relative_to(VECTORS).as_posix() for path in VECTORS.rglob("*.json")} == LOADED


def test_duplicate_case_names_refused() -> None:
    with pytest.raises(ValueError, match="share a name"):
        read_cases('{"cases": [{"name": "zero"}, {"name": "zero"}]}')


@pytest.mark.parametrize("bare", ["2.5", "2", "1e3", "NaN", "-Infinity"])
def test_bare_numbers_refused(bare: str) -> None:
    with pytest.raises(ValueError, match="bare number"):
        read_cases(f'{{"cases": [{{"name": "bad", "amount": {bare}}}]}}')


@pytest.mark.parametrize("case", cases_in("rounding.json"))
def test_vectors_rounding(case: dict[str, Any]) -> None:
    result = numbers.round_money(Decimal(case["amount"]), Decimal(case["step"]))

    # Compared as text, not as numbers: Decimal("459") == Decimal("459.00") and Decimal("-0") == 0, but the
    # text must be exactly what is stored and shown, two places and never "-0.00".
    assert str(result) == case["expect"]


@pytest.mark.parametrize("case", cases_in("units.json"))
def test_vectors_units(case: dict[str, Any]) -> None:
    counts, rest = numbers.split_into_units(Decimal(case["quantity"]), [Decimal(f) for f in case["factors"]])

    assert [str(count) for count in counts] == case["expect"]["counts"]
    assert str(rest) == case["expect"]["rest"]
