"""apps/staffpay/tests/test_meal_share.py — who pays for a day's meals, and how much each (WAGE-7; 02 §15, 14):
meal_part and meal_share (apps/staffpay/calculations.py), with no database and no clock.

    Monday's meal money 8,000.00
    Asha   on time              → shares it
    Juma   half day             → shares it, the same as a full day
    Neema  on time, the cook    → no: she makes the meals
    Baba   absent, no rate      → no
    8 share it: 1,000.00 each

Which day a worker had, and whose money it was, are the book's (test_attendance_book.py). The amounts are made up: the
repo is public (rule 10).
"""

from decimal import Decimal

import pytest

from apps.staffpay.calculations import MealPart, meal_part, meal_share
from apps.staffpay.models import DayStatus

SHILLING = Decimal("1.00")


def test_e11_meal_shares() -> None:
    # 02 §18, E11. Monday's meal money is 8,000. 8 workers came, one of them only half a day, one late, and so did the
    # cook: 1,000 each, and none for the cook.
    came = [DayStatus.ON_TIME] * 6 + [DayStatus.LATE, DayStatus.HALF]
    parts = [meal_part(status, "", shares_meals=True) for status in came]
    cook = meal_part(DayStatus.ON_TIME, "", shares_meals=False)
    assert (parts.count(MealPart.SHARES), cook) == (8, MealPart.NONE)
    assert meal_share(Decimal("8000.00"), 8, SHILLING) == Decimal("1000.00")
    # In a month where every day's share is 2,000, Asha came 10 days and pays 20,000; Juma came 20 and pays 40,000: a
    # worker pays for the days they came, never a part of the whole month.
    share = meal_share(Decimal("16000.00"), 8, SHILLING)
    assert (share * 10, share * 20) == (Decimal("20000.00"), Decimal("40000.00"))


@pytest.mark.parametrize("status", [DayStatus.ON_TIME, DayStatus.LATE, DayStatus.HALF])
def test_who_came_shares_the_meals(status: DayStatus) -> None:
    # A half day pays a whole share: they ate (spec §8.1).
    assert meal_part(status, "", shares_meals=True) == MealPart.SHARES


@pytest.mark.parametrize("status", [DayStatus.ABSENT, DayStatus.OFF])
def test_who_did_not_come_shares_nothing(status: DayStatus) -> None:
    assert meal_part(status, "", shares_meals=True) == MealPart.NONE


def test_a_day_to_decide_waits() -> None:
    # Nobody knows yet whether they came for the day, so it has no share until a person decides it (02 §12).
    assert meal_part(DayStatus.NEEDS_REVIEW, "", shares_meals=True) == MealPart.WAITS


@pytest.mark.parametrize(
    ("status", "decided", "part"),
    [
        # A day that waited: decided that they came, they share it; decided absent, they don't. Absent is a no-show, a
        # permission, and office duty too, who ate away (Jack: A, 24 Nov 2026): all three are kept as absent (ATT-6).
        (DayStatus.NEEDS_REVIEW, DayStatus.ON_TIME, MealPart.SHARES),
        (DayStatus.NEEDS_REVIEW, DayStatus.LATE, MealPart.SHARES),
        (DayStatus.NEEDS_REVIEW, DayStatus.HALF, MealPart.SHARES),
        (DayStatus.NEEDS_REVIEW, DayStatus.ABSENT, MealPart.NONE),
        # The decision over the book's answer, whichever way it went (A2).
        (DayStatus.ON_TIME, DayStatus.ABSENT, MealPart.NONE),
        (DayStatus.ABSENT, DayStatus.HALF, MealPart.SHARES),
    ],
)
def test_a_decision_says_who_came(status: DayStatus, decided: DayStatus, part: MealPart) -> None:
    assert meal_part(status, decided, shares_meals=True) == part


@pytest.mark.parametrize("decided", [DayStatus.ON_TIME, DayStatus.LATE, DayStatus.HALF, DayStatus.ABSENT])
def test_a_day_the_shop_was_shut_shares_nothing_whatever_was_decided(decided: DayStatus) -> None:
    # Juma tapped on the Friday of a funeral, so his day waited and Baba decided it; then the tap, a mistake, was
    # crossed out, and the day is off, its decision kept beside it (A2). An off day is nobody's to count, as on his
    # month's line, and the table refuses it a share (WAGE-7's review).
    assert meal_part(DayStatus.OFF, decided, shares_meals=True) == MealPart.NONE


@pytest.mark.parametrize("shares_meals", [False, None])
@pytest.mark.parametrize("status", list(DayStatus))
def test_the_cook_and_one_with_no_rate_share_nothing(status: DayStatus, shares_meals: bool | None) -> None:
    # The cook, whose rate says so (WAGE-1), and whoever has no rate in force that day, as the owner, who never
    # clocks in: none of them waits either, as deciding their day moves nobody's share.
    assert meal_part(status, "", shares_meals=shares_meals) == MealPart.NONE


@pytest.mark.parametrize(
    ("money", "sharers", "step", "share"),
    [
        # 8,000 among 7 is 1,142.857…, so 1,143 each: 8,001 in all, a shilling over (02 §15, 14).
        ("8000.00", 7, "1.00", "1143.00"),
        # 1,000 among 3 is 333.333…, so 333 each, a shilling under.
        ("1000.00", 3, "1.00", "333.00"),
        # Half a shilling goes up, as everywhere (ADR-0024): 500 among 8 is 62.5.
        ("500.00", 8, "1.00", "63.00"),
        # A shop that rounds to 50 (money.rounding_step): 1,142.857… is nearest 1,150.
        ("8000.00", 7, "50.00", "1150.00"),
        # One came: he pays it all.
        ("8000.00", 1, "1.00", "8000.00"),
        # More than a column of money could hold while dividing: the sum is exact, never a float's.
        ("999999999999.00", 3, "1.00", "333333333333.00"),
    ],
)
def test_a_share_is_rounded_with_the_shared_function(money: str, sharers: int, step: str, share: str) -> None:
    answer = meal_share(Decimal(money), sharers, Decimal(step))
    assert answer == Decimal(share)
    # Written with two places, as every amount is stored (03 §9), so it reads 1143.00 wherever it is kept.
    assert str(answer) == share


def test_nobody_to_share_means_nobody_pays() -> None:
    # A day whose money was typed and nobody came who shares it: the shop bears it (the plan Jack approved).
    assert str(meal_share(Decimal("8000.00"), 0, SHILLING)) == "0.00"


def test_no_money_no_share() -> None:
    # A day nobody typed, or whose rows are all crossed out.
    assert str(meal_share(Decimal("0.00"), 8, SHILLING)) == "0.00"


def test_a_count_below_nothing_is_a_bug() -> None:
    # Never from the book, which counts heads: a share below 0 would pay workers for eating.
    with pytest.raises(ValueError, match="below"):
        meal_share(Decimal("8000.00"), -1, SHILLING)
