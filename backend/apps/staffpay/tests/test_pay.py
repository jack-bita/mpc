"""apps/staffpay/tests/test_pay.py — what a worker is paid (WAGE-2; spec §8.1, 02 §15, 8): the sum, with no database.

    Juma, 10,000 a day:  on time          10,000
                         late, fine 500   10,000 less 500
                         half a day        5,000
                         waits                —    until someone decides the day
                         half, fine 6,000  5,000 less 5,000: a day stops at 0, and never takes from his other days

Each day is paid alone, with its own rate, fine and decision. Where the days come from, and who is listed, is
test_pay_month.py's; here, only the sum. The amounts are made up (rule 10).
"""

from decimal import Decimal, localcontext

import pytest

from apps.staffpay.calculations import DayToPay, PaidAs, PaidDay, pay_day
from apps.staffpay.models import AbsenceType, DayStatus

RATE = Decimal("10000.00")
NOTHING = Decimal("0.00")


def a_day(
    status: DayStatus,
    *,
    fine: str = "0.00",
    decided: DayStatus | str = "",
    absence: AbsenceType | str = "",
    decided_fine: str | None = None,
    meal_share: str = "0.00",
    rate: str | None = "10000.00",
    step: str = "1.00",
) -> DayToPay:
    """One of Juma's days, as the pay reads it: 10,000 a day, nobody decided it, no fine and no meals, unless the test
    says otherwise."""
    return DayToPay(
        status=status,
        fine=Decimal(fine),
        decided_status=decided,
        absence_type=absence,
        decided_fine=None if decided_fine is None else Decimal(decided_fine),
        meal_share=Decimal(meal_share),
        rate=None if rate is None else Decimal(rate),
        step=Decimal(step),
    )


def test_a_full_day_pays_the_days_rate() -> None:
    # On time: the whole of the rate. Late: the whole of it too, less the fine, which is a line of its own.
    assert pay_day(a_day(DayStatus.ON_TIME)) == PaidDay(PaidAs.FULL, RATE, NOTHING)
    assert pay_day(a_day(DayStatus.LATE, fine="500.00")) == PaidDay(PaidAs.FULL, RATE, Decimal("500.00"))


def test_a_half_day_pays_half_the_rate() -> None:
    assert pay_day(a_day(DayStatus.HALF)) == PaidDay(PaidAs.HALF, Decimal("5000.00"), NOTHING)
    # The morning's half day of a late arrival keeps its fine (the owner, 19 Nov 2026).
    late = a_day(DayStatus.HALF, fine="500.00")
    assert pay_day(late) == PaidDay(PaidAs.HALF, Decimal("5000.00"), Decimal("500.00"))


def test_half_a_day_is_rounded_once_to_the_shops_step() -> None:
    # 9,001 ÷ 2 is 4,500.50: nobody has 50 cents to give, so 4,501, half-up, as every amount (ADR-0024).
    assert pay_day(a_day(DayStatus.HALF, rate="9001.00")).amount == Decimal("4501.00")
    # A shop that rounds to 50: 9,025 ÷ 2 is 4,512.50, so 4,500; and 9,050 ÷ 2 is 4,525, half-way, so up.
    assert pay_day(a_day(DayStatus.HALF, rate="9025.00", step="50.00")).amount == Decimal("4500.00")
    assert pay_day(a_day(DayStatus.HALF, rate="9050.00", step="50.00")).amount == Decimal("4550.00")
    # A full day is the rate the owner typed, never rounded: the 25 are his own.
    assert pay_day(a_day(DayStatus.ON_TIME, rate="9025.00", step="50.00")).amount == Decimal("9025.00")


def test_half_a_day_is_exact_whatever_the_thread_rounds_to() -> None:
    # Other code may lower the digits a thread keeps: with 4, 123,457 ÷ 2 would come out as 61,730, not 61,729.
    with localcontext(prec=4):
        assert pay_day(a_day(DayStatus.HALF, rate="123457.00")).amount == Decimal("61729.00")


def test_an_absent_day_pays_nothing() -> None:
    assert pay_day(a_day(DayStatus.ABSENT)) == PaidDay(PaidAs.NOTHING, NOTHING, NOTHING)
    # With permission, or a no-show: both unpaid (spec §8.1).
    for absence in (AbsenceType.PERMISSION, AbsenceType.NO_SHOW):
        away = a_day(DayStatus.ABSENT, decided=DayStatus.ABSENT, absence=absence, decided_fine="0.00")
        assert pay_day(away) == PaidDay(PaidAs.NOTHING, NOTHING, NOTHING)


def test_office_duty_pays_a_full_day() -> None:
    # Kept as an absence with its kind, as they never came to the shop, but paid: they worked for it elsewhere.
    away = a_day(DayStatus.ABSENT, decided=DayStatus.ABSENT, absence=AbsenceType.OFFICE_DUTY, decided_fine="0.00")
    assert pay_day(away) == PaidDay(PaidAs.FULL, RATE, NOTHING)


def test_a_day_to_decide_waits_unpaid() -> None:
    assert pay_day(a_day(DayStatus.NEEDS_REVIEW)) == PaidDay(PaidAs.WAITS, NOTHING, NOTHING)


def test_the_decision_comes_before_the_book() -> None:
    # Juma's Thursday, no Toka: Meneja decided it was half a day, with the fine of his 07:50 (A2, ATT-6).
    decided = a_day(DayStatus.NEEDS_REVIEW, decided=DayStatus.HALF, decided_fine="500.00")
    assert pay_day(decided) == PaidDay(PaidAs.HALF, Decimal("5000.00"), Decimal("500.00"))
    # The book fined him 1,500; Baba decided he was on time, so the book's fine goes with the book's answer.
    forgiven = a_day(DayStatus.LATE, fine="1500.00", decided=DayStatus.ON_TIME, decided_fine="0.00")
    assert pay_day(forgiven) == PaidDay(PaidAs.FULL, RATE, NOTHING)
    # And the other way: on time by the book, sent home sick at 10:00.
    sick = a_day(DayStatus.ON_TIME, decided=DayStatus.HALF, decided_fine="0.00")
    assert pay_day(sick) == PaidDay(PaidAs.HALF, Decimal("5000.00"), NOTHING)


def test_an_off_day_pays_nothing_whatever_was_decided() -> None:
    # A closed day with a tap was decided as worked, then its tap was crossed out: the shop was shut, and the day is
    # nobody's, as the meals and the month's counts say (WAGE-7's review).
    assert pay_day(a_day(DayStatus.OFF)) == PaidDay(PaidAs.NOTHING, NOTHING, NOTHING)
    decided = a_day(DayStatus.OFF, decided=DayStatus.ON_TIME, decided_fine="0.00")
    assert pay_day(decided) == PaidDay(PaidAs.NOTHING, NOTHING, NOTHING)
    fined = a_day(DayStatus.OFF, decided=DayStatus.LATE, decided_fine="500.00")
    assert pay_day(fined) == PaidDay(PaidAs.NOTHING, NOTHING, NOTHING)


def test_a_fine_never_takes_a_day_below_0() -> None:
    # Half a day is 5,000 and the second fine 6,000: the fine takes 5,000, never 1,000 of his other days (Jack: A).
    assert pay_day(a_day(DayStatus.HALF, fine="6000.00")) == PaidDay(
        PaidAs.HALF, Decimal("5000.00"), Decimal("5000.00")
    )
    # Exactly the day's pay: all of it.
    assert pay_day(a_day(DayStatus.HALF, fine="5000.00")).fine == Decimal("5000.00")
    # A decided one too.
    decided = a_day(DayStatus.NEEDS_REVIEW, decided=DayStatus.LATE, decided_fine="12000.00")
    assert pay_day(decided) == PaidDay(PaidAs.FULL, RATE, RATE)


def test_a_paid_day_with_no_rate_pays_nothing_and_says_so() -> None:
    # His first day was moved earlier (PPL-10), and no rate was typed for the new days: nobody knows what they pay, so
    # nothing, and the page says it. No fine either: there is nothing to take it from.
    for status, kind in ((DayStatus.LATE, PaidAs.FULL), (DayStatus.HALF, PaidAs.HALF)):
        no_rate = pay_day(a_day(status, fine="500.00", rate=None))
        assert no_rate == PaidDay(kind, NOTHING, NOTHING, no_rate=True)


@pytest.mark.parametrize("status", [DayStatus.ABSENT, DayStatus.OFF, DayStatus.NEEDS_REVIEW])
def test_a_day_not_paid_needs_no_rate(status: DayStatus) -> None:
    # A day nobody is paid for, or one that waits, isn't told as a day with no rate: there is nothing to type yet.
    assert pay_day(a_day(status, rate=None)).no_rate is False
