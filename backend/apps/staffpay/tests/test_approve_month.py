"""apps/staffpay/tests/test_approve_month.py — a month's pay approved, and read back from its payslips (WAGE-3; 02 §12,
A3): approve_month (apps/staffpay/services/approval.py) and what pay_month answers before and after it.

Today is Tuesday 1 December 2026 at MPC, at 19:05, so November is over, and its 25 working days are Asha's to be paid:

    20 on time, 3 late, 2 half, at 9,000     207,000 + 9,000, less 1,500 of fines and an advance of 20,000
    Baba approves it                         a payslip of 194,500 (E10), and 30 days marked as paid

Attendance is on from 1 November, and the rates start with it, so November is the first month anyone could be paid in.
What a month's draft holds is test_pay_month.py's, and the sum test_pay.py's; what an approved month then refuses is
test_approved_month.py's. The clock is fixed. The amounts are made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.control.models import EditEvent
from apps.core.permissions import Permission, RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON, LATE_FINE
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, DeviceStatus, StaffMember
from apps.people.services import grant_permission, mark_left
from apps.shops.models import Shop, Side
from apps.staffpay.models import (
    Advance,
    AttendanceDay,
    AttendanceEvent,
    ClockKind,
    DayChoice,
    MealMoney,
    PayRate,
    PayRun,
    Payslip,
    PayslipLine,
)
from apps.staffpay.services import (
    Approval,
    OpenDay,
    PayMonth,
    WorkerPay,
    approve_month,
    decide_day,
    pay_month,
    record_advance,
    record_meal_money,
    set_pay_rate,
    void_advance,
    work_out_days,
    worker_pay,
)
from apps.staffpay.services import approval as approval_services
from apps.staffpay.services import pay as pay_services
from apps.staffpay.tests.days import JAN_1, job, kept_day, rule, tapped
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

OCTOBER, NOVEMBER, DECEMBER = dt.date(2026, 10, 1), dt.date(2026, 11, 1), dt.date(2026, 12, 1)
JANUARY = dt.date(2027, 1, 1)
NOTHING = Decimal("0.00")
# November's working days: every one but its five Sundays.
WORKING = [day for day in (dt.date(2026, 11, n) for n in range(1, 31)) if day.weekday() != 6]
MON, TUE, WED = (dt.date(2026, 11, day) for day in (16, 17, 18))
FULL = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
LATE = ((ClockKind.IN, 7, 50), (ClockKind.OUT, 18, 45))
HALF = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 13, 10))
NO_OUT = ((ClockKind.IN, 7, 20),)


def at(moment: dt.datetime) -> Callable[[], dt.datetime]:
    """A clock stopped at one moment of Arusha's, for timezone.now."""
    return lambda: moment.replace(tzinfo=dt.timezone(dt.timedelta(hours=3)))


EVENING = dt.datetime(2026, 12, 1, 19, 5)


@pytest.fixture(autouse=True)
def first_of_december(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device) -> None:
    # 19:05 on Tuesday 1 December in Arusha, for every read of the clock. Attendance is on from 1 November, with a
    # made-up fine of 500, and the shop's laptop is where every tap below is made (days.py); it sent something this
    # evening.
    monkeypatch.setattr(timezone, "now", at(EVENING))
    rule(shop_a, ATTENDANCE_ON, True, NOVEMBER)
    rule(shop_a, LATE_FINE, Decimal("500.00"), NOVEMBER)
    with shop_context(shop_a):
        Device.objects.update(last_synced_at=timezone.now())


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: he holds every key, and is paid by no day.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def paid(shop: Shop, name: str, rate: str = "10000", *, since: dt.date = NOVEMBER) -> StaffMember:
    """A worker since January, paid a made-up daily rate from a day on (WAGE-1)."""
    staff = job(shop, name)
    with shop_context(shop):
        set_pay_rate(staff, daily_rate=Decimal(rate), effective_from=since, by=None)
    return staff


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    return paid(shop_a, "Asha")


def give(staff: StaffMember, by: StaffMember, day: dt.date, amount: str) -> Advance:
    with shop_context(staff.shop_id):
        return record_advance(staff, advance_id=uuid.uuid7(), date=day, amount=Decimal(amount), by=by)


def month(shop: Shop, of: dt.date = NOVEMBER) -> PayMonth:
    with shop_context(shop):
        return pay_month(shop, of)


def line_of(answer: PayMonth, name: str) -> WorkerPay:
    return next(worker for worker in answer.workers if worker.display_name == name)


def totals(answer: PayMonth) -> dict[uuid.UUID, Decimal]:
    """What the page showed, as it sends it back."""
    return {line.staff_id: line.total for line in answer.workers}


def approve(
    shop: Shop, by: StaffMember, of: dt.date = NOVEMBER, *, seen: dict[uuid.UUID, Decimal] | None = None
) -> PayRun:
    """The month read, then approved as it was read."""
    with shop_context(shop):
        shown = totals(pay_month(shop, of)) if seen is None else seen
        return approve_month(shop, of, run_id=uuid.uuid7(), seen=shown, by=by)


def refused(shop: Shop, by: StaffMember, of: dt.date = NOVEMBER, **kwargs: Any) -> ValidationError:
    """The refusal of an approval, which keeps nothing."""
    with shop_context(shop):
        before = (PayRun.objects.count(), Payslip.objects.count(), PayslipLine.objects.count())
    with pytest.raises(ValidationError) as refusal:
        approve(shop, by, of, **kwargs)
    with shop_context(shop):
        assert (PayRun.objects.count(), Payslip.objects.count(), PayslipLine.objects.count()) == before
    return refusal.value


def lines_kept(
    staff: StaffMember, of: dt.date = NOVEMBER
) -> list[tuple[str, int | None, str | None, dt.date | None, str]]:
    """The lines of a payslip, in their order, as the table keeps them."""
    with shop_context(staff.shop_id):
        return [
            (line.kind, line.days, None if line.each is None else str(line.each), line.date, str(line.amount))
            for line in PayslipLine.objects.filter(payslip__staff=staff, payslip__month=of).order_by("position")
        ]


def test_baba_approves_november(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    juma = paid(shop_a, "Juma")
    for day in (MON, TUE, WED):
        kept_day(asha, *FULL, date=day)
    kept_day(juma, *LATE, date=MON)
    kept_day(juma, *HALF, date=TUE)
    shown = month(shop_a)
    assert (shown.approval, [line.approval for line in shown.workers]) == (None, [None, None])

    run = approve(shop_a, baba)

    assert (run.month, run.created_by_id, run.created_at) == (NOVEMBER, baba.pk, timezone.now())
    with shop_context(shop_a):
        kept = {slip.staff_id: (slip.total, slip.pay_run_id, slip.created_by_id) for slip in Payslip.objects.all()}
    assert kept == {
        asha.pk: (Decimal("30000.00"), run.pk, baba.pk),
        juma.pk: (Decimal("14500.00"), run.pk, baba.pk),
    }
    answer = month(shop_a)
    said = Approval(by="Baba", at=timezone.now())
    assert (answer.approval, answer.to_approve) == (said, None)
    assert (answer.counted_to, answer.total) == (dt.date(2026, 11, 30), Decimal("44500.00"))
    # Each worker's line is the very line he read, but for who approved it: lines, fines, total, all of it.
    assert answer.workers == [replace(line, approval=said) for line in shown.workers]
    with shop_context(shop_a):
        assert worker_pay(shop_a, juma, NOVEMBER).worker == line_of(answer, "Juma")


def test_e10_payslip_194500_kept(shop_a: Shop, baba: StaffMember) -> None:
    # 02 §18, E10, spec §8.1's example, as November's 25 working days: 20 on time, 3 late, 2 half, 9,000 a day, a fine
    # of 500, an advance of 20,000.
    asha = paid(shop_a, "Asha", "9000")
    for day, taps in zip(WORKING, [FULL] * 20 + [LATE] * 3 + [HALF] * 2, strict=True):
        tapped(asha, *taps, date=day)
    give(asha, baba, dt.date(2026, 11, 10), "20000")
    approve(shop_a, baba)
    with shop_context(shop_a):
        assert Payslip.objects.get().total == Decimal("194500.00")
    assert lines_kept(asha) == [
        ("full", 23, "9000.00", None, "207000.00"),
        ("half", 2, "4500.00", None, "9000.00"),
        ("fines", 3, None, None, "-1500.00"),
        ("advance", None, None, dt.date(2026, 11, 10), "-20000.00"),
    ]
    assert line_of(month(shop_a), "Asha").total == Decimal("194500.00")


def test_every_kind_of_line_is_kept(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # A raise makes two lines; the meals; each advance a line of its own with its day, the crossed-out one not among
    # them, two of one day in the order they were typed.
    with shop_context(shop_a):
        set_pay_rate(asha, daily_rate=Decimal("12000"), effective_from=WED, by=None)
        record_meal_money(shop_a, money_id=uuid.uuid7(), date=MON, amount=Decimal("2000"), by=baba)
    for day, taps in ((MON, FULL), (TUE, HALF), (WED, FULL)):
        kept_day(asha, *taps, date=day)
    give(asha, baba, TUE, "3000")
    give(asha, baba, MON, "1000")
    give(asha, baba, TUE, "500")
    with shop_context(shop_a):
        void_advance(give(asha, baba, WED, "9000"), reason="Si yeye", by=baba)
    shown = line_of(month(shop_a), "Asha")
    approve(shop_a, baba)
    assert lines_kept(asha) == [
        ("full", 1, "10000.00", None, "10000.00"),
        ("full", 1, "12000.00", None, "12000.00"),
        ("half", 1, "5000.00", None, "5000.00"),
        ("meals", 1, None, None, "-2000.00"),
        ("advance", None, None, MON, "-1000.00"),
        ("advance", None, None, TUE, "-3000.00"),
        ("advance", None, None, TUE, "-500.00"),
    ]
    assert line_of(month(shop_a), "Asha").pay == shown.pay


def test_the_days_paid_are_marked(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # All thirty of Asha's, the absent ones and the Sundays too, as none of them may change now; none of Baba's, who is
    # on no payslip; and none of another month's.
    kept_day(asha, *FULL, date=MON)
    with shop_context(shop_a):
        work_out_days(shop_a, OCTOBER, dt.date(2026, 12, 1))
    approve(shop_a, baba)
    with shop_context(shop_a):
        slip = Payslip.objects.get()
        marked = set(AttendanceDay.objects.filter(payslip=slip).values_list("staff_id", "date"))
        assert marked == {(asha.pk, dt.date(2026, 11, day)) for day in range(1, 31)}
        assert AttendanceDay.objects.filter(staff=baba).exists()
        assert not AttendanceDay.objects.filter(payslip__isnull=False).exclude(staff=asha).exists()


def test_an_approved_month_says_the_same_whatever_comes(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Written past every service, as a bug or SQL typed by hand would: a rate, an advance, meal money, a late tap. The
    # month is read from its payslips alone.
    tap_day = kept_day(asha, *FULL, date=MON)
    approve(shop_a, baba)
    was = month(shop_a)
    with shop_context(shop_a):
        PayRate(shop=shop_a, staff=asha, daily_rate=Decimal("99000.00"), effective_from=NOVEMBER).save()
        Advance(shop=shop_a, staff=asha, date=MON, amount=Decimal("7000.00"), created_by=baba).save()
        MealMoney(shop=shop_a, date=MON, amount=Decimal("5000.00"), created_by=baba).save()
        AttendanceEvent.objects.filter(staff=asha).update(
            voided_at=timezone.now(), voided_by=baba, void_reason="Kwa makosa"
        )
    tapped(asha, *FULL, date=TUE)
    assert month(shop_a) == was
    with shop_context(shop_a):
        work_out_days(shop_a, NOVEMBER, dt.date(2026, 11, 30))
        assert AttendanceDay.objects.get(pk=tap_day.pk).status == "on_time"


def test_an_approved_month_is_read_in_a_few_queries_and_writes_nothing(
    shop_a: Shop, baba: StaffMember, asha: StaffMember
) -> None:
    # The run and who gave it, the payslips with their workers, their lines; whatever the number of workers. The book
    # isn't asked, so nothing is locked or written.
    for name in ("Baraka", "Juma", "Zawadi"):
        paid(shop_a, name)
    for staff_name in ("Asha", "Juma"):
        with shop_context(shop_a):
            staff = StaffMember.objects.get(display_name=staff_name)
        kept_day(staff, *FULL, date=MON)
    approve(shop_a, baba)
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        answer = pay_month(shop_a, NOVEMBER)
    assert len(answer.workers) == 4
    assert len(queries) <= 3
    assert all(query["sql"].startswith("SELECT") and "FOR NO KEY UPDATE" not in query["sql"] for query in queries)


def test_a_month_is_approved_in_a_few_queries(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One statement for the payslips and one for their lines; a mark for each worker, and nothing else that grows with
    # them: so December, with three workers more, costs three queries more at most.
    def queries_of(of: dt.date) -> int:
        shown = totals(month(shop_a, of))
        with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
            approve_month(shop_a, of, run_id=uuid.uuid7(), seen=shown, by=baba)
        return len(queries)

    kept_day(asha, *FULL, date=MON)
    november = queries_of(NOVEMBER)
    with shop_context(shop_a):
        # Each of her thirty days is one line of the edit history: the mark.
        assert EditEvent.objects.filter(subject_type="attendance_day").count() == 30
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2027, 1, 4, 9, 0)))
    for name in ("Baraka", "Juma", "Zawadi"):
        kept_day(paid(shop_a, name, since=DECEMBER), *FULL, date=dt.date(2026, 12, 1))
    assert queries_of(DECEMBER) <= november + 3


# What refuses it.


def test_a_month_not_over_is_refused(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # At 23:59 on 30 November the last day still runs, though UTC is still in the evening; at 01:30 on 1 December, by
    # the shop's own clock, the month is over, though UTC says 30 November.
    kept_day(asha, *FULL, date=MON)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 30, 23, 59)))
    assert refused(shop_a, baba).code == "pay_run.month_not_over"
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 1, 1, 30)))
    approve(shop_a, baba)


def test_a_month_to_come_is_refused(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    for to_come in (JANUARY, dt.date(9999, 12, 1)):
        assert refused(shop_a, baba, to_come, seen={}).code == "pay_run.month_not_over"


def test_a_month_approved_is_refused_again(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    kept_day(asha, *FULL, date=MON)
    approve(shop_a, baba)
    assert refused(shop_a, baba).code == "pay_run.already_approved"


def test_a_month_with_nobody_to_pay_is_refused(shop_a: Shop, baba: StaffMember) -> None:
    # Baba alone, who has no rate: nothing to keep.
    assert month(shop_a).to_approve is None
    assert refused(shop_a, baba).code == "pay_run.nobody"


def test_a_day_that_waits_refuses_it_and_is_named(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Jack: A. Juma forgot Toka on the 18th, and Asha on the 17th: both are shown before the tap, oldest first, and the
    # refusal says how many and the first. Decided, they are paid.
    juma = paid(shop_a, "Juma")
    asha_waits = kept_day(asha, *NO_OUT, date=TUE)
    juma_waits = kept_day(juma, *NO_OUT, date=WED)
    stops = month(shop_a).to_approve
    assert stops is not None
    assert stops.waiting == [OpenDay(asha.pk, "Asha", TUE), OpenDay(juma.pk, "Juma", WED)]
    refusal = refused(shop_a, baba)
    assert (refusal.code, refusal.params) == (
        "pay_run.days_waiting",
        {"count": 2, "name": "Asha", "date": "2026-11-17"},
    )
    with shop_context(shop_a):
        for day in (asha_waits, juma_waits):
            decide_day(day, choice=DayChoice.ON_TIME, reason="Alisahau Toka", replaces=None, by=baba)
    approve(shop_a, baba)
    assert line_of(month(shop_a), "Juma").total == Decimal("10000.00")


def test_a_day_with_no_rate_refuses_it_and_is_named(shop_a: Shop, baba: StaffMember) -> None:
    # Juma came on the 16th and 18th, and his rate was typed from the 17th: what the 16th pays nobody has said. Typed
    # from the 16th, it is paid.
    juma = paid(shop_a, "Juma", since=TUE)
    for day in (MON, WED):
        kept_day(juma, *FULL, date=day)
    stops = month(shop_a).to_approve
    assert stops is not None
    assert (stops.waiting, stops.no_rate) == ([], [OpenDay(juma.pk, "Juma", MON)])
    refusal = refused(shop_a, baba)
    assert (refusal.code, refusal.params) == (
        "pay_run.days_without_rate",
        {"count": 1, "name": "Juma", "date": "2026-11-16"},
    )
    with shop_context(shop_a):
        set_pay_rate(juma, daily_rate=Decimal("10000"), effective_from=MON, by=baba)
    approve(shop_a, baba)
    assert line_of(month(shop_a), "Juma").total == Decimal("20000.00")


def test_one_who_left_with_a_day_and_no_rate_can_be_mended(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Juma came on the 16th and the 17th, his rate was typed from the 17th, and he was marked as gone on the 18th. Baba
    # may still type the 16th's: nothing else could, so November, and every month after it, would wait for ever.
    juma = paid(shop_a, "Juma", since=TUE)
    for day in (MON, TUE):
        kept_day(juma, *FULL, date=day)
    with shop_context(shop_a):
        mark_left(juma, left_on=WED, by=baba, reason="Amehamia Moshi")
    assert refused(shop_a, baba).code == "pay_run.days_without_rate"
    with shop_context(shop_a):
        set_pay_rate(juma, daily_rate=Decimal("10000"), effective_from=MON, by=baba)
    approve(shop_a, baba)
    assert line_of(month(shop_a), "Juma").total == Decimal("20000.00")


def test_an_earlier_month_still_open_refuses_it(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On 1 January, November was never approved: December waits for it, or a debt of November would be lost. Approved in
    # order, both are.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2027, 1, 1, 9, 0)))
    kept_day(asha, *FULL, date=MON)
    stops = month(shop_a, DECEMBER).to_approve
    assert stops is not None
    assert stops.earlier == NOVEMBER
    refusal = refused(shop_a, baba, DECEMBER)
    assert (refusal.code, refusal.params) == ("pay_run.earlier_month_open", {"month": "2026-11"})
    approve(shop_a, baba, NOVEMBER)
    approve(shop_a, baba, DECEMBER)


def test_money_given_before_attendance_was_on_is_an_earlier_month(
    shop_a: Shop, baba: StaffMember, asha: StaffMember
) -> None:
    # 20,000 given in October, before anyone clocked in: October holds a debt of Asha's, so it is approved first, and
    # November takes it.
    kept_day(asha, *FULL, date=MON)
    kept_day(asha, *FULL, date=TUE)
    give(asha, baba, dt.date(2026, 10, 20), "5000")
    assert refused(shop_a, baba).params == {"month": "2026-10"}
    approve(shop_a, baba, OCTOBER)
    assert line_of(month(shop_a), "Asha").pay.carried == Decimal("5000.00")
    approve(shop_a, baba)
    assert line_of(month(shop_a), "Asha").total == Decimal("15000.00")


def test_a_rate_long_before_attendance_opens_no_month(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Juma's rate is typed from his first day, in January, and attendance was said to be off in May: no month before
    # November, when it was switched on, could hold any pay, so none is read. A job of 2019 would be read month by month
    # for seven years each time the page asks, for nothing.
    juma = paid(shop_a, "Juma", since=JAN_1)
    rule(shop_a, ATTENDANCE_ON, False, dt.date(2026, 5, 1))
    for staff in (asha, juma):
        kept_day(staff, *FULL, date=MON)
    read: list[dt.date] = []
    real = pay_services.read_parts

    def noted(shop: Shop, first: dt.date, last: dt.date, today: dt.date) -> Any:
        read.append(first)
        return real(shop, first, last, today)

    monkeypatch.setattr(pay_services, "read_parts", noted)
    stops = month(shop_a).to_approve
    assert stops is not None
    assert (stops.earlier, read) == (None, [NOVEMBER])
    approve(shop_a, baba)


def test_totals_that_moved_since_they_were_read_refuse_it(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Baba read 10,000 each; then Asha is given 3,000. He approves only what he read, so nothing is kept, and the page
    # shows him the new totals. Two changes that cancel out in the whole move two totals all the same.
    juma = paid(shop_a, "Juma")
    for staff in (asha, juma):
        kept_day(staff, *FULL, date=MON)
    shown = totals(month(shop_a))
    give(asha, baba, MON, "3000")
    assert refused(shop_a, baba, seen=shown).code == "pay_run.totals_moved"
    for wrong in (
        {asha.pk: Decimal("10000.00"), juma.pk: Decimal("7000.00")},
        {asha.pk: Decimal("7000.00")},
        {asha.pk: Decimal("7000.00"), juma.pk: Decimal("10000.00"), baba.pk: NOTHING},
        {},
    ):
        assert refused(shop_a, baba, seen=wrong).code == "pay_run.totals_moved"
    # 7,000 sent as "7000" is the same amount.
    approve(shop_a, baba, seen={asha.pk: Decimal("7000"), juma.pk: Decimal("10000")})


@pytest.mark.parametrize("missing", [Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE])
def test_without_each_key_nobody_approves(
    shop_a: Shop, asha: StaffMember, give_role: GiveRole, missing: Permission
) -> None:
    # The approval's own key and the two of pay, on the whole shop. A manager holds none of the three (02 §5).
    meneja = job(shop_a, "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    kept_day(asha, *FULL, date=MON)
    with shop_context(shop_a):
        for key in approval_services.APPROVES:
            if key != missing:
                grant_permission(meneja, key, side=None, by=None)
        with pytest.raises(PermissionDenied):
            approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=totals(pay_month(shop_a, NOVEMBER)), by=meneja)
        assert not PayRun.objects.exists()
        # With all three, he does, though he is no owner.
        grant_permission(meneja, missing, side=None, by=None)
    approve(shop_a, meneja)


def test_a_key_on_one_side_approves_nothing(shop_a: Shop, side_a: Side, asha: StaffMember) -> None:
    neema = job(shop_a, "Neema")
    kept_day(asha, *FULL, date=MON)
    with shop_context(shop_a):
        for key in approval_services.APPROVES:
            grant_permission(neema, key, side=side_a, by=None)
        with pytest.raises(PermissionDenied):
            approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=totals(pay_month(shop_a, NOVEMBER)), by=neema)


def test_whoever_approves_may_be_on_the_list(shop_a: Shop, baba: StaffMember) -> None:
    # Meneja holds the three keys and is paid by the day: he decides, fixes and rates nothing of his own, so his own
    # line is others' word, and he approves the whole.
    meneja = paid(shop_a, "Meneja")
    kept_day(meneja, *FULL, date=MON)
    with shop_context(shop_a):
        for key in approval_services.APPROVES:
            grant_permission(meneja, key, side=None, by=None)
    approve(shop_a, meneja)
    assert line_of(month(shop_a), "Meneja").approval == Approval("Meneja", timezone.now())


def test_another_shops_person_is_a_bug(shop_a: Shop, shop_b: Shop, baba: StaffMember, staff_b: StaffMember) -> None:
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen={}, by=staff_b)


def test_an_approved_month_is_asked_inside_its_own_shop(
    shop_a: Shop, shop_b: Shop, baba: StaffMember, asha: StaffMember
) -> None:
    # An approved month asks the book nothing, so it checks the shop itself: inside another's visit the guard would hide
    # every payslip, and the month would be empty without a word (ADR-0022). And a datetime is no business date.
    kept_day(asha, *FULL, date=MON)
    approve(shop_a, baba)
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        pay_month(shop_a, NOVEMBER)
    with shop_context(shop_a), pytest.raises(TypeError):
        pay_month(shop_a, dt.datetime(2026, 11, 1, tzinfo=dt.UTC))


def test_lines_that_do_not_add_up_keep_nothing(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A bug in our code, such as an advance read for the sum and not for the lines: a server error, and nothing kept.
    kept_day(asha, *FULL, date=MON)
    give(asha, baba, MON, "3000")
    monkeypatch.setattr(approval_services, "advances_by_job", lambda *_args: {})
    with pytest.raises(ValueError, match="add up"):
        approve(shop_a, baba)
    with shop_context(shop_a):
        assert not PayRun.objects.exists()
        assert not AttendanceDay.objects.filter(payslip__isnull=False).exists()


# A debt (Jack: A).


def test_a_debt_comes_off_the_next_month(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Asha earned 10,000 in November and was given 28,000: 0 to hand over, and 18,000 owed. December's draft takes it as
    # soon as November is approved, not before; her December pays it all, and January owes nothing.
    kept_day(asha, *FULL, date=MON)
    give(asha, baba, MON, "28000")
    assert (line_of(month(shop_a), "Asha").total, month(shop_a).total) == (Decimal("-18000.00"), NOTHING)
    december = [dt.date(2026, 12, day) for day in (2, 3, 4)]
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 8, 9, 0)))
    for day in december:
        kept_day(asha, *FULL, date=day)
    assert line_of(month(shop_a, DECEMBER), "Asha").pay.carried == NOTHING

    approve(shop_a, baba)

    assert lines_kept(asha)[-1] == ("advance", None, None, MON, "-28000.00")
    with shop_context(shop_a):
        assert Payslip.objects.get().total == Decimal("-18000.00")
    worker = line_of(month(shop_a, DECEMBER), "Asha")
    assert (worker.carried_from, worker.pay.carried, worker.total) == (
        NOVEMBER,
        Decimal("18000.00"),
        Decimal("12000.00"),
    )
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2027, 1, 4, 9, 0)))
    approve(shop_a, baba, DECEMBER)
    assert lines_kept(asha, DECEMBER) == [
        ("full", 3, "10000.00", None, "30000.00"),
        ("carried", None, None, NOVEMBER, "-18000.00"),
    ]
    kept = line_of(month(shop_a, DECEMBER), "Asha")
    assert (kept.carried_from, kept.pay.carried, kept.total) == (NOVEMBER, Decimal("18000.00"), Decimal("12000.00"))
    january = line_of(month(shop_a, JANUARY), "Asha")
    assert (january.carried_from, january.pay.carried) == (None, NOTHING)


def test_a_debt_bigger_than_the_next_month_goes_on(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 18,000 owed and one day of 10,000 in December: 8,000 goes on to January, from December, never 18,000 again.
    kept_day(asha, *FULL, date=MON)
    give(asha, baba, MON, "28000")
    approve(shop_a, baba)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2027, 1, 4, 9, 0)))
    kept_day(asha, *FULL, date=dt.date(2026, 12, 2))
    approve(shop_a, baba, DECEMBER)
    january = line_of(month(shop_a, JANUARY), "Asha")
    assert (january.carried_from, january.pay.carried) == (DECEMBER, Decimal("8000.00"))


def test_a_debt_is_taken_once_while_a_month_between_is_open(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On 4 January, December is over and not yet approved: it takes November's 18,000, and January's draft takes none of
    # it, or Asha would see it twice. Approved, December leaves nothing, and January's draft still takes none.
    kept_day(asha, *FULL, date=MON)
    give(asha, baba, MON, "28000")
    approve(shop_a, baba)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2027, 1, 4, 9, 0)))
    for day in (2, 3, 4):
        kept_day(asha, *FULL, date=dt.date(2026, 12, day))
    assert line_of(month(shop_a, DECEMBER), "Asha").pay.carried == Decimal("18000.00")
    assert line_of(month(shop_a, JANUARY), "Asha").pay.carried == NOTHING
    approve(shop_a, baba, DECEMBER)
    assert line_of(month(shop_a, JANUARY), "Asha").pay.carried == NOTHING


def test_a_debt_waits_for_a_month_they_are_paid_in(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Juma owes 18,000 from November, and leaves the shop's list for December, as he left on 30 November. Nobody lists
    # him for a debt alone: it stays on his last payslip. Asha's December owes nothing of his.
    juma = paid(shop_a, "Juma")
    for staff in (asha, juma):
        kept_day(staff, *FULL, date=MON)
    give(juma, baba, MON, "28000")
    with shop_context(shop_a):
        mark_left(juma, left_on=dt.date(2026, 11, 30), by=baba, reason="Amehama")
    approve(shop_a, baba)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 8, 9, 0)))
    december = month(shop_a, DECEMBER)
    assert [(line.display_name, line.pay.carried) for line in december.workers] == [("Asha", NOTHING)]


def test_no_debt_is_read_from_a_later_month(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # November was approved with a debt of 18,000. An advance of October then appears, past the service, which refuses
    # one: October's draft shows it alone. A debt goes forward, never back.
    kept_day(asha, *FULL, date=MON)
    give(asha, baba, MON, "28000")
    approve(shop_a, baba)
    with shop_context(shop_a):
        Advance(shop=shop_a, staff=asha, date=dt.date(2026, 10, 20), amount=Decimal("1000.00"), created_by=baba).save()
    october = line_of(month(shop_a, OCTOBER), "Asha")
    assert (october.pay.carried, october.total) == (NOTHING, Decimal("-1000.00"))
    assert line_of(month(shop_a), "Asha").pay.carried == NOTHING


# What it warns of, and stops nothing.


def test_a_laptop_that_has_sent_nothing_since_is_named(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, device_a: Device
) -> None:
    # Jack: A. The laptop last sent on 28 November, so taps of the 30th may still be inside: named before the tap, and
    # the month is approved all the same. One that sent at the very midnight the month ended is not named; nor one
    # blocked, nor one paired since, which can hold nothing of November.
    kept_day(asha, *FULL, date=MON)
    stops = month(shop_a).to_approve
    assert stops is not None
    assert stops.quiet_laptops == []
    midnight = dt.datetime(2026, 12, 1, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    long_ago = dt.datetime(2026, 11, 28, 18, 45, tzinfo=dt.timezone(dt.timedelta(hours=3)))

    def named() -> list[tuple[str, dt.datetime | None]]:
        stops = month(shop_a).to_approve
        assert stops is not None
        return [(laptop.name, laptop.last_synced_at) for laptop in stops.quiet_laptops]

    with shop_context(shop_a):
        laptop = Device.objects.filter(pk=device_a.pk)
        # Made in January, as a laptop that was there all November.
        laptop.update(created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC), last_synced_at=long_ago)
        assert named() == [(device_a.name, long_ago)]
        laptop.update(last_synced_at=None)
        assert named() == [(device_a.name, None)]
        laptop.update(last_synced_at=midnight)
        assert named() == []
        laptop.update(last_synced_at=long_ago, created_at=midnight)
        assert named() == []
        laptop.update(created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC), status=DeviceStatus.BLOCKED)
        assert named() == []
        laptop.update(status=DeviceStatus.ACTIVE)
        assert named() == [(device_a.name, long_ago)]
    approve(shop_a, baba)


def test_one_who_came_with_no_pay_is_named(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Zawadi came twice and Salim's day waits, and nobody typed a daily pay for either: they are on no payslip, and once
    # the month is closed no rate can be typed for it. Named, by name, and not Baba, who never came, nor Juma, absent.
    for name, taps in (("Zawadi", FULL), ("Salim", NO_OUT)):
        kept_day(job(shop_a, name), *taps, date=MON)
    job(shop_a, "Juma")
    kept_day(asha, *FULL, date=MON)
    stops = month(shop_a).to_approve
    assert stops is not None
    assert (stops.came_unpaid, stops.waiting) == (["Salim", "Zawadi"], [])
    approve(shop_a, baba)
    with shop_context(shop_a):
        assert set(Payslip.objects.values_list("staff_id", flat=True)) == {asha.pk}


def test_a_month_still_running_waits_for_nothing(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # December, on its 1st: nothing to approve yet, so nothing is asked, and the page offers no button.
    assert month(shop_a, DECEMBER).to_approve is None


# Two at once.


@pytest.mark.django_db(transaction=True)
def test_two_people_approving_at_once_make_one_run(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Baba and Meneja both tap Idhinisha. The second waits for the first, then finds the month approved.
    kept_day(asha, *FULL, date=MON)
    shown = totals(month(shop_a))

    def again() -> str:
        with shop_context(shop_a):
            try:
                approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=shown, by=baba)
            except ValidationError as refusal:
                return str(refusal.code)
        return "approved"

    with shop_context(shop_a), transaction.atomic():
        approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=shown, by=baba)
        thread, ended = in_another_transaction(again)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["pay_run.already_approved"]
    with shop_context(shop_a):
        assert (PayRun.objects.count(), Payslip.objects.count()) == (1, 1)
