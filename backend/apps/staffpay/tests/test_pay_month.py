"""apps/staffpay/tests/test_pay_month.py — the month's pay of everyone, and one worker's, as Mishahara and the worker's
page show it (WAGE-2; spec §8.1, 02 §12): pay_month and worker_pay (apps/staffpay/services.py).

Today is Tuesday 24 November 2026 at MPC, at 10:00, so the pay counts up to Monday 23:

    Asha    Mon 16 Nov  full day            10,000
            Tue 17 Nov  late, 07:50         10,000 less 500
            Wed 18 Nov  the morning's half   5,000
            Thu 19 Nov  no Toka             waits for a decision
            to pay                          24,500, and 1 day waits

And on Tuesday evening, once Asha taps Toka, today counts too, as Leo, less today's share of the meals (Jack: A), judged
by the book's own rule and never kept:

            Leo, full day                   10,000 less 4,000 of the 8,000 that two ate today

Which days a worker had is the book's (test_attendance_book.py), and what they add up to the sum's (test_pay.py); here,
who is listed, on which days, at which rate, and that nothing is kept. The clock is fixed, so the days are the same
whenever the tests run. The amounts are made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.control.models import EditEvent, FlagKind
from apps.control.services import raise_flag
from apps.core.links import table_of
from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON, ROUNDING_STEP
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import change_worker, hire_again, mark_left
from apps.shops.models import Closure, Shop, Side
from apps.staffpay import services
from apps.staffpay.calculations import PaidAs, Pay, PayLine
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind, DayChoice, MealMoney, PayRate
from apps.staffpay.services import (
    PayMonth,
    WorkerPay,
    add_tap,
    decide_day,
    pay_month,
    record_meal_money,
    set_pay_rate,
    void_meal_money,
    void_tap,
    worker_pay,
)
from apps.staffpay.tests.days import JAN_1, absent_day, doubted_tap, job, kept_day, rule, switch_on, tapped

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER = dt.date(2026, 11, 1)
OCTOBER = dt.date(2026, 10, 1)
# The week before today's: Monday 16 to Saturday 21, then Sunday 22 and Monday 23, yesterday.
MON, TUE, WED, THU, FRI, SAT = (dt.date(2026, 11, day) for day in range(16, 22))
YESTERDAY = dt.date(2026, 11, 23)
TODAY = dt.date(2026, 11, 24)
NOTHING = Decimal("0.00")
# Taps, as kept_day takes them: a full day, a late one, the morning's half, and no Toka.
FULL = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
LATE = ((ClockKind.IN, 7, 50), (ClockKind.OUT, 18, 45))
HALF = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 13, 10))
NO_OUT = ((ClockKind.IN, 7, 20),)


def at(moment: dt.datetime) -> Callable[[], dt.datetime]:
    """A clock stopped at one moment of Arusha's, for timezone.now."""
    return lambda: moment.replace(tzinfo=dt.timezone(dt.timedelta(hours=3)))


@pytest.fixture(autouse=True)
def tuesday_morning(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device) -> None:
    # 10:00 on Tuesday 24 November in Arusha, for every read of the clock. The shop switched attendance on in January,
    # with the demo's made-up fines, and its laptop is where every tap below is made (days.py).
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 24, 10, 0)))
    switch_on(shop_a)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: he decides days, sets rates and types meal money, and is paid by no day.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def paid(shop: Shop, name: str, rate: str = "10000", *, since: dt.date = JAN_1, meals: bool = True) -> StaffMember:
    """A worker since January, paid a made-up daily rate from a day on (WAGE-1)."""
    staff = job(shop, name)
    new_rate(staff, rate, since, meals=meals)
    return staff


def new_rate(staff: StaffMember, rate: str, since: dt.date, *, meals: bool = True) -> None:
    with shop_context(staff.shop_id):
        set_pay_rate(staff, daily_rate=Decimal(rate), effective_from=since, shares_meals=meals, by=None)


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    return paid(shop_a, "Asha")


def typed(by: StaffMember, day: dt.date, amount: str) -> MealMoney:
    with shop_context(by.shop_id):
        shop = Shop.objects.get(pk=by.shop_id)
        return record_meal_money(shop, money_id=uuid.uuid7(), date=day, amount=Decimal(amount), by=by)


def month(shop: Shop, of: dt.date = NOVEMBER) -> PayMonth:
    with shop_context(shop):
        return pay_month(shop, of)


def line_of(answer: PayMonth, name: str) -> WorkerPay:
    return next(worker for worker in answer.workers if worker.display_name == name)


def full(days: int, each: str = "10000.00") -> PayLine:
    return PayLine(PaidAs.FULL, days, Decimal(each), days * Decimal(each))


def half(days: int, each: str = "5000.00") -> PayLine:
    return PayLine(PaidAs.HALF, days, Decimal(each), days * Decimal(each))


def test_november_up_to_yesterday(shop_a: Shop, asha: StaffMember) -> None:
    # The table above.
    for day, taps in ((MON, FULL), (TUE, LATE), (WED, HALF), (THU, NO_OUT)):
        kept_day(asha, *taps, date=day)

    answer = month(shop_a)

    assert (answer.month, answer.today, answer.counted_to) == (NOVEMBER, TODAY, YESTERDAY)
    worker = line_of(answer, "Asha")
    assert (worker.staff_id, worker.left_on) == (asha.pk, None)
    assert worker.pay.lines == (full(2), half(1))
    assert (worker.pay.fined_days, worker.pay.fines) == (1, Decimal("500.00"))
    assert (worker.pay.meal_days, worker.pay.advances) == (0, NOTHING)
    assert (worker.pay.waiting, worker.pay.no_rate) == (1, 0)
    assert worker.total == Decimal("24500.00")
    assert answer.total == Decimal("24500.00")


def test_a_day_still_running_is_not_counted(shop_a: Shop, asha: StaffMember) -> None:
    # In since 07:20 today, with no Toka yet: today pays nothing, and the pay counts up to yesterday.
    kept_day(asha, *FULL, date=YESTERDAY)
    tapped(asha, (ClockKind.IN, 7, 20), date=TODAY)
    worker = line_of(month(shop_a), "Asha")
    assert (worker.today, worker.total) == (None, Decimal("10000.00"))


def test_each_day_is_paid_at_its_own_rate(shop_a: Shop, asha: StaffMember) -> None:
    # A raise from Wednesday 18: Monday and Tuesday at 10,000, Wednesday and Thursday at 12,000, the half day with them.
    for day, taps in ((MON, FULL), (TUE, FULL), (WED, HALF), (THU, FULL)):
        kept_day(asha, *taps, date=day)
    new_rate(asha, "12000", WED)
    worker = line_of(month(shop_a), "Asha")
    assert worker.pay.lines == (full(2), full(1, "12000.00"), half(1, "6000.00"))
    assert worker.total == Decimal("38000.00")


def test_half_a_day_rounds_to_the_step_of_its_own_day(shop_a: Shop) -> None:
    # The shop rounds to 1 shilling until Tuesday, and to 50 from Wednesday: half of 9,025 is 4,513, then 4,500 (A1).
    asha = paid(shop_a, "Asha", "9025")
    rule(shop_a, ROUNDING_STEP, Decimal("50.00"), WED)
    kept_day(asha, *HALF, date=TUE)
    kept_day(asha, *HALF, date=WED)
    assert line_of(month(shop_a), "Asha").pay.lines == (half(1, "4513.00"), half(1, "4500.00"))


def test_the_meals_come_off_as_the_book_split_them(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Monday's 8,000 among Asha and Juma, 4,000 each; the cook came too and pays none.
    juma = paid(shop_a, "Juma")
    cook = paid(shop_a, "Mpishi", meals=False)
    for staff in (asha, juma, cook):
        kept_day(staff, *FULL, date=MON)
    typed(baba, MON, "8000")
    answer = month(shop_a)
    for name in ("Asha", "Juma"):
        worker = line_of(answer, name)
        assert (worker.pay.meal_days, worker.pay.meals, worker.total) == (1, Decimal("4000.00"), Decimal("6000.00"))
    assert (line_of(answer, "Mpishi").pay.meal_days, line_of(answer, "Mpishi").total) == (0, Decimal("10000.00"))
    assert answer.total == Decimal("22000.00")


def test_whatever_moves_a_day_moves_the_pay(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Nothing is saved, so each change shows at the next read: a decision, a tap crossed out, one added, a rate typed,
    # meal money typed and crossed out.
    waits = kept_day(asha, *NO_OUT, date=MON)
    assert (line_of(month(shop_a), "Asha").total, line_of(month(shop_a), "Asha").pay.waiting) == (NOTHING, 1)

    with shop_context(shop_a):
        decide_day(waits, choice=DayChoice.ON_TIME, reason="Alisahau kubonyeza Toka", replaces=None, by=baba)
    assert (line_of(month(shop_a), "Asha").total, line_of(month(shop_a), "Asha").pay.waiting) == (
        Decimal("10000.00"),
        0,
    )

    kept_day(asha, *FULL, date=TUE)
    assert line_of(month(shop_a), "Asha").total == Decimal("20000.00")
    with shop_context(shop_a):
        tuesday = AttendanceEvent.objects.filter(staff=asha, kind=ClockKind.OUT).get()
        void_tap(tuesday, reason="Alibonyeza kimakosa", by=baba)
    assert line_of(month(shop_a), "Asha").total == Decimal("10000.00")
    with shop_context(shop_a):
        add_tap(
            asha,
            tap_id=uuid.uuid7(),
            kind=ClockKind.OUT,
            date=TUE,
            minute=dt.time(13, 10),
            reason="Aliondoka mchana",
            by=baba,
        )
    assert line_of(month(shop_a), "Asha").total == Decimal("15000.00")

    new_rate(asha, "12000", TUE)
    assert line_of(month(shop_a), "Asha").total == Decimal("16000.00")

    money = typed(baba, TUE, "3000")
    assert line_of(month(shop_a), "Asha").total == Decimal("13000.00")
    with shop_context(shop_a):
        void_meal_money(money, reason="Kiasi kimekosewa", by=baba)
    assert line_of(month(shop_a), "Asha").total == Decimal("16000.00")


def test_office_duty_is_paid_and_permission_is_not(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Two days away, each decided by its kind (ATT-6): sent to the bank for the shop, paid; a wedding, unpaid.
    for day, choice, why in ((MON, DayChoice.OFFICE_DUTY, "Alitumwa benki"), (TUE, DayChoice.PERMISSION, "Harusi")):
        away = absent_day(asha, day)
        with shop_context(shop_a):
            decide_day(away, choice=choice, reason=why, replaces=None, by=baba)
    worker = line_of(month(shop_a), "Asha")
    assert (worker.pay.lines, worker.total) == ((full(1),), Decimal("10000.00"))


def test_a_decided_days_fine_comes_off(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # In at 07:50 with no Toka, the book fined nothing and sent the day to a person; Baba decided it was a late day,
    # with its first fine (ATT-6), and that is the fine that comes off.
    waits = kept_day(asha, (ClockKind.IN, 7, 50), date=MON)
    with shop_context(shop_a):
        decide_day(waits, choice=DayChoice.LATE, reason="Alisahau kubonyeza Toka", replaces=None, by=baba)
    worker = line_of(month(shop_a), "Asha")
    assert (worker.pay.fined_days, worker.pay.fines, worker.total) == (1, Decimal("500.00"), Decimal("9500.00"))


def test_only_those_paid_by_the_day_are_listed(shop_a: Shop, baba: StaffMember) -> None:
    # Baba has no rate. Zawadi's starts next month. Both worked this month's days in the book, and neither is paid by
    # it. By name, whatever its first letter.
    paid(shop_a, "Juma")
    paid(shop_a, "asha")
    paid(shop_a, "Zawadi", since=dt.date(2026, 12, 1))
    assert [worker.display_name for worker in month(shop_a).workers] == ["asha", "Juma"]


def test_one_who_left_is_paid_up_to_their_last_day(shop_a: Shop, baba: StaffMember) -> None:
    # Neema left on Wednesday 18: her days up to it, and the day she left said beside her name. Halima left in October:
    # no November day of hers, so no line, though her rate goes on (rates_between).
    neema = paid(shop_a, "Neema")
    for day in (MON, TUE, WED):
        kept_day(neema, *FULL, date=day)
    halima = paid(shop_a, "Halima")
    kept_day(halima, *FULL, date=dt.date(2026, 10, 30))
    with shop_context(shop_a):
        mark_left(neema, left_on=WED, by=baba, reason="Amehama")
        mark_left(halima, left_on=dt.date(2026, 10, 31), by=baba, reason="Amehama")
    answer = month(shop_a)
    assert [(worker.display_name, worker.left_on, worker.total) for worker in answer.workers] == [
        ("Neema", WED, Decimal("30000.00"))
    ]
    october = month(shop_a, OCTOBER)
    assert line_of(october, "Halima").total == Decimal("10000.00")


def test_a_worker_with_only_off_days_is_not_listed(shop_a: Shop, baba: StaffMember) -> None:
    # Neema's last day was Sunday 1 November: no working day of hers in the month, so no line of zeros, as on the
    # attendance month (ATT-5's review).
    neema = paid(shop_a, "Neema")
    with shop_context(shop_a):
        mark_left(neema, left_on=NOVEMBER, by=baba, reason="Amehama")
    assert month(shop_a).workers == []


def test_a_person_hired_again_has_a_line_for_each_job(shop_a: Shop, baba: StaffMember) -> None:
    # Juma left on Monday 16 and was hired again from Thursday 19, at another rate: two jobs, two lines, each with its
    # own days and its own rate (PPL-11).
    juma = paid(shop_a, "Juma")
    kept_day(juma, *FULL, date=MON)
    with shop_context(shop_a):
        mark_left(juma, left_on=MON, by=baba, reason="Amehama")
        again = hire_again(juma, display_name="Juma", started_on=THU, by=None)
    new_rate(again, "12000", THU)
    kept_day(again, *FULL, date=THU)
    lines = [(worker.staff_id, worker.left_on, worker.total) for worker in month(shop_a).workers]
    assert lines == [(juma.pk, MON, Decimal("10000.00")), (again.pk, None, Decimal("12000.00"))]


def test_a_paid_day_with_no_rate_is_counted_not_paid(shop_a: Shop) -> None:
    # Asha worked from Monday, and her rate was typed from Wednesday: Monday and Tuesday are paid nothing, and the page
    # says there are two such days. Thursday she didn't come, which no rate would pay.
    asha = paid(shop_a, "Asha", since=WED)
    for day in (MON, TUE, WED):
        kept_day(asha, *FULL, date=day)
    worker = line_of(month(shop_a), "Asha")
    assert (worker.pay.lines, worker.pay.no_rate, worker.total) == ((full(1),), 2, Decimal("10000.00"))


def test_a_day_the_book_no_longer_answers_is_not_paid(shop_a: Shop, asha: StaffMember, baba: StaffMember) -> None:
    # Asha's first day was typed wrong and moved to Tuesday, Monday's taps crossed out: Monday's row stays in the table
    # (rule 7), and the book no longer answers it, so neither does the pay (ATT-11's review).
    monday = kept_day(asha, *FULL, date=MON)
    kept_day(asha, *FULL, date=TUE)
    with shop_context(shop_a):
        for tap in AttendanceEvent.objects.filter(staff=asha).order_by("trusted_time")[:2]:
            void_tap(tap, reason="Si wake", by=baba)
        asha.refresh_from_db()
        change_worker(asha, version=asha.version, reason="Alianza Jumanne", by=None, started_on=TUE)
        assert AttendanceDay.objects.filter(pk=monday.pk).exists()
    assert line_of(month(shop_a), "Asha").total == Decimal("10000.00")


def test_a_closed_day_pays_nothing_and_waits_once_tapped_on(shop_a: Shop, asha: StaffMember) -> None:
    # The shop closed for a funeral on Monday: Juma stayed home, and Asha had come, so her day waits (ATT-10).
    paid(shop_a, "Juma")
    with shop_context(shop_a):
        Closure.objects.create(shop=shop_a, first_day=MON, last_day=MON, name="Msiba")
    kept_day(asha, *FULL, date=MON)
    answer = month(shop_a)
    assert (line_of(answer, "Asha").pay.waiting, line_of(answer, "Asha").total) == (1, NOTHING)
    assert (line_of(answer, "Juma").pay.waiting, line_of(answer, "Juma").total) == (0, NOTHING)


def test_a_past_month_is_counted_to_its_end(shop_a: Shop, asha: StaffMember) -> None:
    # Any day of October asks for the whole of it, and it is counted to the 31st, a Saturday.
    kept_day(asha, *FULL, date=dt.date(2026, 10, 31))
    answer = month(shop_a, dt.date(2026, 10, 17))
    assert (answer.month, answer.counted_to) == (OCTOBER, dt.date(2026, 10, 31))
    assert line_of(answer, "Asha").total == Decimal("10000.00")


def test_a_month_to_come_has_nobody(shop_a: Shop, asha: StaffMember) -> None:
    # No day of December is over, and none of the calendar's last month ever will be here: an answer, never an error.
    for to_come in (dt.date(2026, 12, 1), dt.date(9999, 12, 1)):
        answer = month(shop_a, to_come)
        assert (answer.month, answer.counted_to, answer.workers, answer.total) == (to_come, None, [], NOTHING)


def test_on_the_first_no_day_is_over(shop_a: Shop, asha: StaffMember, monkeypatch: pytest.MonkeyPatch) -> None:
    # Tuesday 1 December, in the morning: no day of December is over, so nothing is counted to any day. Who is paid by
    # the day today is listed all the same, with nothing to pay yet, and the 1st counts in the evening, as Leo.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 1, 10, 0)))
    answer = month(shop_a, dt.date(2026, 12, 1))
    assert (answer.counted_to, [(line.display_name, line.total) for line in answer.workers]) == (
        None,
        [("Asha", NOTHING)],
    )
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 1, 19, 0)))
    tapped(asha, *FULL, date=dt.date(2026, 12, 1))
    answer = month(shop_a, dt.date(2026, 12, 1))
    assert (answer.counted_to, line_of(answer, "Asha").total) == (None, Decimal("10000.00"))


@pytest.mark.parametrize("closed", [False, True])
def test_a_1st_with_no_work_has_no_day_yet(
    shop_a: Shop, asha: StaffMember, baba: StaffMember, monkeypatch: pytest.MonkeyPatch, closed: bool
) -> None:
    # 1 November 2026 is a Sunday, and 1 January 2027, a Friday, is a holiday: no working day of the month has come, so
    # nobody is listed for want of a day, never of a rate, and the pages can say so (WAGE-2's review). On the 2nd, a
    # working day, everyone paid by the day is listed, with nothing to pay yet.
    first = dt.date(2027, 1, 1) if closed else NOVEMBER
    if closed:
        with shop_context(shop_a):
            Closure.objects.create(shop=shop_a, first_day=first, last_day=first, name="Mwaka mpya")
    monkeypatch.setattr(timezone, "now", at(dt.datetime.combine(first, dt.time(10))))
    answer = month(shop_a, first)
    assert (answer.workers, answer.no_day_yet) == ([], True)
    with shop_context(shop_a):
        assert (worker_pay(shop_a, asha, first).paid_by_day, worker_pay(shop_a, asha, first).no_day_yet) == (
            False,
            True,
        )

    second = first + dt.timedelta(days=1)
    monkeypatch.setattr(timezone, "now", at(dt.datetime.combine(second, dt.time(10))))
    answer = month(shop_a, first)
    assert ([line.display_name for line in answer.workers], answer.no_day_yet) == (["Asha"], False)
    # The 1st is over, though nobody worked it.
    assert answer.counted_to == first


def test_whose_first_day_is_still_to_come(shop_a: Shop, baba: StaffMember) -> None:
    # Zawadi is hired from the 28th, paid from then, and looked at on the 24th: her first working day is to come, so her
    # page says no day is over yet, never that she has no daily pay. Baba works and has none. Neema left in October:
    # nothing of hers is to come. And a month gone by has nothing to come for anyone.
    zawadi = paid(shop_a, "Zawadi", since=dt.date(2026, 11, 28))
    neema = paid(shop_a, "Neema")
    with shop_context(shop_a):
        change_worker(zawadi, version=zawadi.version, reason="Ataanza", by=None, started_on=dt.date(2026, 11, 28))
        mark_left(neema, left_on=dt.date(2026, 10, 31), by=baba, reason="Amehama")
        asked = {
            staff.display_name: (answer.paid_by_day, answer.no_day_yet)
            for staff in (zawadi, baba, neema)
            for answer in [worker_pay(shop_a, StaffMember.objects.get(pk=staff.pk), NOVEMBER)]
        }
        gone_by = worker_pay(shop_a, StaffMember.objects.get(pk=zawadi.pk), OCTOBER)
    assert asked == {"Zawadi": (False, True), "Baba": (False, False), "Neema": (False, False)}
    assert (gone_by.paid_by_day, gone_by.no_day_yet) == (False, False)
    assert (month(shop_a).no_day_yet, month(shop_a, OCTOBER).no_day_yet) == (False, False)
    # A month before the shop switched attendance on had no working day either, and none is to come; nor in December,
    # which isn't running.
    assert [month(shop_a, of).no_day_yet for of in (dt.date(2025, 12, 1), dt.date(2026, 12, 1))] == [False, False]


def test_midnight_between_two_reads_counts_no_day_early(
    shop_a: Shop, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Baba opens the page at 23:59:59 on Monday 23, and the book, a moment later, answers Monday too, as it is Tuesday
    # by then. For this answer Monday is still today: counted up to Sunday 22, and Monday once, as Leo, never twice.
    kept_day(asha, *FULL, date=SAT)
    kept_day(asha, *FULL, date=YESTERDAY)
    reads = iter([YESTERDAY, TODAY, TODAY, TODAY])
    monkeypatch.setattr(services, "shop_today", lambda shop: next(reads))
    answer = month(shop_a)
    assert (answer.today, answer.counted_to) == (YESTERDAY, dt.date(2026, 11, 22))
    worker = line_of(answer, "Asha")
    assert (worker.pay.lines, todays(worker).lines) == ((full(1),), (full(1),))
    assert worker.total == Decimal("20000.00")


def test_the_pay_is_never_kept(shop_a: Shop, asha: StaffMember) -> None:
    # Asked for twice, it writes nothing the second time: the book's days are as they were, and nothing else is kept.
    for day, taps in ((MON, FULL), (TUE, LATE)):
        kept_day(asha, *taps, date=day)
    month(shop_a)
    with shop_context(shop_a):
        before = (AttendanceDay.objects.count(), EditEvent.objects.count(), PayRate.objects.count())
    month(shop_a)
    with shop_context(shop_a):
        assert (AttendanceDay.objects.count(), EditEvent.objects.count(), PayRate.objects.count()) == before


def test_the_month_is_read_in_a_few_queries(shop_a: Shop, baba: StaffMember) -> None:
    # However many workers and days: the book's dozen queries, with the meals' two, one for the rates and one for the
    # step; and today's five, its jobs, taps, closed days, rules and meal money. Counted on the second visit, as on the
    # first every day is new (test_attendance_month.py).
    for name in ("Asha", "Baraka", "Juma", "Zawadi"):
        staff = paid(shop_a, name)
        for day in (MON, TUE, WED, THU, FRI):
            kept_day(staff, *FULL, date=day)
        tapped(staff, *FULL, date=TODAY)
    typed(baba, MON, "8000")
    typed(baba, TODAY, "8000")
    month(shop_a)
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        answer = pay_month(shop_a, NOVEMBER)
    assert len(answer.workers) == 4
    assert len(queries) <= 22


# Leo: today, still running, once the worker taps Toka (Jack: A).


@pytest.fixture
def evening(monkeypatch: pytest.MonkeyPatch) -> None:
    # 19:00 on the same Tuesday: the day's last Toka is tapped, and the day itself isn't over.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 24, 19, 0)))


def todays(worker: WorkerPay) -> Pay:
    assert worker.today is not None
    return worker.today


def test_today_counts_once_toka_is_tapped(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    # Asha leaves the shop for good tonight: yesterday's 10,000, and today's, in one total Baba pays at once.
    kept_day(asha, *FULL, date=YESTERDAY)
    tapped(asha, *FULL, date=TODAY)
    answer = month(shop_a)
    worker = line_of(answer, "Asha")
    # The lines still say the days that are over, up to yesterday; today is apart.
    assert (answer.counted_to, worker.pay.lines) == (YESTERDAY, (full(1),))
    assert todays(worker).lines == (full(1),)
    assert (worker.total, answer.total) == (Decimal("20000.00"), Decimal("20000.00"))


def test_today_is_judged_by_the_days_own_rule(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    # Late at 07:50, out at 18:45: the whole day less the first fine. A half day, out at 13:10. As tomorrow's book will
    # say of them.
    tapped(asha, *LATE, date=TODAY)
    late = todays(line_of(month(shop_a), "Asha"))
    assert (late.lines, late.fined_days, late.fines, late.total) == (
        (full(1),),
        1,
        Decimal("500.00"),
        Decimal("9500.00"),
    )
    juma = paid(shop_a, "Juma")
    tapped(juma, *HALF, date=TODAY)
    assert todays(line_of(month(shop_a), "Juma")).lines == (half(1),)


def test_a_toka_the_rule_cant_judge_waits(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    # Out at 16:00: dharura, and nobody decides a day before it is over. So it pays nothing tonight, and the page says
    # that today waits.
    kept_day(asha, *FULL, date=YESTERDAY)
    tapped(asha, (ClockKind.IN, 7, 20), (ClockKind.OUT, 16, 0), date=TODAY)
    worker = line_of(month(shop_a), "Asha")
    assert (todays(worker).waiting, todays(worker).total, worker.total) == (1, NOTHING, Decimal("10000.00"))
    # Apart from the days that are over: none of those waits.
    assert worker.pay.waiting == 0


def test_a_toka_whose_time_isnt_trusted_waits_tonight(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, evening: None
) -> None:
    # The laptop's clock moved, so her Toka has no time the server trusts, and the rule reads no end to her day. She did
    # tap Toka, and she leaves for good tonight: her page says that today waits, never nothing, or Baba would pay her
    # without it and not know (WAGE-2's review). She ate, so the meals' split counts her.
    juma = paid(shop_a, "Juma")
    kept_day(asha, *FULL, date=YESTERDAY)
    tapped(asha, (ClockKind.IN, 7, 20), date=TODAY)
    doubted_tap(asha, 18, 45, TODAY, kind=ClockKind.OUT)
    tapped(juma, *FULL, date=TODAY)
    typed(baba, TODAY, "8000")
    answer = month(shop_a)
    worker = line_of(answer, "Asha")
    assert (todays(worker).waiting, todays(worker).total, worker.total) == (1, NOTHING, Decimal("10000.00"))
    assert todays(line_of(answer, "Juma")).meals == Decimal("4000.00")


def test_an_untrusted_ingia_waits_before_any_toka(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    # Her Ingia this morning has no trusted time: whatever she taps later, today waits for a decision, so it says so.
    doubted_tap(asha, 7, 20, TODAY)
    assert todays(line_of(month(shop_a), "Asha")).waiting == 1


def test_no_toka_yet_counts_nothing_of_today(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    # Still at work at 19:00, or forgot to tap: nothing of today. And someone who didn't come has no today at all.
    juma = paid(shop_a, "Juma")
    tapped(asha, (ClockKind.IN, 7, 20), date=TODAY)
    answer = month(shop_a)
    assert (line_of(answer, "Asha").today, line_of(answer, "Juma").today) == (None, None)
    assert juma.pk in [line.staff_id for line in answer.workers]


def test_todays_meals_are_split_among_those_who_tapped(shop_a: Shop, baba: StaffMember, evening: None) -> None:
    # 8,000 typed for today. Asha went home, Juma is still at work, and so is the cook: two share it, 4,000 each, so
    # Asha's today is 6,000 (Jack: A). Zawadi didn't come. The cook, gone home too, pays none.
    asha, juma, cook = paid(shop_a, "Asha"), paid(shop_a, "Juma"), paid(shop_a, "Mpishi", meals=False)
    paid(shop_a, "Zawadi")
    tapped(asha, *FULL, date=TODAY)
    tapped(juma, (ClockKind.IN, 7, 20), date=TODAY)
    tapped(cook, *FULL, date=TODAY)
    # None typed yet, none taken.
    assert todays(line_of(month(shop_a), "Asha")).total == Decimal("10000.00")

    typed(baba, TODAY, "8000")

    answer = month(shop_a)
    leaving = todays(line_of(answer, "Asha"))
    assert (leaving.meal_days, leaving.meals, leaving.total) == (1, Decimal("4000.00"), Decimal("6000.00"))
    assert line_of(answer, "Asha").total == Decimal("6000.00")
    assert todays(line_of(answer, "Mpishi")).total == Decimal("10000.00")
    assert line_of(answer, "Juma").today is None
    # Money crossed out is no money, today as on any day.
    with shop_context(shop_a):
        void_meal_money(MealMoney.objects.get(), reason="Kiasi kimekosewa", by=baba)
    assert todays(line_of(month(shop_a), "Asha")).total == Decimal("10000.00")


def test_a_toka_that_waits_still_shares_todays_meals(shop_a: Shop, baba: StaffMember, evening: None) -> None:
    # Juma left at 16:00, so his day waits, but he ate: the split counts him, and takes nothing from him tonight.
    asha, juma = paid(shop_a, "Asha"), paid(shop_a, "Juma")
    tapped(asha, *FULL, date=TODAY)
    tapped(juma, (ClockKind.IN, 7, 20), (ClockKind.OUT, 16, 0), date=TODAY)
    typed(baba, TODAY, "8000")
    answer = month(shop_a)
    assert todays(line_of(answer, "Asha")).meals == Decimal("4000.00")
    assert todays(line_of(answer, "Juma")).total == NOTHING


def test_a_toka_with_no_ingia_waits_tonight(shop_a: Shop, baba: StaffMember, evening: None) -> None:
    # Juma forgot Ingia this morning and tapped Toka at 18:45: nobody knows when he came, so today waits, and he ate, so
    # the meals' split counts him.
    asha, juma = paid(shop_a, "Asha"), paid(shop_a, "Juma")
    tapped(asha, *FULL, date=TODAY)
    tapped(juma, (ClockKind.OUT, 18, 45), date=TODAY)
    typed(baba, TODAY, "8000")
    answer = month(shop_a)
    assert (todays(line_of(answer, "Juma")).waiting, todays(line_of(answer, "Juma")).total) == (1, NOTHING)
    assert todays(line_of(answer, "Asha")).meals == Decimal("4000.00")


def test_a_suspended_workers_taps_wait_tonight(shop_a: Shop, baba: StaffMember, evening: None) -> None:
    # Baba suspended Juma at 11:00, and the laptop, offline, let his Toka through: the push flags the tap (X2), and
    # whether today is paid is a person's call, never the rule's, however ordinary its taps (ATT-11). He ate, so the
    # split counts him until someone decides.
    asha, juma = paid(shop_a, "Asha"), paid(shop_a, "Juma")
    for staff in (asha, juma):
        kept_day(staff, *FULL, date=YESTERDAY)
        tapped(staff, *FULL, date=TODAY)
    with shop_context(shop_a):
        toka = AttendanceEvent.objects.get(staff=juma, kind=ClockKind.OUT, trusted_time__date=TODAY)
        line = cast(Any, table_of("pushed_document")).objects.create(
            shop=shop_a,
            device=toka.device,
            device_seq=toka.device_seq,
            client_time=toka.client_time,
            received_at=toka.received_at,
            created_by=juma,
            document_id=toka.pk,
            type="clock",
            schema_version=2,
            status="accepted",
        )
        raise_flag(kind=FlagKind.SUSPENDED_STAFF_ACTIVITY, subject=line, people=[juma], by=None)
    typed(baba, TODAY, "8000")
    answer = month(shop_a)
    assert (todays(line_of(answer, "Juma")).waiting, line_of(answer, "Juma").total) == (1, Decimal("10000.00"))
    assert todays(line_of(answer, "Asha")).meals == Decimal("4000.00")


def test_the_taps_of_one_gone_before_today_wait(shop_a: Shop, baba: StaffMember, evening: None) -> None:
    # Neema's last day was yesterday, and she tapped all day today: a day outside her job, for a person to decide.
    neema = paid(shop_a, "Neema")
    kept_day(neema, *FULL, date=YESTERDAY)
    with shop_context(shop_a):
        mark_left(neema, left_on=YESTERDAY, by=baba, reason="Amehama")
    tapped(neema, *FULL, date=TODAY)
    worker = line_of(month(shop_a), "Neema")
    assert (todays(worker).waiting, worker.total) == (1, Decimal("10000.00"))


def test_todays_share_rounds_to_todays_step(shop_a: Shop, baba: StaffMember, evening: None) -> None:
    # From today the shop rounds to 50: 8,000 among three is 2,666.67, so 2,650.
    rule(shop_a, ROUNDING_STEP, Decimal("50.00"), TODAY)
    for name in ("Asha", "Baraka", "Juma"):
        tapped(paid(shop_a, name), *FULL, date=TODAY)
    typed(baba, TODAY, "8000")
    assert todays(line_of(month(shop_a), "Asha")).meals == Decimal("2650.00")


def test_today_is_paid_at_todays_rate(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    new_rate(asha, "12000", TODAY)
    tapped(asha, *FULL, date=TODAY)
    assert todays(line_of(month(shop_a), "Asha")).lines == (full(1, "12000.00"),)


def test_a_first_rate_still_to_come_lists_nobody(shop_a: Shop, evening: None) -> None:
    # Her first rate starts tomorrow: nobody pays her for today, so she has no line yet. A worker listed always has a
    # rate today, as a rate never ends.
    asha = paid(shop_a, "Asha", since=dt.date(2026, 11, 25))
    tapped(asha, *FULL, date=TODAY)
    assert month(shop_a).workers == []


def test_one_who_starts_today_is_listed(shop_a: Shop, evening: None) -> None:
    # Zawadi's first day is today, paid from today: listed, with today alone.
    zawadi = paid(shop_a, "Zawadi", since=TODAY)
    with shop_context(shop_a):
        change_worker(zawadi, version=zawadi.version, reason="Ameanza leo", by=None, started_on=TODAY)
    tapped(zawadi, *FULL, date=TODAY)
    worker = line_of(month(shop_a), "Zawadi")
    assert (worker.pay.lines, todays(worker).lines, worker.total) == ((), (full(1),), Decimal("10000.00"))


def test_one_who_left_today_is_paid_for_today(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, evening: None
) -> None:
    # She taps Toka, and Baba marks her gone tonight: her last day is today, and it stays in her pay.
    kept_day(asha, *FULL, date=YESTERDAY)
    tapped(asha, *FULL, date=TODAY)
    with shop_context(shop_a):
        mark_left(asha, left_on=TODAY, by=baba, reason="Amehama")
    worker = line_of(month(shop_a), "Asha")
    assert (worker.left_on, worker.total) == (TODAY, Decimal("20000.00"))


def test_a_person_hired_again_today_shares_todays_meals_once(shop_a: Shop, baba: StaffMember, evening: None) -> None:
    # Juma left this morning and was hired again at noon: two jobs, tapped on both, and he ate once (Jack: A). His share
    # is on the job he had first.
    juma, asha = paid(shop_a, "Juma"), paid(shop_a, "Asha")
    tapped(asha, *FULL, date=TODAY)
    tapped(juma, *HALF, date=TODAY)
    with shop_context(shop_a):
        mark_left(juma, left_on=TODAY, by=baba, reason="Amehama")
        again = hire_again(juma, display_name="Juma", started_on=TODAY, by=None)
    new_rate(again, "10000", TODAY)
    tapped(again, (ClockKind.IN, 12, 30), (ClockKind.OUT, 18, 45), date=TODAY)
    typed(baba, TODAY, "8000")
    answer = month(shop_a)
    meals = {line.staff_id: todays(line).meals for line in answer.workers}
    assert meals == {asha.pk: Decimal("4000.00"), juma.pk: Decimal("4000.00"), again.pk: NOTHING}


def test_a_sunday_and_a_closed_day_have_no_today(
    shop_a: Shop, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sunday 22: off, whatever was tapped. And Monday 23, closed for a funeral: a tap sends it to a person, so it waits.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 22, 19, 0)))
    kept_day(asha, *FULL, date=SAT)
    tapped(asha, *FULL, date=dt.date(2026, 11, 22))
    assert line_of(month(shop_a), "Asha").today is None
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 23, 19, 0)))
    with shop_context(shop_a):
        Closure.objects.create(shop=shop_a, first_day=YESTERDAY, last_day=YESTERDAY, name="Msiba")
    tapped(asha, *FULL, date=YESTERDAY)
    assert (todays(line_of(month(shop_a), "Asha")).waiting, line_of(month(shop_a), "Asha").total) == (
        1,
        Decimal("10000.00"),
    )


def test_attendance_switched_off_today_counts_nothing_of_it(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    kept_day(asha, *FULL, date=YESTERDAY)
    tapped(asha, *FULL, date=TODAY)
    rule(shop_a, ATTENDANCE_ON, False, TODAY)
    worker = line_of(month(shop_a), "Asha")
    assert (worker.today, worker.total) == (None, Decimal("10000.00"))


def test_a_past_month_has_no_today(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    kept_day(asha, *FULL, date=dt.date(2026, 10, 30))
    tapped(asha, *FULL, date=TODAY)
    worker = line_of(month(shop_a, OCTOBER), "Asha")
    assert (worker.today, worker.total) == (None, Decimal("10000.00"))


def test_today_is_never_kept(shop_a: Shop, asha: StaffMember, evening: None) -> None:
    # Judged, and not written: today's row is the book's to keep, once the day is over.
    kept_day(asha, *FULL, date=YESTERDAY)
    tapped(asha, *FULL, date=TODAY)
    month(shop_a)
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        pay_month(shop_a, NOVEMBER)
        assert not AttendanceDay.objects.filter(date=TODAY).exists()
    # And locks nothing of its own: the jobs are locked once, by the book, whose days are over, and let go as it
    # commits, so a tap, a PIN or another page never waits for today's line.
    assert sum("FOR NO KEY UPDATE" in query["sql"] for query in queries) == 1


def test_tomorrow_the_book_says_the_same_of_today(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, evening: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # What Baba pays tonight is what tomorrow's page says, from the same taps and the same money, as one rule judges
    # both: 10,000 less the first fine less 4,000 of meals.
    juma = paid(shop_a, "Juma")
    tapped(asha, *LATE, date=TODAY)
    tapped(juma, *FULL, date=TODAY)
    typed(baba, TODAY, "8000")
    tonight = line_of(month(shop_a), "Asha")
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 25, 8, 0)))
    tomorrow = line_of(month(shop_a), "Asha")
    assert (tonight.total, tomorrow.total) == (Decimal("5500.00"), Decimal("5500.00"))
    assert (tonight.today is not None, tomorrow.today) == (True, None)
    assert tomorrow.pay == todays(tonight)


def test_one_workers_pay_is_their_line_of_the_month(shop_a: Shop, asha: StaffMember) -> None:
    # The worker's page and Mishahara never say two different totals: it is the same line.
    paid(shop_a, "Juma")
    for day, taps in ((MON, FULL), (TUE, LATE), (THU, NO_OUT)):
        kept_day(asha, *taps, date=day)
    tapped(asha, *FULL, date=TODAY)
    with shop_context(shop_a):
        answer = worker_pay(shop_a, asha, NOVEMBER)
    whole = month(shop_a)
    assert (answer.month, answer.today, answer.counted_to) == (whole.month, whole.today, whole.counted_to)
    assert answer.paid_by_day is True
    assert answer.worker == line_of(whole, "Asha")


def test_a_worker_not_paid_by_the_day_has_no_pay(shop_a: Shop, baba: StaffMember) -> None:
    # Baba's own page: he has no rate, so there is nothing to pay him, and the page can say why.
    with shop_context(shop_a):
        answer = worker_pay(shop_a, baba, NOVEMBER)
    assert answer.paid_by_day is False
    assert (answer.worker.display_name, answer.worker.pay.lines, answer.worker.total) == ("Baba", (), NOTHING)


def test_another_shop_is_refused(shop_a: Shop, shop_b: Shop, asha: StaffMember) -> None:
    # Asked inside another shop's visit, the guard would hide every row, and the pay would be nothing without a word:
    # so it fails loudly (ADR-0022). And a job of another shop is never answered (T1).
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        pay_month(shop_a, NOVEMBER)
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        worker_pay(shop_b, asha, NOVEMBER)


def test_a_moment_is_no_month(shop_a: Shop) -> None:
    # A datetime is a kind of date in Python, but a moment, not the shop's day: refused, as the book refuses one.
    with shop_context(shop_a), pytest.raises(TypeError):
        pay_month(shop_a, dt.datetime(2026, 11, 1, tzinfo=dt.UTC))
