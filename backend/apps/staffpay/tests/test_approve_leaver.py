"""apps/staffpay/tests/test_approve_leaver.py — one worker who left, approved alone (WAGE-3; 02 §12): approve_leaver
(apps/staffpay/services/approval.py), and what their page answers before and after it.

Today is Saturday 14 November 2026 at MPC, at 19:00. Neema has tapped Toka and is marked as gone:

    5 full days, 2 half, a share of the meals on each       60,000 less 7,000
    Leo, a full day, less her share of today's meals        10,000 less 1,000
    Baba approves her alone                                 a payslip of 62,000, today's day kept with the others

On 1 December the month's approval leaves her payslip as it is. Attendance is on from 1 November, and the rates start
with it. What a month's approval keeps is test_approve_month.py's, and what is refused once she is approved
test_approved_month.py's. The clock is fixed. The amounts are made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.permissions import Permission, RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, PermissionGrant, StaffMember
from apps.people.services import end_permission, grant_permission, hire_again, mark_left
from apps.shops.models import Closure, Shop, Side
from apps.staffpay.models import AttendanceDay, ClockKind, DayChoice, DayStatus, PayRun, Payslip, PayslipLine
from apps.staffpay.services import (
    Approval,
    OpenDay,
    PayMonth,
    ToApprove,
    WorkerPayMonth,
    approve_leaver,
    approve_month,
    decide_day,
    pay_month,
    record_advance,
    record_meal_money,
    set_pay_rate,
    work_out_days,
    worker_pay,
)
from apps.staffpay.services import approval as approval_services
from apps.staffpay.services import pay as pay_services
from apps.staffpay.tests.days import doubted_tap, job, kept_day, rule, tapped
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER, DECEMBER = dt.date(2026, 11, 1), dt.date(2026, 12, 1)
TODAY = dt.date(2026, 11, 14)
NOTHING = Decimal("0.00")
# The days Neema came before today: Monday 2 to Friday 6 whole, Saturday 7 and Monday 9 the morning.
WHOLE = [dt.date(2026, 11, day) for day in (2, 3, 4, 5, 6)]
MORNINGS = [dt.date(2026, 11, day) for day in (7, 9)]
FULL = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
HALF = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 13, 10))
NO_OUT = ((ClockKind.IN, 7, 20),)
ARUSHA = dt.timezone(dt.timedelta(hours=3))


def at(moment: dt.datetime) -> Callable[[], dt.datetime]:
    """A clock stopped at one moment of Arusha's, for timezone.now."""
    return lambda: moment.replace(tzinfo=ARUSHA)


@pytest.fixture(autouse=True)
def saturday_evening(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device) -> None:
    # 19:00 on Saturday 14 November in Arusha, for every read of the clock. Attendance is on from 1 November, and the
    # shop's laptop, where every tap below is made (days.py), sent something this evening.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 14, 19, 0)))
    rule(shop_a, ATTENDANCE_ON, True, NOVEMBER)
    with shop_context(shop_a):
        Device.objects.update(last_synced_at=timezone.now(), created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def paid(shop: Shop, name: str, *, since: dt.date = NOVEMBER) -> StaffMember:
    """A worker since January, paid a made-up 10,000 a day from a day on (WAGE-1)."""
    staff = job(shop, name)
    with shop_context(shop):
        set_pay_rate(staff, daily_rate=Decimal("10000"), effective_from=since, by=None)
    return staff


@pytest.fixture
def neema(shop_a: Shop) -> StaffMember:
    return paid(shop_a, "Neema")


def typed(by: StaffMember, day: dt.date, amount: str) -> None:
    with shop_context(by.shop_id):
        shop = Shop.objects.get(pk=by.shop_id)
        record_meal_money(shop, money_id=uuid.uuid7(), date=day, amount=Decimal(amount), by=by)


def leaves(staff: StaffMember, by: StaffMember, on: dt.date = TODAY) -> StaffMember:
    with shop_context(staff.shop_id):
        return mark_left(staff, left_on=on, by=by, reason="Amehama")


def page(staff: StaffMember, of: dt.date = NOVEMBER) -> WorkerPayMonth:
    with shop_context(staff.shop_id):
        return worker_pay(Shop.objects.get(pk=staff.shop_id), StaffMember.objects.get(pk=staff.pk), of)


def waits_for(staff: StaffMember, of: dt.date = NOVEMBER) -> ToApprove:
    stops = page(staff, of).to_approve
    assert stops is not None
    return stops


def approve(staff: StaffMember, by: StaffMember, of: dt.date = NOVEMBER, *, seen: str | None = None) -> Payslip:
    """The worker's pay read, then approved alone as it was read."""
    with shop_context(staff.shop_id):
        total = page(staff, of).worker.total if seen is None else Decimal(seen)
        return approve_leaver(staff, of, payslip_id=uuid.uuid7(), seen=total, by=by)


def refused(staff: StaffMember, by: StaffMember, of: dt.date = NOVEMBER, **kwargs: Any) -> ValidationError:
    """The refusal of an approval, which keeps nothing."""
    with shop_context(staff.shop_id):
        before = (
            Payslip.objects.count(),
            PayslipLine.objects.count(),
            AttendanceDay.objects.filter(payslip__isnull=False).count(),
        )
    with pytest.raises(ValidationError) as refusal:
        approve(staff, by, of, **kwargs)
    with shop_context(staff.shop_id):
        assert (
            Payslip.objects.count(),
            PayslipLine.objects.count(),
            AttendanceDay.objects.filter(payslip__isnull=False).count(),
        ) == before
    return refusal.value


def month(shop: Shop, of: dt.date = NOVEMBER) -> PayMonth:
    with shop_context(shop):
        return pay_month(shop, of)


def lines_kept(staff: StaffMember, of: dt.date = NOVEMBER) -> list[tuple[str, int | None, str]]:
    with shop_context(staff.shop_id):
        return [
            (line.kind, line.days, str(line.amount))
            for line in PayslipLine.objects.filter(payslip__staff=staff, payslip__month=of).order_by("position")
        ]


@pytest.fixture
def worked(shop_a: Shop, baba: StaffMember, neema: StaffMember) -> StaffMember:
    # Neema's days before today, and today, as at the top of this file: 1,000 of meals on each day she came.
    for day in WHOLE:
        kept_day(neema, *FULL, date=day)
    for day in MORNINGS:
        kept_day(neema, *HALF, date=day)
    tapped(neema, *FULL, date=TODAY)
    for day in (*WHOLE, *MORNINGS, TODAY):
        typed(baba, day, "1000")
    return neema


def test_neema_is_approved_alone_the_evening_she_leaves(shop_a: Shop, baba: StaffMember, worked: StaffMember) -> None:
    leaves(worked, baba)
    shown = page(worked)
    assert (shown.worker.total, shown.worker.approval) == (Decimal("62000.00"), None)
    assert shown.to_approve == ToApprove(None, [], [], [], [], still_clocked_in=False)

    slip = approve(worked, baba)

    assert (slip.staff_id, slip.month, slip.pay_run_id, slip.total) == (worked.pk, NOVEMBER, None, Decimal("62000.00"))
    assert slip.created_by_id == baba.pk
    # Leo is a line of the page alone: on the payslip it is one of her days, and its meals among the others.
    assert lines_kept(worked) == [("full", 6, "60000.00"), ("half", 2, "10000.00"), ("meals", 8, "-8000.00")]
    # Her days up to today, marked, the absent ones and the Sunday too; today's kept now, with its share.
    with shop_context(shop_a):
        marked = AttendanceDay.objects.filter(payslip=slip).order_by("date")
        assert [day.date for day in marked] == [dt.date(2026, 11, day) for day in range(1, 15)]
        today = marked.last()
        assert today is not None
        assert (today.status, today.meal_share, today.first_out) == (
            DayStatus.ON_TIME,
            Decimal("1000.00"),
            dt.time(18, 45),
        )
        assert not PayRun.objects.exists()
    # Her page and Mishahara say it is approved, by whom and when, and the month still runs for the others.
    answer = page(worked)
    assert answer.worker.approval == Approval("Baba", timezone.now())
    assert (answer.worker.total, answer.worker.today, answer.to_approve) == (Decimal("62000.00"), None, None)
    whole = month(shop_a)
    assert (whole.approval, whole.workers, whole.total) == (None, [answer.worker], Decimal("62000.00"))


def test_the_months_approval_leaves_it_as_it_is(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1 December: Juma's payslip is the run's; Neema's stays her own, with no run, as she was approved on the 14th.
    juma = paid(shop_a, "Juma")
    kept_day(juma, *FULL, date=dt.date(2026, 11, 10))
    leaves(worked, baba)
    alone = approve(worked, baba)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 1, 9, 0)))
    shown = month(shop_a)
    assert [(line.display_name, line.total) for line in shown.workers] == [
        ("Juma", Decimal("10000.00")),
        ("Neema", Decimal("62000.00")),
    ]
    with shop_context(shop_a):
        run = approve_month(
            shop_a,
            NOVEMBER,
            run_id=uuid.uuid7(),
            seen={line.staff_id: line.total for line in shown.workers},
            by=baba,
        )
        assert {slip.staff_id: slip.pay_run_id for slip in Payslip.objects.all()} == {juma.pk: run.pk, worked.pk: None}
        assert Payslip.objects.get(pk=alone.pk).created_at == alone.created_at
    approved = month(shop_a)
    assert [(line.display_name, line.total) for line in approved.workers] == [
        ("Juma", Decimal("10000.00")),
        ("Neema", Decimal("62000.00")),
    ]
    neema = next(line for line in approved.workers if line.display_name == "Neema")
    assert neema.approval == Approval("Baba", alone.created_at)


def test_her_last_day_is_the_books_tomorrow_as_it_was_paid(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Tonight two have tapped, Asha and Neema: 4,000 of meals is 2,000 each, and Neema is paid less hers. Salim's taps
    # come late: three ate. Tomorrow the book splits it again, 1,333 for the two still to pay; Neema's stays 2,000.
    asha, salim = paid(shop_a, "Asha"), paid(shop_a, "Salim")
    tapped(asha, *FULL, date=TODAY)
    typed(baba, TODAY, "3000")
    leaves(worked, baba)
    approve(worked, baba)
    tapped(salim, *FULL, date=TODAY)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 16, 9, 0)))
    with shop_context(shop_a):
        days = {day.staff_id: day.meal_share for day in work_out_days(shop_a, TODAY, TODAY)}
    assert (days[worked.pk], days[asha.pk], days[salim.pk]) == (
        Decimal("2000.00"),
        Decimal("1333.00"),
        Decimal("1333.00"),
    )


# What refuses it.


@pytest.mark.parametrize("taps", [NO_OUT, ((ClockKind.IN, 9, 0),)])
def test_still_clocked_in_waits_for_toka(
    shop_a: Shop, baba: StaffMember, neema: StaffMember, taps: tuple[tuple[ClockKind, int, int], ...]
) -> None:
    # Marked as gone at 18:30, before her Toka: approved now, today would be left out of her pay for good, whenever she
    # came. Once she taps Toka, or a manager adds it, she is.
    kept_day(neema, *FULL, date=WHOLE[0])
    tapped(neema, *taps, date=TODAY)
    leaves(neema, baba)
    stops = waits_for(neema)
    assert (stops.still_clocked_in, stops.waiting) == (True, [])
    assert refused(neema, baba).code == "payslip.still_clocked_in"


def test_a_last_day_the_rule_cannot_judge_waits_for_tomorrow(
    shop_a: Shop, baba: StaffMember, neema: StaffMember
) -> None:
    # Out at 16:00: a manager decides it, which can be done once the day is over. Named with today's date.
    tapped(neema, (ClockKind.IN, 7, 20), (ClockKind.OUT, 16, 0), date=TODAY)
    leaves(neema, baba)
    stops = waits_for(neema)
    assert (stops.still_clocked_in, stops.waiting) == (False, [OpenDay(neema.pk, "Neema", TODAY)])
    refusal = refused(neema, baba)
    assert (refusal.code, refusal.params) == (
        "pay_run.days_waiting",
        {"count": 1, "name": "Neema", "date": "2026-11-14"},
    )


def test_a_last_day_whose_time_is_in_doubt_waits(shop_a: Shop, baba: StaffMember, neema: StaffMember) -> None:
    # Her Toka's time isn't trusted, so no Toka of today can be read, now or ever: it waits for a decision, and isn't
    # said to be a missing Toka.
    tapped(neema, (ClockKind.IN, 7, 20), date=TODAY)
    doubted_tap(neema, 18, 45, date=TODAY, kind=ClockKind.OUT)
    leaves(neema, baba)
    stops = waits_for(neema)
    assert (stops.still_clocked_in, stops.waiting) == (False, [OpenDay(neema.pk, "Neema", TODAY)])


def test_a_last_day_with_no_rate_is_named(shop_a: Shop, baba: StaffMember, neema: StaffMember) -> None:
    # Juma, whose rate was typed from tomorrow: what today pays, nobody said.
    juma = paid(shop_a, "Juma", since=TODAY + dt.timedelta(days=1))
    tapped(juma, *FULL, date=TODAY)
    with shop_context(shop_a):
        record_advance(juma, advance_id=uuid.uuid7(), date=TODAY, amount=Decimal("1000"), by=baba)
    leaves(juma, baba)
    assert waits_for(juma).no_rate == [OpenDay(juma.pk, "Juma", TODAY)]
    assert refused(juma, baba).code == "pay_run.days_without_rate"
    # Baba types it, though Juma has left (WAGE-3's review), and he is approved: his day, less what he was given.
    with shop_context(shop_a):
        set_pay_rate(juma, daily_rate=Decimal("10000"), effective_from=TODAY, by=baba)
    assert approve(juma, baba).total == Decimal("9000.00")


def test_one_who_did_not_come_on_the_last_day_is_approved(shop_a: Shop, baba: StaffMember, neema: StaffMember) -> None:
    # She said goodbye by phone: no tap today, so no Leo; today is kept as absent, and no later tap can make it paid.
    kept_day(neema, *FULL, date=WHOLE[0])
    leaves(neema, baba)
    assert waits_for(neema).still_clocked_in is False
    slip = approve(neema, baba)
    assert slip.total == Decimal("10000.00")
    with shop_context(shop_a):
        assert AttendanceDay.objects.get(staff=neema, date=TODAY).status == DayStatus.ABSENT


def test_a_last_day_that_is_off_is_approved(
    shop_a: Shop, baba: StaffMember, neema: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A closed Saturday: nobody works, and there is nothing to wait for.
    kept_day(neema, *FULL, date=WHOLE[0])
    with shop_context(shop_a):
        Closure(shop=shop_a, first_day=TODAY, last_day=TODAY, name="Msiba").save()
    leaves(neema, baba)
    approve(neema, baba)
    with shop_context(shop_a):
        assert AttendanceDay.objects.get(staff=neema, date=TODAY).status == DayStatus.OFF


def test_midnight_passing_as_it_is_read_keeps_nothing(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 23:59: what Baba read holds today as Leo. Midnight passes as her days are asked for, and the book keeps today as a
    # day gone by: kept a second time, it would be an error of the database's. He reads it again, and it is the same.
    leaves(worked, baba)
    shown = page(worked).worker.total
    real = pay_services.read_parts

    def past_midnight(shop: Shop, first: dt.date, last: dt.date, today: dt.date) -> Any:
        monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 15, 0, 0)))
        return real(shop, first, last, today)

    monkeypatch.setattr(approval_services, "read_parts", past_midnight)
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refusal:
            approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=shown, by=baba)
        assert refusal.value.code == "pay_run.totals_moved"
        assert not Payslip.objects.exists()
    monkeypatch.setattr(approval_services, "read_parts", real)
    assert approve(worked, baba).total == shown == Decimal("62000.00")


def test_one_marked_as_gone_days_later(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On Friday 20 Baba remembers that Neema left on the 14th: her days stop there, and today's isn't hers.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 20, 12, 0)))
    leaves(worked, baba)
    assert approve(worked, baba).total == Decimal("62000.00")
    with shop_context(shop_a):
        days = AttendanceDay.objects.filter(staff=worked, payslip__isnull=False).values_list("date", flat=True)
        assert max(days) == TODAY


def test_one_who_still_works_waits_for_the_month(shop_a: Shop, baba: StaffMember, worked: StaffMember) -> None:
    assert page(worked).to_approve is None
    assert refused(worked, baba).code == "payslip.not_left"


def test_nobody_approves_their_own_alone(shop_a: Shop, baba: StaffMember, worked: StaffMember) -> None:
    # Neema left and was hired again as a manager with the three keys: her old job's pay is closed by somebody else.
    leaves(worked, baba)
    with shop_context(shop_a):
        again = hire_again(worked, display_name="Neema", started_on=TODAY, by=None)
        for key in approval_services.APPROVES:
            grant_permission(again, key, side=None, by=None)
    assert refused(worked, again).code == "payslip.own"


def test_one_approved_is_refused_again(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaves(worked, baba)
    approve(worked, baba)
    assert refused(worked, baba).code == "payslip.already_approved"
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 1, 9, 0)))
    with shop_context(shop_a):
        approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen={worked.pk: Decimal("62000")}, by=baba)
    assert refused(worked, baba).code == "pay_run.already_approved"


def test_a_month_with_nothing_of_theirs_is_refused(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # October, before she was paid by the day; December, after she left; and a month still to come.
    leaves(worked, baba)
    for other in (dt.date(2026, 10, 1), DECEMBER, dt.date(9999, 12, 1)):
        assert page(worked, other).to_approve is None
        assert refused(worked, baba, other, seen="0").code == "payslip.nothing"
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 8, 9, 0)))
    assert refused(worked, baba, DECEMBER, seen="0").code == "payslip.nothing"


def test_a_total_that_moved_is_refused(shop_a: Shop, baba: StaffMember, worked: StaffMember) -> None:
    leaves(worked, baba)
    with shop_context(shop_a):
        record_advance(worked, advance_id=uuid.uuid7(), date=TODAY, amount=Decimal("2000"), by=baba)
    assert refused(worked, baba, seen="62000").code == "pay_run.totals_moved"
    assert approve(worked, baba, seen="60000").total == Decimal("60000.00")


def test_a_day_of_theirs_that_waits_refuses_it_and_anothers_does_not(
    shop_a: Shop, baba: StaffMember, worked: StaffMember
) -> None:
    # Juma's day waits, which is no reason to keep Neema from her pay; hers does, oldest first.
    juma = paid(shop_a, "Juma")
    kept_day(juma, *NO_OUT, date=dt.date(2026, 11, 3))
    hers = kept_day(worked, *NO_OUT, date=dt.date(2026, 11, 11))
    leaves(worked, baba)
    assert waits_for(worked).waiting == [OpenDay(worked.pk, "Neema", dt.date(2026, 11, 11))]
    assert refused(worked, baba).code == "pay_run.days_waiting"
    with shop_context(shop_a):
        decide_day(hers, choice=DayChoice.HALF, reason="Alisahau Toka", replaces=None, by=baba)
    assert approve(worked, baba).total == Decimal("67000.00")


def test_an_earlier_month_of_theirs_refuses_it(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # She leaves on 2 December, and November isn't approved yet, as Juma's day of it waits: hers of November is approved
    # alone first, then December's, so a debt of November would come off it.
    juma = paid(shop_a, "Juma")
    kept_day(juma, *NO_OUT, date=dt.date(2026, 11, 3))
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 2, 19, 0)))
    tapped(worked, *FULL, date=dt.date(2026, 12, 2))
    leaves(worked, baba, dt.date(2026, 12, 2))
    assert (waits_for(worked, NOVEMBER).earlier, waits_for(worked, DECEMBER).earlier) == (None, NOVEMBER)
    refusal = refused(worked, baba, DECEMBER)
    assert (refusal.code, refusal.params) == ("pay_run.earlier_month_open", {"month": "2026-11"})
    approve(worked, baba, NOVEMBER)
    assert approve(worked, baba, DECEMBER).total == Decimal("10000.00")


def test_one_who_owes_is_approved_at_below_0(shop_a: Shop, baba: StaffMember, worked: StaffMember) -> None:
    # 80,000 given before payday: nothing to hand over, and what she owes stays on her last payslip (Jack: A).
    with shop_context(shop_a):
        record_advance(worked, advance_id=uuid.uuid7(), date=TODAY, amount=Decimal("80000"), by=baba)
    leaves(worked, baba)
    assert approve(worked, baba).total == Decimal("-18000.00")
    assert lines_kept(worked)[-1] == ("advance", None, "-80000.00")
    assert month(shop_a).total == NOTHING


def test_each_job_of_one_hired_again_has_its_own(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Neema left on the 14th, was approved, and is hired again on the 16th: her new job starts clean, on its own line.
    leaves(worked, baba)
    approve(worked, baba)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 17, 9, 0)))
    with shop_context(shop_a):
        again = hire_again(worked, display_name="Neema", started_on=dt.date(2026, 11, 16), by=None)
        set_pay_rate(again, daily_rate=Decimal("10000"), effective_from=dt.date(2026, 11, 16), by=None)
    kept_day(again, *FULL, date=dt.date(2026, 11, 16))
    assert [(line.staff_id, line.total, line.approval is None) for line in month(shop_a).workers] == [
        (worked.pk, Decimal("62000.00"), False),
        (again.pk, Decimal("10000.00"), True),
    ]


def test_a_laptop_that_has_sent_nothing_since_the_day_they_left_is_named(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, device_a: Device, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Tonight: one that has sent nothing today. On Friday 20: one that has sent nothing since the 14th ended, so one
    # that sent on the 15th holds nothing of hers.
    def sent(moment: dt.datetime) -> list[str]:
        with shop_context(shop_a):
            Device.objects.filter(pk=device_a.pk).update(last_synced_at=moment.replace(tzinfo=ARUSHA))
        return [laptop.name for laptop in waits_for(worked).quiet_laptops]

    leaves(worked, baba)
    assert sent(dt.datetime(2026, 11, 13, 23, 59)) == [device_a.name]
    assert sent(dt.datetime(2026, 11, 14, 0, 0)) == []
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 11, 20, 12, 0)))
    assert sent(dt.datetime(2026, 11, 14, 23, 59)) == [device_a.name]
    assert sent(dt.datetime(2026, 11, 15, 0, 0)) == []
    # It stops nothing.
    approve(worked, baba)


def test_a_month_gone_by_asks_of_laptops_since_it_ended(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, device_a: Device, monkeypatch: pytest.MonkeyPatch
) -> None:
    # She leaves on 2 December, and November is approved alone first: a laptop that sent on 1 December holds nothing of
    # November, though her job ran on into December.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 2, 19, 0)))
    leaves(worked, baba, dt.date(2026, 12, 2))
    named = {}
    for moment in (dt.datetime(2026, 11, 30, 23, 59), dt.datetime(2026, 12, 1, 0, 0)):
        with shop_context(shop_a):
            Device.objects.filter(pk=device_a.pk).update(last_synced_at=moment.replace(tzinfo=ARUSHA))
        named[moment.day] = [laptop.name for laptop in waits_for(worked, NOVEMBER).quiet_laptops]
    assert named == {30: [device_a.name], 1: []}


def test_a_payslip_there_is_is_always_listed(shop_a: Shop, baba: StaffMember, neema: StaffMember) -> None:
    # Whatever the book answers of its days: Zawadi's payslip of November, written past the service, and no day or rate
    # of hers. A page that left it out would hide money that was approved.
    zawadi = job(shop_a, "Zawadi")
    with shop_context(shop_a):
        Payslip(shop=shop_a, staff=zawadi, month=NOVEMBER, total=Decimal("5000.00"), created_by=baba).save()
    listed = {line.display_name: line.total for line in month(shop_a).workers}
    assert listed["Zawadi"] == Decimal("5000.00")


@pytest.mark.parametrize("missing", approval_services.APPROVES)
def test_without_each_key_nobody_approves_one_alone(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, give_role: GiveRole, missing: str
) -> None:
    meneja = job(shop_a, "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    leaves(worked, baba)
    with shop_context(shop_a):
        for key in approval_services.APPROVES:
            if key != missing:
                grant_permission(meneja, key, side=None, by=None)
        with pytest.raises(PermissionDenied):
            approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=Decimal("62000"), by=meneja)
        assert not Payslip.objects.exists()


# Two at once.


@pytest.mark.django_db(transaction=True)
def test_a_key_taken_away_meanwhile_approves_nobody(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, give_role: GiveRole
) -> None:
    # As for a month: Baba takes the key from Meneja while Meneja taps Idhinisha.
    meneja = job(shop_a, "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    leaves(worked, baba)
    with shop_context(shop_a):
        for key in approval_services.APPROVES:
            grant_permission(meneja, key, side=None, by=None)
        [mine] = PermissionGrant.objects.filter(staff=meneja, permission=Permission.PAY_APPROVE)

    def approves() -> str:
        with shop_context(shop_a):
            try:
                approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=Decimal("62000"), by=meneja)
            except PermissionDenied:
                return "refused"
        return "approved"

    with shop_context(shop_a), transaction.atomic():
        end_permission(mine, reason="Baba ataidhinisha mwenyewe", by=baba)
        thread, ended = in_another_transaction(approves)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["refused"]
    with shop_context(shop_a):
        assert not Payslip.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_people_approving_one_at_once_make_one_payslip(
    shop_a: Shop, baba: StaffMember, worked: StaffMember
) -> None:
    leaves(worked, baba)

    def again() -> str:
        with shop_context(shop_a):
            try:
                approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=Decimal("62000"), by=baba)
            except ValidationError as refusal:
                return str(refusal.code)
        return "approved"

    with shop_context(shop_a), transaction.atomic():
        approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=Decimal("62000"), by=baba)
        thread, ended = in_another_transaction(again)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["payslip.already_approved"]
    with shop_context(shop_a):
        assert Payslip.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_a_leaver_beside_the_months_approval_waits_and_is_refused(
    shop_a: Shop, baba: StaffMember, worked: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On 1 December, November is approved for everyone as Neema is approved alone: one payslip of hers, the month's.
    leaves(worked, baba)
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 1, 19, 0)))
    shown = {line.staff_id: line.total for line in month(shop_a).workers}

    def alone() -> str:
        with shop_context(shop_a):
            try:
                approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=shown[worked.pk], by=baba)
            except ValidationError as refusal:
                return str(refusal.code)
        return "approved"

    with shop_context(shop_a), transaction.atomic():
        run = approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=shown, by=baba)
        thread, ended = in_another_transaction(alone)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["pay_run.already_approved"]
    with shop_context(shop_a):
        assert list(Payslip.objects.values_list("staff", "pay_run")) == [(worked.pk, run.pk)]


@pytest.mark.django_db(transaction=True)
def test_money_given_beside_it_waits_and_is_refused(shop_a: Shop, baba: StaffMember, worked: StaffMember) -> None:
    # Baba types an advance of hers at the counter as her pay is being approved: it waits, and finds her month closed.
    leaves(worked, baba)

    def gives() -> str:
        with shop_context(shop_a):
            try:
                record_advance(worked, advance_id=uuid.uuid7(), date=TODAY, amount=Decimal("5000"), by=baba)
            except ValidationError as refusal:
                return ",".join(error.code or "" for errors in refusal.error_dict.values() for error in errors)
        return "given"

    with shop_context(shop_a), transaction.atomic():
        approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=Decimal("62000"), by=baba)
        thread, ended = in_another_transaction(gives)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["pay.day_approved"]


def test_another_shops_person_is_a_bug(
    shop_a: Shop, worked: StaffMember, baba: StaffMember, staff_b: StaffMember
) -> None:
    leaves(worked, baba)
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        approve_leaver(worked, NOVEMBER, payslip_id=uuid.uuid7(), seen=Decimal("62000"), by=staff_b)


def test_the_payslips_id_is_the_clients(shop_a: Shop, baba: StaffMember, worked: StaffMember) -> None:
    # So a request sent twice, its first answer lost, is the same payslip (ADR-0007).
    leaves(worked, baba)
    made = uuid.uuid7()
    with shop_context(shop_a):
        assert approve_leaver(worked, NOVEMBER, payslip_id=made, seen=Decimal("62000"), by=baba).pk == made
