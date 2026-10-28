"""apps/core/tests/test_numbers.py — tests for the money and quantity helpers in apps/core/numbers.py.

The shared answer book (shared/test-vectors/, run by backend/tests/test_vectors.py) holds the answers both
languages must give. This file holds what only Python has to prove: E1 from start to finish, and the
inputs the helpers refuse (bad text, a float, a step of 0, factors out of order).
No @pytest.mark.django_db: the helpers are pure, and pytest-django blocks the database here.
The module is imported whole, not by name, so each piece of numbers.py turns its own tests green.
"""

from decimal import Decimal

import pytest

from apps.core import numbers


def test_e1_shown_as_bags_and_kg() -> None:
    # E1 (02 §18): pumba, base unit kg, sold by the 50 kg bag. Opening count 20 bags, sell 3 bags, sell
    # 12.5 kg, a delivery of 10 bags, 2 kg spilled. The movements arrive as text (ADR-0024).
    movements = ["1000", "-150", "-12.5", "500", "-2"]
    on_hand = sum((numbers.parse_quantity(m) for m in movements), Decimal("0"))

    bags, rest = numbers.split_into_units(on_hand, [Decimal("50")])

    assert str(on_hand) == "1335.500"
    assert bags == [26]
    assert str(rest) == "35.500"


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("43000", "43000.00"),
        ("0.5", "0.50"),
        ("-7000", "-7000.00"),  # change given back: money going out
        ("-0", "0.00"),  # never "-0.00" on a screen or a receipt
        ("999999999999.99", "999999999999.99"),  # the most numeric(14,2) holds
    ],
)
def test_money_text_gets_two_places(typed: str, stored: str) -> None:
    assert str(numbers.parse_money(typed)) == stored


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("12.5", "12.500"),
        ("1000", "1000.000"),
        ("-2", "-2.000"),  # spilled: stock going out
        ("0.001", "0.001"),  # one gram, one millilitre, one millimetre
        ("-0", "0.000"),
        ("99999999999.999", "99999999999.999"),  # the most numeric(14,3) holds
    ],
)
def test_quantity_text_gets_three_places(typed: str, stored: str) -> None:
    assert str(numbers.parse_quantity(typed)) == stored


@pytest.mark.parametrize(
    "typed",
    [
        "",
        " 12",  # Decimal() would read these four, but nobody types them as an amount
        "1e3",
        "NaN",
        "1_000",
        "1,000",
        "+12",
        "12.",
        ".5",
        "-",
        "١٢",  # Arabic-Indic digits: Decimal() reads them as 12
        "1.005",  # money has two places: a third would have to be rounded
        "1000000000000",  # 13 digits: more than numeric(14,2) holds
    ],
)
def test_bad_money_text_refused(typed: str) -> None:
    with pytest.raises(ValueError):
        numbers.parse_money(typed)


@pytest.mark.parametrize("typed", ["1.0005", "100000000000", "Infinity", "12 kg"])
def test_bad_quantity_text_refused(typed: str) -> None:
    with pytest.raises(ValueError):
        numbers.parse_quantity(typed)


def test_float_refused() -> None:
    # A float has already lost the exact value (0.35 is stored as 0.34999…), so it is refused, not
    # converted. This is what a bare number in JSON becomes in Python.
    with pytest.raises(TypeError):
        numbers.parse_money(0.35)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        numbers.parse_quantity(12.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("step", ["0", "-50"])
def test_round_money_refuses_a_step_of_zero_or_less(step: str) -> None:
    # A step of 0 leaves nothing to round to; the setting refuses it too (money.rounding_step, CORE-4).
    with pytest.raises(ValueError):
        numbers.round_money(Decimal("458.5"), Decimal(step))


def test_result_finer_than_a_cent_refused() -> None:
    # A step of half a cent gives 1.005, which money can't hold with two places. Writing it as 1.00 or
    # 1.01 would round a second time, past the one rounding rule (ADR-0024), so it is refused.
    with pytest.raises(ValueError):
        numbers.round_money(Decimal("1.0025"), Decimal("0.005"))


@pytest.mark.parametrize(
    "factors",
    [
        ["0"],  # a selling unit of nothing
        ["-50"],
        ["25", "50"],  # smallest first: 1,335.5 kg would show as 53 small bags and never a big one
        ["50", "50"],  # the same size twice: the second always shows 0
    ],
)
def test_split_refuses_bad_factors(factors: list[str]) -> None:
    with pytest.raises(ValueError):
        numbers.split_into_units(Decimal("1335.5"), [Decimal(f) for f in factors])


def test_split_never_rounds_the_rest() -> None:
    # One gram short of another whole bag stays 49.999 kg: the rest is shown as it is, never rounded up.
    bags, rest = numbers.split_into_units(Decimal("1349.999"), [Decimal("50")])

    assert bags == [26]
    assert str(rest) == "49.999"
