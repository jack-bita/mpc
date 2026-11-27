"""apps/staffpay/tests/test_approved_month.py — what an approved month's pay was made of takes no change (WAGE-3; A3):
each of the eight services that write it refuses (is_closed, apps/staffpay/selectors.py), under the lock the approval
takes.

    November approved on 1 December:
        a day decided, a tap added or crossed out, a pay rate, meal money typed or crossed out, an advance typed or
        crossed out, of any day up to 30 November        refused, pay.day_approved
        the same of 1 December                           taken
    Neema approved alone on 14 November:                 her days, rates and advances refused; the others' taken, and
                                                         the shop's meal money too

A mistake found later is an adjustment in a later month (WAGE-9). The clock is fixed. The amounts are made up (rule 10).
Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import mark_left
from apps.shops.models import Shop, Side
from apps.staffpay.models import (
    Advance,
    AttendanceDay,
    AttendanceEvent,
    ClockKind,
    DayChoice,
    MealMoney,
    PayCorrection,
    PayRate,
    PayRun,
    Payslip,
)
from apps.staffpay.selectors import is_closed
from apps.staffpay.services import (
    add_tap,
    approve_leaver,
    approve_month,
    attendance_month,
    decide_day,
    pay_month,
    record_advance,
    record_correction,
    record_meal_money,
    set_pay_rate,
    void_advance,
    void_correction,
    void_meal_money,
    void_tap,
    work_out_days,
    worker_attendance,
)
from apps.staffpay.tests.days import job, kept_day, rule, tapped
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER, DECEMBER = dt.date(2026, 11, 1), dt.date(2026, 12, 1)
MON, TUE, LAST = dt.date(2026, 11, 16), dt.date(2026, 11, 17), dt.date(2026, 11, 30)
FULL = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))


def at(moment: dt.datetime) -> Callable[[], dt.datetime]:
    """A clock stopped at one moment of Arusha's, for timezone.now."""
    return lambda: moment.replace(tzinfo=dt.timezone(dt.timedelta(hours=3)))


@pytest.fixture(autouse=True)
def second_of_december(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device) -> None:
    # 19:05 on Wednesday 2 December in Arusha, so 1 December is a day gone by too. Attendance is on from 1 November.
    monkeypatch.setattr(timezone, "now", at(dt.datetime(2026, 12, 2, 19, 5)))
    rule(shop_a, ATTENDANCE_ON, True, NOVEMBER)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, and paid by no day.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def paid(shop: Shop, name: str) -> StaffMember:
    staff = job(shop, name)
    with shop_context(shop):
        set_pay_rate(staff, daily_rate=Decimal("10000"), effective_from=NOVEMBER, by=None)
    return staff


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    staff = paid(shop_a, "Asha")
    kept_day(staff, *FULL, date=MON)
    return staff


def approve(shop: Shop, by: StaffMember, of: dt.date = NOVEMBER) -> PayRun:
    with shop_context(shop):
        seen = {line.staff_id: line.total for line in pay_month(shop, of).workers}
        return approve_month(shop, of, run_id=uuid.uuid7(), seen=seen, by=by)


# What each service does, of one day: a write, named. `staff` is whose, `by` who writes.


def decide(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    row = next(each for each in work_out_days(shop, day, day) if each.staff_id == staff.pk)
    return decide_day(row, choice=DayChoice.HALF, reason="Aliumwa", replaces=None, by=by)


def add(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    # A Toka at 13:10, before her 18:45: half a day.
    return add_tap(
        staff, tap_id=uuid.uuid7(), kind=ClockKind.OUT, date=day, minute=dt.time(13, 10), reason="Alisahau", by=by
    )


def cross_out(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    zone = dt.timezone(dt.timedelta(hours=3))
    start = dt.datetime.combine(day, dt.time.min, tzinfo=zone)
    tap = AttendanceEvent.objects.filter(staff=staff, trusted_time__gte=start).order_by("trusted_time").first()
    assert tap is not None
    return void_tap(tap, reason="Kwa makosa", by=by)


def rate(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    return set_pay_rate(staff, daily_rate=Decimal("12000"), effective_from=day, by=by)


def meals(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    return record_meal_money(shop, money_id=uuid.uuid7(), date=day, amount=Decimal("1000"), by=by)


def advance(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    return record_advance(staff, advance_id=uuid.uuid7(), date=day, amount=Decimal("1000"), by=by)


def correct(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    # A correction in the pay of the day's month (WAGE-10).
    return record_correction(
        staff, correction_id=uuid.uuid7(), month=day, amount=Decimal("1000"), reason="Oktoba: kosa", by=by
    )


WRITES = {
    "decide": decide,
    "add": add,
    "cross_out": cross_out,
    "rate": rate,
    "meals": meals,
    "advance": advance,
    "correct": correct,
}


def rows() -> tuple[int, ...]:
    """Everything a write could have left behind, in the shop open."""
    return (
        AttendanceDay.objects.exclude(decided_status="").count(),
        AttendanceEvent.objects.count(),
        AttendanceEvent.objects.filter(voided_at__isnull=False).count(),
        PayRate.objects.count(),
        MealMoney.objects.count(),
        MealMoney.objects.filter(voided_at__isnull=False).count(),
        Advance.objects.count(),
        Advance.objects.filter(voided_at__isnull=False).count(),
        PayCorrection.objects.count(),
        PayCorrection.objects.filter(voided_at__isnull=False).count(),
    )


def codes(refusal: ValidationError) -> set[str]:
    """The refusal's codes, whether beside a box or above them."""
    if hasattr(refusal, "error_dict"):
        return {str(error.code) for errors in refusal.error_dict.values() for error in errors}
    return {str(error.code) for error in refusal.error_list}


@pytest.mark.parametrize("name", WRITES)
@pytest.mark.parametrize("day", [MON, LAST])
def test_an_approved_day_takes_no_change(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, name: str, day: dt.date
) -> None:
    if day == LAST:
        kept_day(asha, *FULL, date=LAST)
    approve(shop_a, baba)
    with shop_context(shop_a):
        before = rows()
        with pytest.raises(ValidationError) as refusal:
            WRITES[name](shop_a, asha, baba, day)
        assert codes(refusal.value) == {"pay.day_approved"}
        assert rows() == before


@pytest.mark.parametrize("name", WRITES)
def test_the_day_after_it_still_does(shop_a: Shop, baba: StaffMember, asha: StaffMember, name: str) -> None:
    # 1 December is nobody's payslip yet.
    tapped(asha, *FULL, date=DECEMBER)
    approve(shop_a, baba)
    with shop_context(shop_a):
        before = rows()
        WRITES[name](shop_a, asha, baba, DECEMBER)
        assert rows() != before


def test_each_refusal_is_said_where_its_day_is_picked(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Beside the day's box, on the sheets that ask for a day; above the boxes on the others, opened from one day.
    approve(shop_a, baba)
    boxes = {}
    with shop_context(shop_a):
        for name, write in WRITES.items():
            with pytest.raises(ValidationError) as refusal:
                write(shop_a, asha, baba, MON)
            boxes[name] = set(refusal.value.error_dict) if hasattr(refusal.value, "error_dict") else None
    assert boxes == {
        "decide": None,
        "add": None,
        "cross_out": None,
        "rate": {"effective_from"},
        "meals": {"date"},
        "advance": {"date"},
        # A correction's sheet has no month to pick: it is the page's, so its refusal is above the boxes (WAGE-10).
        "correct": None,
    }


def test_one_with_no_payslip_is_closed_too(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Zawadi came in November with no daily pay, so she is on no payslip. The month is closed for her all the same: no
    # rate from November, no advance of it, or her November would be open with nobody to approve it.
    zawadi = job(shop_a, "Zawadi")
    kept_day(zawadi, *FULL, date=MON)
    approve(shop_a, baba)
    with shop_context(shop_a):
        for write in (decide, add, cross_out, rate, advance):
            with pytest.raises(ValidationError) as refusal:
                write(shop_a, zawadi, baba, MON)
            assert "pay.day_approved" in codes(refusal.value)
        rate(shop_a, zawadi, baba, DECEMBER)


def test_a_month_before_an_approved_one_is_closed(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # October had nothing to pay, so it has no approval of its own. Money typed in it now would be on nobody's pay, as
    # November is already closed: Asha's, who has a payslip of November, and Zawadi's, who has none; and the shop's own.
    zawadi = job(shop_a, "Zawadi")
    approve(shop_a, baba)
    with shop_context(shop_a):
        rate(shop_a, zawadi, baba, DECEMBER)
        for day in (dt.date(2026, 10, 20), dt.date(2026, 2, 3)):
            for staff in (asha, zawadi):
                with pytest.raises(ValidationError) as refusal:
                    advance(shop_a, staff, baba, day)
                assert codes(refusal.value) == {"pay.day_approved"}
            assert is_closed(shop_a, day) is True
        assert is_closed(shop_a, DECEMBER) is False


def test_another_shops_approval_closes_nothing_here(
    shop_a: Shop, shop_b: Shop, baba: StaffMember, asha: StaffMember, staff_b: StaffMember
) -> None:
    PayRun(shop=shop_b, month=DECEMBER, created_by=staff_b).save()
    with shop_context(shop_a):
        advance(shop_a, asha, baba, MON)


# Crossing out money, and what is sent twice.


def test_money_of_an_approved_month_is_not_crossed_out(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    with shop_context(shop_a):
        typed, given = meals(shop_a, asha, baba, MON), advance(shop_a, asha, baba, MON)
        later = (meals(shop_a, asha, baba, DECEMBER), advance(shop_a, asha, baba, DECEMBER))
    approve(shop_a, baba)
    with shop_context(shop_a):
        before = rows()
        for void, row in ((void_meal_money, typed), (void_advance, given)):
            with pytest.raises(ValidationError) as refusal:
                void(row, reason="Sifuri moja zaidi", by=baba)
            assert codes(refusal.value) == {"pay.day_approved"}
        assert rows() == before
        void_meal_money(later[0], reason="Sifuri moja zaidi", by=baba)
        void_advance(later[1], reason="Sifuri moja zaidi", by=baba)


def test_what_was_done_before_the_approval_is_answered_as_done(
    shop_a: Shop, baba: StaffMember, asha: StaffMember
) -> None:
    # Decided and crossed out a moment before Baba approved, the answers lost on the way: sent again after it, each is
    # answered as it was kept, never refused as if it hadn't been made (03 §5.5).
    with shop_context(shop_a):
        day = decide(shop_a, asha, baba, MON)
        extra = add(shop_a, asha, baba, TUE)
        tap = void_tap(extra, reason="Kwa makosa", by=baba)
        money = void_meal_money(meals(shop_a, asha, baba, MON), reason="Kosa", by=baba)
        given = void_advance(advance(shop_a, asha, baba, MON), reason="Kosa", by=baba)
    approve(shop_a, baba)
    with shop_context(shop_a):
        again = decide_day(day, choice=DayChoice.HALF, reason="Aliumwa", replaces=None, by=baba)
        assert again.decided_at == day.decided_at
        assert void_tap(extra, reason="Kwa makosa", by=baba).voided_at == tap.voided_at
        assert void_meal_money(money, reason="Kosa", by=baba).voided_at == money.voided_at
        assert void_advance(given, reason="Kosa", by=baba).voided_at == given.voided_at
        # Decided otherwise, it is refused: by the approval, before anything else.
        with pytest.raises(ValidationError) as refusal:
            decide_day(again, choice=DayChoice.ON_TIME, reason="Alikuja", replaces=again.decided_at, by=baba)
        assert codes(refusal.value) == {"pay.day_approved"}


def test_a_tap_falls_on_the_shops_own_day(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # A tap at 00:30 on 1 December in Arusha is 21:30 UTC of 30 November: December's, which is open. One of 23:30 on 30
    # November is November's.
    tapped(asha, (ClockKind.IN, 23, 30), date=LAST)
    tapped(asha, (ClockKind.IN, 0, 30), date=DECEMBER)
    with shop_context(shop_a):
        late, early = AttendanceEvent.objects.filter(staff=asha).order_by("-trusted_time")[:2]
        decide(shop_a, asha, baba, LAST)
    approve(shop_a, baba)
    with shop_context(shop_a):
        with pytest.raises(ValidationError):
            void_tap(early, reason="Kwa makosa", by=baba)
        void_tap(late, reason="Kwa makosa", by=baba)


# One approved alone.


@pytest.fixture
def neema(shop_a: Shop, baba: StaffMember, monkeypatch: pytest.MonkeyPatch) -> StaffMember:
    # Neema came on Monday 16, was given 2,000, left that evening, and was approved alone the next day.
    staff = paid(shop_a, "Neema")
    kept_day(staff, *FULL, date=MON)
    with shop_context(shop_a):
        advance(shop_a, staff, baba, MON)
        staff = mark_left(staff, left_on=MON, by=baba, reason="Amehama")
        total = next(line.total for line in pay_month(shop_a, NOVEMBER).workers if line.staff_id == staff.pk)
        approve_leaver(staff, NOVEMBER, payslip_id=uuid.uuid7(), seen=total, by=baba)
    return staff


@pytest.mark.parametrize("name", ["decide", "add", "cross_out", "advance"])
def test_one_approved_alone_takes_no_change(shop_a: Shop, baba: StaffMember, neema: StaffMember, name: str) -> None:
    with shop_context(shop_a):
        before = rows()
        with pytest.raises(ValidationError) as refusal:
            WRITES[name](shop_a, neema, baba, MON)
        assert codes(refusal.value) == {"pay.day_approved"}
        given = Advance.objects.get(staff=neema)
        with pytest.raises(ValidationError) as refusal:
            void_advance(given, reason="Kosa", by=baba)
        assert codes(refusal.value) == {"pay.day_approved"}
        assert rows() == before


def test_one_approved_alone_takes_no_correction(shop_a: Shop, baba: StaffMember, neema: StaffMember) -> None:
    # Neema's pay is approved alone, and no later pay of hers will be made: whatever month is asked, the system says
    # why, and Baba pays her by hand (WAGE-10, Jack: A).
    with shop_context(shop_a):
        for month in (NOVEMBER, DECEMBER):
            with pytest.raises(ValidationError) as refusal:
                correct(shop_a, neema, baba, month)
            assert codes(refusal.value) == {"correction.left_paid"}
        assert not PayCorrection.objects.exists()


@pytest.mark.parametrize("by_the_system", [False, True])
def test_a_rate_of_one_approved_alone_is_refused(
    shop_a: Shop, baba: StaffMember, neema: StaffMember, by_the_system: bool
) -> None:
    # Her last day was paid at the rate there was, and no day of hers comes after it: one typed now could only say
    # another, for the system too.
    with shop_context(shop_a):
        for day in (NOVEMBER, MON):
            with pytest.raises(ValidationError) as refusal:
                set_pay_rate(neema, daily_rate=Decimal("20000"), effective_from=day, by=None if by_the_system else baba)
            assert codes(refusal.value) == {"pay.day_approved"}


@pytest.mark.parametrize("name", WRITES)
def test_one_approved_alone_locks_nothing_of_the_others(
    shop_a: Shop, baba: StaffMember, neema: StaffMember, asha: StaffMember, name: str
) -> None:
    # Nor the shop's meal money: the others' shares still move, and hers stays as she paid it.
    with shop_context(shop_a):
        before = rows()
        WRITES[name](shop_a, asha, baba, MON)
        assert rows() != before
        assert is_closed(shop_a, MON) is False


def test_the_month_is_asked_of_its_own_shop(shop_a: Shop, shop_b: Shop) -> None:
    # Inside another shop's visit the guard would hide the approval, and a closed month would take a change (ADR-0022).
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        is_closed(shop_a, MON)
    with shop_context(shop_a), pytest.raises(TypeError):
        is_closed(shop_a, dt.datetime(2026, 11, 16, tzinfo=dt.UTC))


# The calendar of an approved month.


def test_an_approved_day_offers_no_decision_and_reads_no_rules(
    shop_a: Shop, baba: StaffMember, asha: StaffMember
) -> None:
    # Offered before it, on every day that isn't off; none after. And its copy of the rules is never read back: a rule
    # added later is missing from it, which stops no page from opening (ATT-6's review).
    with shop_context(shop_a):
        before = worker_attendance(shop_a, asha, NOVEMBER, viewer=baba)
        assert {day.date for day in before.days if day.choices} == {
            day.date for day in before.days if day.status != "off"
        }
        AttendanceDay.objects.filter(staff=asha, date=MON).update(rules_used={"closing": "18:40"})
    approve(shop_a, baba)
    with shop_context(shop_a):
        after = worker_attendance(shop_a, asha, NOVEMBER, viewer=baba)
    assert not [day for day in after.days if day.choices]
    assert [day.status for day in after.days] == [day.status for day in before.days]


def to_decide(shop: Shop) -> list[tuple[str, dt.date]]:
    """Zinahitaji uamuzi of November, and who is counted as having one."""
    with shop_context(shop):
        answer = attendance_month(shop, NOVEMBER)
    assert sum(line.needs_review for line in answer.workers) == len(answer.to_decide)
    return [(day.staff.display_name, day.date) for day in answer.to_decide]


def test_a_tap_that_came_after_the_approval_is_nobodys_to_decide(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, neema: StaffMember
) -> None:
    # Neema left on the 16th and was paid alone; then a laptop sends her Ingia of the 17th. The server takes no decision
    # on it, so no page asks for one (WAGE-3's review): on her calendar it is a tap that isn't counted. Asha's open
    # day waits, and stays to decide.
    for staff in (asha, neema):
        tapped(staff, (ClockKind.IN, 7, 20), date=TUE)
    assert to_decide(shop_a) == [("Asha", TUE)]
    with shop_context(shop_a):
        hers = worker_attendance(shop_a, neema, NOVEMBER, viewer=baba)
        ashas = worker_attendance(shop_a, asha, NOVEMBER, viewer=baba)
    assert TUE not in {day.date for day in hers.days}
    assert [tap.date for tap in hers.taps if tap.date == TUE] == [TUE]
    assert (hers.worker.needs_review, hers.closed, ashas.worker.needs_review, ashas.closed) == (0, True, 1, False)
    # Her days that were paid are still there.
    assert MON in {day.date for day in hers.days}


def test_nor_is_one_that_came_after_the_whole_months(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Asha left on the 16th, November was approved for everyone, and then her Ingia of the 17th comes.
    with shop_context(shop_a):
        mark_left(asha, left_on=MON, by=baba, reason="Amehama")
    approve(shop_a, baba)
    tapped(asha, (ClockKind.IN, 7, 20), date=TUE)
    assert to_decide(shop_a) == []


def test_the_other_days_of_an_approved_month_stay_on_the_calendar(
    shop_a: Shop, baba: StaffMember, asha: StaffMember
) -> None:
    # Zawadi has no daily pay, so no payslip marks her days: the month is closed for her too, and her calendar says what
    # each was. And Asha's Tuesday, with no Toka, which Baba decided before he approved it: the book still says it needs
    # a person, beside his decision (A2), and it was paid.
    zawadi = job(shop_a, "Zawadi")
    kept_day(zawadi, *FULL, date=MON)
    waited = kept_day(asha, (ClockKind.IN, 7, 20), date=TUE)
    with shop_context(shop_a):
        decide_day(waited, choice=DayChoice.ON_TIME, reason="Alisahau Toka", replaces=None, by=baba)
    approve(shop_a, baba)
    with shop_context(shop_a):
        hers = worker_attendance(shop_a, zawadi, NOVEMBER, viewer=baba)
        ashas = worker_attendance(shop_a, asha, NOVEMBER, viewer=baba)
        listed = attendance_month(shop_a, NOVEMBER)
    assert (hers.closed, hers.worker.on_time) == (True, 1)
    assert {day.status for day in hers.days} == {"on_time", "absent", "off"}
    assert TUE in {day.date for day in ashas.days}
    assert ashas.worker.on_time == 2
    assert [line.on_time for line in listed.workers if line.display_name == "Asha"] == [2]


# Two at once: the write waits for the approval, and then finds the day approved.


def cross_out_meals(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    return void_meal_money(MealMoney.objects.get(date=day), reason="Kosa", by=by)


def cross_out_advance(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    return void_advance(Advance.objects.get(staff=staff, date=day), reason="Kosa", by=by)


def cross_out_correction(shop: Shop, staff: StaffMember, by: StaffMember, day: dt.date) -> Any:
    return void_correction(PayCorrection.objects.get(staff=staff, month=day.replace(day=1)), reason="Kosa", by=by)


# The ten services, each a write that waits for the approval's lock: a correction and its crossing out among them
# (WAGE-10). The three that cross money out need some there.
ALL_WRITES = WRITES | {
    "cross_out_meals": cross_out_meals,
    "cross_out_advance": cross_out_advance,
    "cross_out_correction": cross_out_correction,
}


def with_money_to_cross_out(shop: Shop, staff: StaffMember, by: StaffMember, name: str) -> None:
    with shop_context(shop):
        if name == "cross_out_meals":
            meals(shop, staff, by, MON)
        elif name == "cross_out_advance":
            advance(shop, staff, by, MON)
        elif name == "cross_out_correction":
            correct(shop, staff, by, MON)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("name", ALL_WRITES)
def test_a_write_beside_an_approval_waits_and_is_refused(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, name: str
) -> None:
    # Baba approves while Meneja's write is on its way: the approval holds its lock, so the write never slips between
    # what Baba read and what is kept.
    with_money_to_cross_out(shop_a, asha, baba, name)
    with shop_context(shop_a):
        seen = {line.staff_id: line.total for line in pay_month(shop_a, NOVEMBER).workers}

    def write() -> str:
        with shop_context(shop_a):
            try:
                ALL_WRITES[name](shop_a, asha, baba, MON)
            except ValidationError as refusal:
                return ",".join(codes(refusal))
        return "written"

    with shop_context(shop_a), transaction.atomic():
        approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=seen, by=baba)
        thread, ended = in_another_transaction(write)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["pay.day_approved"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("name", ALL_WRITES)
def test_an_approval_beside_a_write_waits_and_sees_it(
    shop_a: Shop, baba: StaffMember, asha: StaffMember, name: str
) -> None:
    # The other way round: the write first, not committed yet, and Baba approves the total he read before it. He waits
    # for it, and is refused: a total has moved, or, with a tap of hers crossed out, a day waits for a decision.
    with_money_to_cross_out(shop_a, asha, baba, name)
    with shop_context(shop_a):
        seen = {line.staff_id: line.total for line in pay_month(shop_a, NOVEMBER).workers}

    def late_approval() -> str:
        with shop_context(shop_a):
            try:
                approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=seen, by=baba)
            except ValidationError as refusal:
                return ",".join(codes(refusal))
        return "approved"

    with shop_context(shop_a), transaction.atomic():
        ALL_WRITES[name](shop_a, asha, baba, MON)
        thread, ended = in_another_transaction(late_approval)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["pay_run.days_waiting" if name == "cross_out" else "pay_run.totals_moved"]
    with shop_context(shop_a):
        assert not Payslip.objects.exists()
