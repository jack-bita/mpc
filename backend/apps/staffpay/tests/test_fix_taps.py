"""apps/staffpay/tests/test_fix_taps.py — a manager fixes a worker's taps (ATT-13; 02 §12): adds one the worker forgot
(add_tap), or crosses out one made by mistake (void_tap).

Juma's Thursday: Ingia at 07:20, then Toka at 10:00 by mistake; he worked on to 18:45 and left with no tap. Baba, the
owner, crosses out the 10:00 Toka and adds Toka 18:45, and the book works the day out again: a full day, as the shop
closes at 18:40.

    the one fixing                           the answer
    Baba, or a manager, on Juma's taps       the tap added, or crossed out, with who, when and why
    a manager on his own taps                tap.own: the owner fixes the manager's (as ATT-6's day.own)
    a seller                                 403
    a Sunday, a day outside the job's        tap.not_working_day
    a minute still to come                   tap.in_future
    no reason                                tap.reason_missing
    on the demo, a reason typed              demo.ready_reasons: the ready one

The fines are the demo's made-up 500 and 1,500 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from pytest_django import Settings

from apps.core.acting import acting_as
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Closure, Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.models import AttendanceEvent, ClockKind, DayStatus, NoPhoto, ReviewReason, TimeCheck
from apps.staffpay.services import add_tap
from apps.staffpay.tests.days import ARUSHA, FIRST_FINE, MONDAY, SUNDAY, absent_day, job, kept_day, switch_on

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture(autouse=True)
def the_shops_day(shop_a: Shop, device_a: Device) -> None:
    # The shop switched attendance on in January, with the owner's fines, and keeps its laptop, Laptop ya Dawa, where
    # every laptop tap below is made (days.py).
    switch_on(shop_a)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, on the whole shop.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager, who holds attendance.manage on the whole shop, as the demo's Meneja does.
    staff = job(shop_a, "Meneja")
    give_role(staff, RoleTemplate.MANAGER, None)
    return staff


@pytest.fixture
def juma(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    # A seller of the Dawa side.
    staff = job(shop_a, "Juma")
    give_role(staff, RoleTemplate.SELLER, side_a)
    return staff


def add(
    staff: StaffMember,
    by: StaffMember,
    kind: ClockKind = ClockKind.OUT,
    hour: int = 18,
    minute: int = 45,
    date: dt.date = MONDAY,
    reason: str = "Alisahau kubonyeza Toka",
    tap_id: uuid.UUID | None = None,
) -> AttendanceEvent:
    # As the route calls it: inside the shop, in the person's visit.
    with shop_context(staff.shop_id), acting_as(by):
        return add_tap(
            staff,
            tap_id=tap_id or uuid.uuid7(),
            kind=kind,
            date=date,
            minute=dt.time(hour, minute),
            reason=reason,
            by=by,
        )


def codes_of(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, set[str]]:
    # Each box's codes, as the sheet shows them beside it.
    return {field: {error.code or "" for error in errors} for field, errors in refused.value.error_dict.items()}


def taps_of(staff: StaffMember) -> list[AttendanceEvent]:
    with shop_context(staff.shop_id):
        return list(AttendanceEvent.objects.filter(staff=staff).order_by("trusted_time"))


# A tap added.


def test_baba_adds_jumas_forgotten_toka(baba: StaffMember, juma: StaffMember) -> None:
    # The card's story: Juma came at 07:20 and forgot his Toka, so his Monday waits, "hakuna Toka". Baba adds Toka 18:45
    # and the book works the day out again with it: a full day, on time, as the shop closes at 18:40, nothing for
    # anyone to decide.
    day = kept_day(juma, (ClockKind.IN, 7, 20))
    assert (day.status, day.review_reason) == (DayStatus.NEEDS_REVIEW, ReviewReason.NO_OUT)
    add(juma, baba)
    day = absent_day(juma)
    assert (day.status, day.fine, day.first_in, day.first_out) == (
        DayStatus.ON_TIME,
        Decimal("0.00"),
        dt.time(7, 20),
        dt.time(18, 45),
    )


def test_an_added_tap_is_the_offices(baba: StaffMember, juma: StaffMember) -> None:
    # A line no laptop made: who entered it, whose it is, the minute typed on the shop's clock, trusted, when it was
    # entered, why, and no photo, by the office's own reason (ATT-13).
    tap = add(juma, baba)
    assert (tap.device_id, tap.device_seq, tap.client_time, tap.last_server_time, tap.clock_error) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert (tap.created_by_id, tap.staff_id, tap.kind) == (baba.pk, juma.pk, ClockKind.OUT)
    assert tap.trusted_time == dt.datetime(2026, 11, 16, 18, 45, tzinfo=ARUSHA)
    assert (tap.time_check, tap.no_photo, tap.entry_reason) == (
        TimeCheck.ENTERED,
        NoPhoto.ENTERED,
        "Alisahau kubonyeza Toka",
    )
    assert tap.received_at is not None
    assert taps_of(juma) == [tap]


def test_an_added_ingia_takes_its_fine(baba: StaffMember, juma: StaffMember) -> None:
    # Juma forgot his Ingia, and Baba says he came at 07:50: the minute Baba typed is trusted, as a real tap's would
    # be, so the day is late, with the first fine (a Claude default Jack said yes to).
    kept_day(juma, (ClockKind.OUT, 18, 45))
    add(juma, baba, ClockKind.IN, 7, 50, reason="Alisahau kubonyeza Ingia")
    day = absent_day(juma)
    assert (day.status, day.fine, day.first_in) == (DayStatus.LATE, FIRST_FINE, dt.time(7, 50))


def test_seconds_are_dropped_from_the_minute(baba: StaffMember, juma: StaffMember) -> None:
    # A minute on the shop's clock, as the counter shows one (shop_minute): 07:35:40 is 07:35, on time.
    with shop_context(juma.shop_id), acting_as(baba):
        tap = add_tap(
            juma,
            tap_id=uuid.uuid7(),
            kind=ClockKind.IN,
            date=MONDAY,
            minute=dt.time(7, 35, 40),
            reason="Alisahau kubonyeza Ingia",
            by=baba,
        )
    assert tap.trusted_time == dt.datetime(2026, 11, 16, 7, 35, tzinfo=ARUSHA)


def test_a_reason_is_kept_without_its_spaces(baba: StaffMember, juma: StaffMember) -> None:
    assert add(juma, baba, reason="  Alisahau kubonyeza Toka \n").entry_reason == "Alisahau kubonyeza Toka"


def test_a_manager_adds_a_workers_tap(meneja: StaffMember, juma: StaffMember) -> None:
    # attendance.manage is the manager's too: Meneja adds Juma's Toka, as on the demo.
    assert add(juma, meneja).created_by_id == meneja.pk


def test_a_closed_day_takes_a_tap_and_waits_for_a_decision(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # The owner closed the shop for a funeral, and Juma came that morning all the same: his tap on a closed day sends
    # the day to review, as a laptop's would (ATT-10), so a closed day is no reason to refuse it. The closure written
    # past its service, which takes no day gone by, as the book's tests write theirs.
    with shop_context(shop_a):
        Closure(shop=shop_a, first_day=MONDAY, last_day=MONDAY, name="Msiba wa bibi").save()
    add(juma, baba, ClockKind.IN, 7, 20, reason="Alisahau kubonyeza Ingia")
    day = absent_day(juma)
    assert (day.status, day.review_reason) == (DayStatus.NEEDS_REVIEW, ReviewReason.CLOSED_DAY)


# Who may.


def test_nobody_adds_their_own_tap(baba: StaffMember, meneja: StaffMember) -> None:
    # Meneja came late and never tapped Ingia: adding his own at 07:20 would take his own fine off. The owner adds it.
    with pytest.raises(ValidationError) as refused:
        add(meneja, meneja, ClockKind.IN, 7, 20)
    assert refused.value.code == "tap.own"
    assert taps_of(meneja) == []
    add(meneja, baba, ClockKind.IN, 7, 20)


def test_a_seller_is_refused(shop_a: Shop, side_a: Side, give_role: GiveRole, juma: StaffMember) -> None:
    # Asha sells on the Dawa side: she holds no attendance.manage, so she may not add Juma's tap.
    asha = job(shop_a, "Asha")
    give_role(asha, RoleTemplate.SELLER, side_a)
    with pytest.raises(PermissionDenied):
        add(juma, asha)
    assert taps_of(juma) == []


def test_a_suspended_manager_is_refused(meneja: StaffMember, juma: StaffMember) -> None:
    # Meneja is suspended this morning: his keys stop at once (X2), read afresh inside the fix.
    with shop_context(meneja.shop_id):
        suspend(meneja, by=None, reason="Uchunguzi wa hesabu")
    with pytest.raises(PermissionDenied):
        add(juma, meneja)


def test_a_key_on_one_side_adds_nothing(shop_a: Shop, side_a: Side, juma: StaffMember) -> None:
    # Attendance is the whole shop's, so a key on the Dawa side alone fixes no tap (X1).
    hamisi = job(shop_a, "Hamisi")
    with shop_context(shop_a):
        grant_permission(hamisi, Permission.ATTENDANCE_MANAGE, side=side_a, by=None)
    with pytest.raises(PermissionDenied):
        add(juma, hamisi)


def test_a_person_hired_again_adds_no_tap_to_either_job(shop_a: Shop, give_role: GiveRole, baba: StaffMember) -> None:
    # Baraka sold until Tuesday 17th, and comes back on the 18th as a manager (PPL-11): one person, two jobs. His old
    # job's Monday is still his own, so the rule reads the person, never the job.
    old = job(shop_a, "Baraka")
    with shop_context(shop_a):
        mark_left(old, left_on=dt.date(2026, 11, 17), by=None, reason="Ameacha kazi")
        old.refresh_from_db()
        new = hire_again(old, display_name="Baraka", started_on=dt.date(2026, 11, 18), by=None)
    give_role(new, RoleTemplate.MANAGER, None)
    with pytest.raises(ValidationError) as refused:
        add(old, new)
    assert refused.value.code == "tap.own"
    add(old, baba)


def test_a_person_of_another_shop_is_a_bug(staff_b: StaffMember, juma: StaffMember) -> None:
    # The route finds the worker and the person in the one shop open, so another shop's person here is a bug in our
    # code (T1): a server error, before anything is read or written.
    with shop_context(juma.shop_id), pytest.raises(ShopMismatch):
        add_tap(
            juma,
            tap_id=uuid.uuid7(),
            kind=ClockKind.OUT,
            date=MONDAY,
            minute=dt.time(18, 30),
            reason="Alisahau",
            by=staff_b,
        )
    assert taps_of(juma) == []


# Which days, and which minutes.


def test_a_sunday_takes_no_tap(baba: StaffMember, juma: StaffMember) -> None:
    # The shop is shut on Sundays, and Sunday work is paid outside the system (01 §8.1): a tap there counts nothing.
    with pytest.raises(ValidationError) as refused:
        add(juma, baba, date=SUNDAY)
    assert refused.value.code == "tap.not_working_day"


def test_a_day_outside_the_job_takes_no_tap(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # Neema starts on Tuesday the 17th: a tap on Monday, before her first day, would send it to review for nothing
    # (ATT-11); and none after Juma's last day either.
    neema = job(shop_a, "Neema")
    with shop_context(shop_a):
        StaffMember.objects.filter(pk=neema.pk).update(started_on=dt.date(2026, 11, 17))
        mark_left(juma, left_on=dt.date(2026, 11, 13), by=None, reason="Ameacha kazi")
    for worker in (neema, juma):
        with pytest.raises(ValidationError) as refused:
            add(worker, baba)
        assert refused.value.code == "tap.not_working_day"


def test_a_minute_to_come_is_refused(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # At 10:05 Juma's 18:45 Toka hasn't happened yet: a tap is added once it is true, never before.
    # Tomorrow, or the day after when tomorrow is a Sunday, so the day itself is one a tap may take.
    with shop_context(shop_a):
        later = shop_today(shop_a) + dt.timedelta(days=1)
    if later.weekday() == SUNDAY.weekday():
        later += dt.timedelta(days=1)
    with pytest.raises(ValidationError) as refused:
        add(juma, baba, hour=7, minute=20, date=later)
    assert codes_of(refused) == {"time": {"tap.in_future"}}
    assert taps_of(juma) == []


def test_no_reason_is_refused(baba: StaffMember, juma: StaffMember) -> None:
    # A tap entered in the office says why (T3): spaces alone say nothing.
    for reason in ("", "   "):
        with pytest.raises(ValidationError) as refused:
            add(juma, baba, reason=reason)
        assert codes_of(refused) == {"reason": {"tap.reason_missing"}}
    assert taps_of(juma) == []


# The demo.


def test_on_the_demo_a_reason_is_the_ready_one(settings: Settings, baba: StaffMember, juma: StaffMember) -> None:
    # Every visitor logs in as Meneja (OPS-3): a typed reason would show to every visitor after them, so adding a tap
    # takes the one ready reason, *Alisahau kubonyeza*, kept as its code (Jack: A, as ATT-6's ready reasons).
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        add(juma, baba, reason="Maneno ya mgeni")
    assert codes_of(refused) == {"reason": {"demo.ready_reasons"}}
    # Crossing out's ready reason is not adding's.
    with pytest.raises(ValidationError):
        add(juma, baba, reason="wrong_tap")
    assert add(juma, baba, reason="forgot_tap").entry_reason == "forgot_tap"
