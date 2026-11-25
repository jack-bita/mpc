"""apps/staffpay/tests/test_pay_month.py — the month's pay of everyone, and one worker's, as Mishahara and the worker's
page show it (WAGE-2; spec §8.1, 02 §12): pay_month and worker_pay (apps/staffpay/services.py).

Today is Tuesday 24 November 2026 at MPC, at 10:00, so the pay counts up to Monday 23:

    Asha    Mon 16 Nov  full day            10,000
            Tue 17 Nov  late, 07:50         10,000 less 500
            Wed 18 Nov  the morning's half   5,000
            Thu 19 Nov  no Toka             waits for a decision
            to pay                          24,500, and 1 day waits

Which days a worker had is the book's (test_attendance_book.py), and what they add up to the sum's (test_pay.py); here,
who is listed, on which days, at which rate, and that nothing is kept. The clock is fixed, so the days are the same
whenever the tests run. The amounts are made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.control.models import EditEvent
from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ROUNDING_STEP
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import change_worker, hire_again, mark_left
from apps.shops.models import Closure, Shop, Side
from apps.staffpay import services
from apps.staffpay.calculations import PaidAs, PayLine
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
from apps.staffpay.tests.days import JAN_1, absent_day, job, kept_day, rule, switch_on, tapped

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
    assert line_of(month(shop_a), "Asha").total == Decimal("10000.00")


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
    # Tuesday 1 December, in the morning: no day of December is over, so nothing is counted to any day.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 1, 10, 0)))
    assert month(shop_a, dt.date(2026, 12, 1)).counted_to is None


def test_midnight_between_two_reads_counts_no_day_early(
    shop_a: Shop, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Baba opens the page at 23:59:59 on Monday 23, and the book, a moment later, answers Monday too, as it is Tuesday
    # by then. The page says it counts up to Sunday 22, so Monday isn't in it: no day is ever counted twice, once as a
    # day over and once as today.
    kept_day(asha, *FULL, date=SAT)
    kept_day(asha, *FULL, date=YESTERDAY)
    reads = iter([YESTERDAY, TODAY, TODAY, TODAY])
    monkeypatch.setattr(services, "shop_today", lambda shop: next(reads))
    answer = month(shop_a)
    assert (answer.today, answer.counted_to) == (YESTERDAY, dt.date(2026, 11, 22))
    assert line_of(answer, "Asha").total == Decimal("10000.00")


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
    # step. Counted on the second visit, as on the first every day is new (test_attendance_month.py).
    for name in ("Asha", "Baraka", "Juma", "Zawadi"):
        staff = paid(shop_a, name)
        for day in (MON, TUE, WED, THU, FRI):
            kept_day(staff, *FULL, date=day)
    typed(baba, MON, "8000")
    month(shop_a)
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        answer = pay_month(shop_a, NOVEMBER)
    assert len(answer.workers) == 4
    assert len(queries) <= 17


def test_one_workers_pay_is_their_line_of_the_month(shop_a: Shop, asha: StaffMember) -> None:
    # The worker's page and Mishahara never say two different totals: it is the same line.
    paid(shop_a, "Juma")
    for day, taps in ((MON, FULL), (TUE, LATE), (THU, NO_OUT)):
        kept_day(asha, *taps, date=day)
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
