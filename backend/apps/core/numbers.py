"""apps/core/numbers.py — the one way money and quantities are read, rounded and shown (ADR-0024).

A float can't hold 0.35 exactly, so 0.35 kg × 1,310 comes out as 458.4999… and rounds to 458, not 459.
So every amount and quantity here is a Decimal, read from text, never from a float. The same sums run in
TypeScript on counter devices (UI-1); both pass shared/test-vectors/, so they agree to the shilling.
"""

import re
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

# Money is stored with two places (numeric(14,2)), quantities with three (numeric(14,3)) (03 §9).
CENT = Decimal("0.01")
THOUSANDTH = Decimal("0.001")

# What number text must look like before Decimal() reads it: an optional minus, digits, and at most two
# places (money) or three (quantities). Decimal() alone would also read "1e3", "NaN", " 12" and "1_000".
# [0-9], not \d: \d also matches other scripts' digits ("١٢"), and Decimal() reads them as 12.
# 12 and 11 digits before the point: the most numeric(14,2) and numeric(14,3) hold (03 §9).
_MONEY_TEXT = re.compile(r"-?[0-9]{1,12}(\.[0-9]{1,2})?")
_QUANTITY_TEXT = re.compile(r"-?[0-9]{1,11}(\.[0-9]{1,3})?")


def _fit(value: Decimal, places: Decimal) -> Decimal:
    # Writes a value with its column's places: 459 becomes 459.00. It only adds zeros: a value it would
    # have to round is refused, so round_money stays the one place that rounds (ADR-0024).
    fitted = value.quantize(places)
    if fitted != value:
        raise ValueError(f"{value} has more places than {places}.")
    # -0 equals 0 but prints as "-0.00": never on a receipt.
    if fitted == 0:
        return abs(fitted)
    return fitted


def _parse(text: str, shape: re.Pattern[str], places: Decimal) -> Decimal:
    # Money and quantities travel as text (ADR-0024). A float has already lost the exact value, so it is
    # refused, not converted: that is what a number without quotes in JSON becomes.
    if not isinstance(text, str):
        raise TypeError(f"{text!r} is not text: send money and quantities as strings.")
    if not shape.fullmatch(text):
        raise ValueError(f"{text!r} is not a number this column can hold.")
    return _fit(Decimal(text), places)


def parse_money(text: str) -> Decimal:
    return _parse(text, _MONEY_TEXT, CENT)


def parse_quantity(text: str) -> Decimal:
    return _parse(text, _QUANTITY_TEXT, THOUSANDTH)


def round_money(amount: Decimal, step: Decimal) -> Decimal:
    # The one rounding rule (03 §8, ADR-0024): half-up to a multiple of the shop's step (the setting
    # money.rounding_step, default 1 shilling). Count the steps, round that count to a whole number, turn
    # it back into money. ROUND_HALF_UP sends a half away from zero: 458.5 → 459, and -2.5 → -3, so a
    # refund rounds like the sale it reverses. Python's round() would send 458.5 to 458 (half to even).
    if step <= 0:
        raise ValueError(f"A rounding step must be above zero, not {step}.")
    steps = (amount / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return _fit(steps * step, CENT)


def split_into_units(quantity: Decimal, factors: Sequence[Decimal]) -> tuple[list[int], Decimal]:
    # Shows stock as people count it (02 §15, item 1): a quantity in the base unit (kg, L, pcs, m) as whole
    # selling units, biggest first, plus the rest in the base unit. 1,335.5 kg with bags of 50 → 26 bags
    # + 35.5 kg. A factor is a selling unit's size in the base unit (CAT-2); its name doesn't matter here.
    if any(factor <= 0 for factor in factors):
        raise ValueError(f"A selling unit's factor must be above zero: {factors}.")
    # Smallest first would count everything in the small unit; the same size twice always shows 0.
    if any(bigger <= smaller for bigger, smaller in pairwise(factors)):
        raise ValueError(f"Factors go biggest first, each size once: {factors}.")
    counts: list[int] = []
    rest = quantity
    for factor in factors:
        # Decimal's // cuts toward zero: -120 kg is -2 bags and -20 kg, not -3 bags and +30 kg, so stock
        # below zero (ADR-0010) reads like the same stock above zero, with a minus.
        count = rest // factor
        counts.append(int(count))
        rest -= count * factor
    return counts, _fit(rest, THOUSANDTH)
