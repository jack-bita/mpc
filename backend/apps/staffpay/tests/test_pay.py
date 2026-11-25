"""apps/staffpay/tests/test_pay.py — what a worker is paid (WAGE-2; spec §8.1, 02 §15, 8): the sum, with no database.

    Juma, 10,000 a day:  on time          10,000
                         late, fine 500   10,000 less 500
                         half a day        5,000
                         waits                —    until someone decides the day
                         half, fine 6,000  5,000 less 5,000: a day stops at 0, and never takes from his other days

Each day is paid alone, with its own rate, fine and decision. Then the days are added up, and grouped by what they pay,
so every line of the pay multiplies to what it shows (02 §18, E10 and E11):

    Siku kamili  23 × 9,000   207,000     Faini  3   −1,500
    Nusu siku     2 × 4,500     9,000     an advance −20,000     to pay 194,500

Where the days come from, and who is listed, is test_pay_month.py's; here, only the sum. The amounts are made up
(rule 10).
"""

from decimal import Decimal, localcontext

import pytest

from apps.staffpay.calculations import PAID_AS, DayToPay, PaidAs, PaidDay, Pay, PayLine, pay_day, work_out_pay
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


def test_every_status_is_paid_as_something() -> None:
    # A status added to the days with nothing said of its pay would stop Mishahara from opening, for everyone, the first
    # day it came up: so it fails here instead, at the next run of the tests (WAGE-2's review). Off is asked before the
    # list (_paid_as).
    assert set(PAID_AS) == set(DayStatus) - {DayStatus.OFF}


@pytest.mark.parametrize("status", [DayStatus.ABSENT, DayStatus.OFF, DayStatus.NEEDS_REVIEW])
def test_a_day_not_paid_needs_no_rate(status: DayStatus) -> None:
    # A day nobody is paid for, or one that waits, isn't told as a day with no rate: there is nothing to type yet.
    assert pay_day(a_day(status, rate=None)).no_rate is False


def full(days: int, each: str) -> PayLine:
    """A line of full days: so many, at so much each."""
    return PayLine(PaidAs.FULL, days, Decimal(each), days * Decimal(each))


def half(days: int, each: str) -> PayLine:
    """A line of half days."""
    return PayLine(PaidAs.HALF, days, Decimal(each), days * Decimal(each))


def test_e10_payslip_194500() -> None:
    # 02 §18, E10, spec §8.1's example: 9,000 a day, a first fine of 500. 20 days on time and 3 late are 23 × 9,000; 2
    # half days × 4,500; 3 fines; an advance of 20,000.
    days = (
        [a_day(DayStatus.ON_TIME, rate="9000.00")] * 20
        + [a_day(DayStatus.LATE, fine="500.00", rate="9000.00")] * 3
        + [a_day(DayStatus.HALF, rate="9000.00")] * 2
    )
    assert work_out_pay(days, advances=Decimal("20000.00")) == Pay(
        lines=(full(23, "9000.00"), half(2, "4500.00")),
        fined_days=3,
        fines=Decimal("1500.00"),
        meal_days=0,
        meals=NOTHING,
        advances=Decimal("20000.00"),
        waiting=0,
        no_rate=0,
        total=Decimal("194500.00"),
    )


def test_e11_pay_takes_the_meal_shares() -> None:
    # 02 §18, E11: every day's share is 2,000. Asha came 10 days and pays 20,000 of meals, Juma 20 and pays 40,000: each
    # for the days they came, never a part of the whole month.
    asha = work_out_pay([a_day(DayStatus.ON_TIME, meal_share="2000.00")] * 10)
    assert (asha.meal_days, asha.meals, asha.total) == (10, Decimal("20000.00"), Decimal("80000.00"))
    juma = work_out_pay([a_day(DayStatus.ON_TIME, meal_share="2000.00")] * 20)
    assert (juma.meal_days, juma.meals, juma.total) == (20, Decimal("40000.00"), Decimal("160000.00"))
    # A half day ate as a full one did, so its share is whole; a day with no share counts as no day of meals.
    mixed = work_out_pay([a_day(DayStatus.HALF, meal_share="2000.00"), a_day(DayStatus.ON_TIME)])
    assert (mixed.meal_days, mixed.meals, mixed.total) == (1, Decimal("2000.00"), Decimal("13000.00"))


def test_a_raise_splits_the_lines() -> None:
    # Juma's raise from 15 Nov: 8 days at 10,000, then 6 at 12,000, and a half day of each. The full days first, then
    # the half ones, each in the month's order.
    days = (
        [a_day(DayStatus.ON_TIME)] * 8
        + [a_day(DayStatus.HALF)]
        + [a_day(DayStatus.ON_TIME, rate="12000.00")] * 6
        + [a_day(DayStatus.HALF, rate="12000.00")]
    )
    pay = work_out_pay(days)
    assert pay.lines == (full(8, "10000.00"), full(6, "12000.00"), half(1, "5000.00"), half(1, "6000.00"))
    assert pay.total == Decimal("163000.00")


def test_days_that_pay_the_same_are_one_line() -> None:
    # A rate typed wrong for three days and mended, or lowered and raised again: the days of one amount are one line,
    # wherever they fall in the month. Office duty is a full day among the others.
    days = [
        a_day(DayStatus.ON_TIME),
        a_day(DayStatus.ON_TIME, rate="12000.00"),
        a_day(DayStatus.LATE),
        a_day(DayStatus.ABSENT, decided=DayStatus.ABSENT, absence=AbsenceType.OFFICE_DUTY, decided_fine="0.00"),
    ]
    assert work_out_pay(days).lines == (full(3, "10000.00"), full(1, "12000.00"))


def test_every_line_multiplies_to_what_it_shows() -> None:
    # Two half days at 9,001: 2 × 4,501 is 9,002, where the month rounded at its end would show 9,001 (lesson 3).
    pay = work_out_pay([a_day(DayStatus.HALF, rate="9001.00")] * 2)
    assert pay.lines == (half(2, "4501.00"),)
    assert pay.total == Decimal("9002.00")


def test_a_full_day_and_a_half_of_one_amount_are_two_lines() -> None:
    # Half of 20,000 is 10,000, and so is a full day before the raise: a full day and a half day are never one line.
    pay = work_out_pay([a_day(DayStatus.ON_TIME), a_day(DayStatus.HALF, rate="20000.00")])
    assert pay.lines == (full(1, "10000.00"), half(1, "10000.00"))


def test_the_fines_are_what_was_taken() -> None:
    # Three fines: 500; 6,000 on a half day of 5,000, which takes 5,000; and a late day whose fine is 0, as a shop's is
    # until its owner types one, which is no day fined.
    days = [
        a_day(DayStatus.LATE, fine="500.00"),
        a_day(DayStatus.HALF, fine="6000.00"),
        a_day(DayStatus.LATE, fine="0.00"),
    ]
    pay = work_out_pay(days)
    assert (pay.fined_days, pay.fines) == (2, Decimal("5500.00"))
    assert pay.total == Decimal("19500.00")


def test_days_that_wait_or_have_no_rate_are_counted_and_not_paid() -> None:
    days = [
        a_day(DayStatus.ON_TIME),
        a_day(DayStatus.NEEDS_REVIEW),
        a_day(DayStatus.NEEDS_REVIEW, rate=None),
        a_day(DayStatus.LATE, fine="500.00", rate=None),
        a_day(DayStatus.ABSENT, rate=None),
        a_day(DayStatus.OFF, rate=None),
    ]
    pay = work_out_pay(days)
    assert (pay.waiting, pay.no_rate) == (2, 1)
    assert pay.lines == (full(1, "10000.00"),)
    assert (pay.fined_days, pay.total) == (0, RATE)


def test_the_total_may_be_below_0() -> None:
    # One half day, and a month of meals bigger than it: the worker owes, and the page shows the minus. Never cut to 0
    # here, as a fine is: the meals were eaten.
    days = [a_day(DayStatus.HALF, rate="1000.00", meal_share="2000.00")]
    assert work_out_pay(days).total == Decimal("-1500.00")
    assert work_out_pay([], advances=Decimal("20000.00")).total == Decimal("-20000.00")


def test_no_days_pay_nothing() -> None:
    assert work_out_pay([]) == Pay((), 0, NOTHING, 0, NOTHING, NOTHING, 0, 0, NOTHING)


def test_every_amount_has_two_places() -> None:
    # As every amount is stored and sent (numeric(14,2)): the same text, whatever the days.
    for days in ([], [a_day(DayStatus.HALF, fine="500.00", meal_share="1143.00")]):
        pay = work_out_pay(days)
        amounts = [pay.fines, pay.meals, pay.advances, pay.total, *(line.amount for line in pay.lines)]
        assert all(amount.as_tuple().exponent == -2 for amount in amounts)


def test_the_sum_is_exact_whatever_the_thread_rounds_to() -> None:
    # With 4 digits, 31 days of 12,345 would come out as 382,700, not 382,695.
    with localcontext(prec=4):
        assert work_out_pay([a_day(DayStatus.ON_TIME, rate="12345.00")] * 31).total == Decimal("382695.00")


def test_an_advance_below_0_is_refused() -> None:
    # An advance is money the worker already took: below 0 it would pay them a second time, so it is a bug in our code.
    with pytest.raises(ValueError, match="below 0"):
        work_out_pay([], advances=Decimal("-1.00"))
