"""apps/staffpay/tests/test_attendance_book.py — the book of days: one row per worker per day, worked out by ATT-4's
rule from that day's taps and that day's rules, and kept (ATT-10; 02 §12).

    who    date        status        fine    in     out
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Asha   Sun 22 Nov  off           0.00    —      —

First the rules the database keeps on a day (AttendanceDay, apps/staffpay/models.py): one per job and date, a day that
fits its status, and never a delete. Then the book (work_out_days, apps/staffpay/services.py): which taps a day reads,
on which date, with which rules, and how a day worked out again is kept. Then the taps in doubt (ATT-11), each sending
its day to review. Last, why a day needs a decision (ATT-5): each day to decide keeps its one reason. What a day was,
from its taps, is the rule's, in test_attendance_day.py. Times are Arusha's, three hours ahead of UTC. The fines are
the demo's made-up 500 and 1,500 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import itertools
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.control.models import EditEvent, Flag, FlagKind
from apps.control.services import dismiss_flag, raise_flag
from apps.core.acting import acting_as
from apps.core.links import table_of
from apps.core.models import ShopScoped
from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON, LATE_FINE, SettingKey
from apps.core.tenancy import ShopMismatch, shop_context, system_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, change_worker, hire_again, mark_left
from apps.shops.models import Closure, Setting, Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.models import (
    AttendanceDay,
    AttendanceEvent,
    ClockKind,
    DayChoice,
    DayStatus,
    ReviewReason,
    TimeCheck,
)
from apps.staffpay.services import decide_day, work_out_days
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

MONDAY = dt.date(2026, 11, 16)


def _day(shop: Shop, staff: StaffMember, **changes: object) -> AttendanceDay:
    # Asha's Monday of the table above: late, the first fine taken off; `changes` overrides a fact.
    facts: dict[str, object] = {
        "shop": shop,
        "staff": staff,
        "date": MONDAY,
        "status": DayStatus.LATE,
        "fine": Decimal("500.00"),
        "first_in": dt.time(7, 50),
        "first_out": dt.time(18, 45),
        "rules_used": {"late_fine": "500.00"},
    }
    facts.update(changes)
    return AttendanceDay(**facts)


def test_one_row_per_worker_per_day(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # However often the book runs, Asha has one Monday: a second row of the same job and date is refused, whoever
    # writes it. Another worker's Monday, or Asha's Tuesday, is a day of its own.
    _day(shop_a, staff_a).save()
    with pytest.raises(IntegrityError, match="one_per_job_and_date"), transaction.atomic():
        _day(shop_a, staff_a, status=DayStatus.ON_TIME, fine=Decimal("0.00")).save()
    _day(shop_a, staff_a2).save()
    _day(shop_a, staff_a, date=MONDAY + dt.timedelta(days=1)).save()
    with shop_context(shop_a):
        assert AttendanceDay.objects.count() == 3


@pytest.mark.parametrize(
    "changes",
    [
        # An off day, a Sunday, takes no fine and reads no tap.
        {"status": DayStatus.OFF},
        {"status": DayStatus.OFF, "fine": Decimal("0.00")},
        # Absent: nobody came, so no tap to read.
        {"status": DayStatus.ABSENT, "fine": Decimal("0.00"), "first_out": None},
        # On time takes no fine.
        {"status": DayStatus.ON_TIME},
        # A late day read both taps, and a fine is never below 0.
        {"first_out": None},
        {"fine": Decimal("-500.00")},
        # A day sent to review takes no fine: a manager decides it (ATT-6).
        {"status": DayStatus.NEEDS_REVIEW},
        # And only the statuses there are.
        {"status": "holiday", "fine": Decimal("0.00")},
    ],
)
def test_a_day_fits_its_status(shop_a: Shop, staff_a: StaffMember, changes: dict[str, object]) -> None:
    # Only the book writes a day, so each of these is a bug in its code, which the database refuses as the last guard
    # (03 §5.6), before a wrong fine reaches a payslip.
    with pytest.raises(IntegrityError, match="fits_its_status"), transaction.atomic():
        _day(shop_a, staff_a, **changes).save()


@pytest.mark.parametrize(
    "changes",
    [
        # An off day reads no rule, so it keeps no copy of one.
        {"status": DayStatus.OFF, "fine": Decimal("0.00"), "first_in": None, "first_out": None},
        # Every other day was read by the rule, so it keeps its copy: a fix of it later reads its fine from there.
        {"rules_used": {}},
        {"status": DayStatus.ABSENT, "fine": Decimal("0.00"), "first_in": None, "first_out": None, "rules_used": {}},
        {"status": DayStatus.NEEDS_REVIEW, "fine": Decimal("0.00"), "rules_used": {}},
    ],
)
def test_only_an_off_day_keeps_no_rules(shop_a: Shop, staff_a: StaffMember, changes: dict[str, object]) -> None:
    # The rules kept with a day exactly when the rule read them (T4): a bug that drops the copy, or gives an off day
    # one, is refused before it reaches a payslip.
    with pytest.raises(IntegrityError, match="rules_kept_unless_off"), transaction.atomic():
        _day(shop_a, staff_a, **changes).save()


@pytest.mark.parametrize(
    "changes",
    [
        # A reason only on a day to decide: a late day has its answer already.
        {"review_reason": ReviewReason.NO_OUT},
        {"status": DayStatus.OFF, "fine": Decimal("0.00"), "first_in": None, "first_out": None, "rules_used": {}}
        | {"review_reason": ReviewReason.CLOSED_DAY},
        # And only the reasons there are.
        {"status": DayStatus.NEEDS_REVIEW, "fine": Decimal("0.00"), "review_reason": "lazy"},
    ],
)
def test_a_reason_only_on_a_day_to_decide(shop_a: Shop, staff_a: StaffMember, changes: dict[str, object]) -> None:
    # A reason on a day nobody must decide would put it on the month page's list for nothing (ATT-5): a bug in the
    # book, which the database refuses as the last guard.
    with pytest.raises(IntegrityError, match="reason_only_to_decide"), transaction.atomic():
        _day(shop_a, staff_a, **changes).save()


def test_each_status_saves_as_it_should(shop_a: Shop, staff_a: StaffMember) -> None:
    # The rule's other side: every status, as the book writes it, is kept. A late day with a fine of 0, as a shop
    # starts with (ATT-2); the morning's half with a late arrival's fine (the owner, ATT-4); and a day for review with
    # its taps, or with none, with its reason, or with none, as a day kept before ATT-5 has.
    days = [
        {"status": DayStatus.LATE, "fine": Decimal("0.00")},
        {"status": DayStatus.HALF, "first_out": dt.time(13, 10)},
        {"status": DayStatus.ON_TIME, "fine": Decimal("0.00"), "first_in": dt.time(7, 20)},
        {"status": DayStatus.OFF, "fine": Decimal("0.00"), "first_in": None, "first_out": None, "rules_used": {}},
        {"status": DayStatus.ABSENT, "fine": Decimal("0.00"), "first_in": None, "first_out": None},
        {"status": DayStatus.NEEDS_REVIEW, "fine": Decimal("0.00"), "first_out": None},
        {"status": DayStatus.NEEDS_REVIEW, "fine": Decimal("0.00"), "first_in": None, "first_out": None},
        {"status": DayStatus.NEEDS_REVIEW, "fine": Decimal("0.00"), "review_reason": ReviewReason.CAME_LATE},
    ]
    for offset, changes in enumerate(days):
        _day(shop_a, staff_a, date=MONDAY + dt.timedelta(days=offset), **changes).save()
    with shop_context(shop_a):
        assert AttendanceDay.objects.count() == len(days)


def test_database_refuses_to_delete_a_day(shop_a: Shop, staff_a: StaffMember) -> None:
    # Rule 7: a day is worked out again, never deleted. Nothing links to one yet, so PROTECT can't stop a delete: the
    # table's own trigger does, whoever sends it, a row's delete() or a bulk one.
    row = _day(shop_a, staff_a)
    row.save()
    with shop_context(shop_a):
        with pytest.raises(IntegrityError, match="never deleted"), transaction.atomic():
            row.delete()
        with pytest.raises(IntegrityError, match="never deleted"), transaction.atomic():
            AttendanceDay.objects.filter(pk=row.pk).delete()
        assert AttendanceDay.objects.filter(pk=row.pk).exists()


# A manager's decision on a day (ATT-6): Juma's Monday, sent to review with no Toka, decided a full day by Baba, with
# why. The decision sits beside what the book worked out, which keeps its own status, fine and reason.
DECIDED_AT = dt.datetime(2026, 11, 20, 9, 0, tzinfo=dt.UTC)


def _decided(shop: Shop, staff: StaffMember, by: StaffMember, **changes: object) -> AttendanceDay:
    # The day as the book sent it to review, with a whole decision on it; `changes` overrides a part.
    decision: dict[str, object] = {
        "decided_status": DayStatus.ON_TIME,
        "decided_fine": Decimal("0.00"),
        "decided_by": by,
        "decided_at": DECIDED_AT,
        "decision_reason": "Alisahau kubonyeza Toka",
    }
    decision.update(changes)
    return _day(
        shop,
        staff,
        status=DayStatus.NEEDS_REVIEW,
        fine=Decimal("0.00"),
        first_out=None,
        review_reason=ReviewReason.NO_OUT,
        **decision,
    )


@pytest.mark.parametrize(
    "changes",
    [
        # Who, when, how much and why: each part of a decision, missing.
        {"decided_by": None},
        {"decided_at": None},
        {"decided_fine": None},
        {"decision_reason": ""},
        # Spaces alone are no reason.
        {"decision_reason": "   "},
        # And no part of a decision without the decision itself.
        {
            "decided_status": "",
            "decided_fine": None,
            "decided_by": None,
            "decided_at": None,
            "decision_reason": "Alienda benki",
        },
        {
            "decided_status": "",
            "decided_fine": None,
            "decided_at": None,
            "decision_reason": "",
        },
    ],
)
def test_a_decision_is_whole_or_none(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, changes: dict[str, object]
) -> None:
    # Every decision says who, when and why (rule 7), as a void's stamp does: only decide_day writes one, after its
    # own checks, so half of one is a bug in our code, which the database refuses as the last guard (03 §5.6).
    with pytest.raises(IntegrityError, match="decision_whole_or_none"), transaction.atomic():
        _decided(shop_a, staff_a, staff_a2, **changes).save()


@pytest.mark.parametrize(
    "changes",
    [
        # Absent says why they were away: office duty is paid, the other two are not, so the pay needs to know.
        {"decided_status": DayStatus.ABSENT},
        # And takes no fine, nor does a full day.
        {"decided_status": DayStatus.ABSENT, "absence_type": "no_show", "decided_fine": Decimal("500.00")},
        {"decided_fine": Decimal("500.00")},
        # A fine is never below 0.
        {"decided_status": DayStatus.LATE, "decided_fine": Decimal("-500.00")},
        # An absence kind only on an absent day: a full day with "permission" would read as both.
        {"absence_type": "permission"},
        {"decided_status": DayStatus.HALF, "absence_type": "office_duty"},
        # And only the kinds there are.
        {"decided_status": DayStatus.ABSENT, "absence_type": "sick"},
        # Only what a person may decide: never the shop's calendar, nor "still to decide", nor a status there isn't.
        # The whole-or-none rule refuses these too; PostgreSQL checks a table's rules in the order of their names, so
        # it names this one.
        {"decided_status": DayStatus.OFF},
        {"decided_status": DayStatus.NEEDS_REVIEW},
        {"decided_status": "holiday"},
    ],
)
def test_a_decision_fits_what_was_decided(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, changes: dict[str, object]
) -> None:
    # A decision the pay would read wrong (WAGE-2): a paid absence with no kind, a full day with a fine, or a status
    # nobody may decide.
    with pytest.raises(IntegrityError, match="decision_fits_its_status"), transaction.atomic():
        _decided(shop_a, staff_a, staff_a2, **changes).save()


def test_each_decision_saves_beside_what_the_book_said(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # The six choices of the sheet (ATT-6), as decide_day writes them: a full day; late with the first fine, or with
    # none as a shop starts with (ATT-2); half with a late arrival's fine; absent with each of its three kinds. Each
    # keeps the book's own answer beside it, needs review with no Toka, which the decision never changes (A2).
    decisions: list[dict[str, object]] = [
        {},
        {"decided_status": DayStatus.LATE, "decided_fine": Decimal("500.00")},
        {"decided_status": DayStatus.LATE, "decided_fine": Decimal("0.00")},
        {"decided_status": DayStatus.HALF, "decided_fine": Decimal("500.00")},
        {"decided_status": DayStatus.ABSENT, "absence_type": "office_duty"},
        {"decided_status": DayStatus.ABSENT, "absence_type": "permission"},
        {"decided_status": DayStatus.ABSENT, "absence_type": "no_show"},
    ]
    for offset, changes in enumerate(decisions):
        _decided(shop_a, staff_a, staff_a2, date=MONDAY + dt.timedelta(days=offset), **changes).save()
    with shop_context(shop_a):
        kept = list(AttendanceDay.objects.order_by("date"))
    assert [day.decided_status for day in kept] == ["on_time", "late", "late", "half", "absent", "absent", "absent"]
    assert {(day.status, day.review_reason) for day in kept} == {(DayStatus.NEEDS_REVIEW, ReviewReason.NO_OUT)}


def test_a_day_with_no_decision_keeps_its_parts_empty(shop_a: Shop, staff_a: StaffMember) -> None:
    # The book writes a day with no decision, as every day already kept has after the migration: all six parts empty.
    row = _day(shop_a, staff_a)
    row.save()
    with shop_context(shop_a):
        kept = AttendanceDay.objects.get(pk=row.pk)
    assert (kept.decided_status, kept.absence_type, kept.decision_reason) == ("", "", "")
    assert (kept.decided_fine, kept.decided_by_id, kept.decided_at) == (None, None, None)


# The book's work (work_out_days). Arusha's clock, as the shop's: a minute here is what the counter showed.
ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")
TUESDAY = MONDAY + dt.timedelta(days=1)
# The Friday and Sunday before it: days already past, as the book keeps only days that are over.
FRIDAY = MONDAY - dt.timedelta(days=3)
SUNDAY = MONDAY - dt.timedelta(days=1)
JAN_1 = dt.date(2026, 1, 1)
# Each tap's number on the laptop, one after another, as a laptop numbers its records (SYNC-4).
_numbers = itertools.count(1)


def at(day: dt.date, hour: int, minute: int, second: int = 0) -> dt.datetime:
    # A moment on the shop's clock: at(MONDAY, 7, 50) is 07:50 in Arusha, 04:50 in UTC.
    return dt.datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ARUSHA)


def _worker(shop: Shop, name: str, started_on: dt.date = JAN_1) -> StaffMember:
    # A worker whose first day was long ago, unless a test says otherwise, so every day these tests read is one of
    # theirs. Made the way the app makes one: create_user, then the people service, inside the shop (PPL-2).
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, started_on=started_on, by=None)


def _setting(shop: Shop, key: SettingKey[Any], value: Any, effective_from: dt.date) -> None:
    # A rule of the shop's, from a day: checked, then saved as set_setting saves one, with no line and on any day
    # (test_get_setting.py writes its rows so), as these tests need rules for days gone by. Written by the key's own
    # kind, as the settings store it ("500.00", "true").
    with shop_context(shop):
        row = Setting(shop=shop, key=key.key, value=key.kind.to_text(value), effective_from=effective_from)
        row.full_clean()
        row.save()


@pytest.fixture
def attendance_on(shop_a: Shop) -> None:
    # The owner switched attendance on long ago (ADR-0033), so every day these tests read counts.
    _setting(shop_a, ATTENDANCE_ON, True, JAN_1)


@pytest.fixture
def asha(shop_a: Shop, attendance_on: None) -> StaffMember:
    return _worker(shop_a, "Asha")


@pytest.fixture
def juma(shop_a: Shop, attendance_on: None) -> StaffMember:
    return _worker(shop_a, "Juma")


def tap(
    device: Device,
    staff: StaffMember,
    kind: ClockKind,
    moment: dt.datetime,
    *,
    check: TimeCheck = TimeCheck.DEVICE_OK,
    server_time: dt.datetime | None = None,
    **changes: object,
) -> AttendanceEvent:
    # One tap kept in the attendance book, as the clock document keeps one (ATT-1): `moment` by the laptop's clock.
    # device_ok: sent later, its time the laptop's. server: sent at once, its time the server's (`server_time`), and
    # the laptop's clock off by the difference. unverified: no time trusted.
    trusted = {TimeCheck.DEVICE_OK: moment, TimeCheck.SERVER: server_time, TimeCheck.UNVERIFIED: None}[check]
    facts: dict[str, object] = {
        "shop_id": device.shop_id,
        "device": device,
        "device_seq": next(_numbers),
        "client_time": moment,
        "received_at": moment + dt.timedelta(hours=1),
        "created_by": staff,
        "staff": staff,
        "kind": kind,
        "trusted_time": trusted,
        "time_check": check,
        "last_server_time": moment - dt.timedelta(minutes=30),
        "clock_error": moment - server_time if server_time is not None else dt.timedelta(0),
        "no_photo": "demo",
    }
    facts.update(changes)
    event = AttendanceEvent(**facts)
    event.save()
    return event


def _rule(shop: Shop, value: str, effective_from: dt.date) -> None:
    # The owner's first fine, from a day.
    _setting(shop, LATE_FINE, Decimal(value), effective_from)


def _days(shop: Shop, first: dt.date, last: dt.date) -> dict[tuple[str, dt.date], AttendanceDay]:
    # The book's answer for the span, by the worker's nickname and the date, to read a day by its two facts.
    with shop_context(shop):
        return {(day.staff.display_name, day.date): day for day in work_out_days(shop, first, last)}


def test_a_day_is_kept_with_its_rules(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha in at 07:50, out at 18:45, with a first fine of 500: late, the fine taken off, and the rules the day read
    # kept with it as text (T4), so a fine raised later leaves her Monday as it was.
    _rule(shop_a, "500.00", JAN_1)
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    day = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    with shop_context(shop_a):
        kept = AttendanceDay.objects.get(pk=day.pk)
    assert (kept.staff_id, kept.date, kept.status) == (asha.pk, MONDAY, DayStatus.LATE)
    assert kept.fine == Decimal("500.00")
    assert (kept.first_in, kept.first_out) == (dt.time(7, 50), dt.time(18, 45))
    assert kept.rules_used["late_fine"] == "500.00"
    assert kept.rules_used["on_time_until"] == "07:35"
    assert kept.created_by_id is None


def test_a_day_with_no_taps_is_absent(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # Every job gets its day: Juma, who never tapped, is absent, beside Asha, who came.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    days = _days(shop_a, MONDAY, MONDAY)
    assert days[("Asha", MONDAY)].status == DayStatus.ON_TIME
    assert days[("Juma", MONDAY)].status == DayStatus.ABSENT
    assert (days[("Juma", MONDAY)].first_in, days[("Juma", MONDAY)].fine) == (None, Decimal("0.00"))


def test_a_voided_tap_counts_for_nothing(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # Asha's Ingia at 07:20 was voided (T2): its day starts at her next one, 07:50, late. A voided tap is a fact kept,
    # never a tap counted.
    tap(
        device_a,
        asha,
        ClockKind.IN,
        at(MONDAY, 7, 20),
        voided_at=at(MONDAY, 9, 0),
        voided_by=juma,
        void_reason="Si yake",
    )
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    day = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    assert (day.status, day.first_in) == (DayStatus.LATE, dt.time(7, 50))


def test_a_day_reads_the_trusted_time(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha's laptop clock was 30 minutes slow: it showed 07:20 as she tapped at 07:50, and sent at once, so the server's
    # time is the one trusted (ATT-1). Her day reads 07:50, late, never the laptop's 07:20, on time.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20), check=TimeCheck.SERVER, server_time=at(MONDAY, 7, 50))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    day = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    assert (day.status, day.first_in) == (DayStatus.LATE, dt.time(7, 50))


def test_a_tap_falls_on_the_shops_date(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # A day runs from the shop's midnight to the next, not UTC's: a tap at 21:30 UTC on Monday is 00:30 on Tuesday in
    # Arusha, so it is Tuesday's; one at 00:00 on Monday, 21:00 UTC on Sunday, is Monday's. Monday reads 00:00 to 18:45,
    # and its seconds are dropped as the counter drops them: 18:45:59 is 18:45.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 0, 0))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45, 59))
    tap(device_a, asha, ClockKind.IN, dt.datetime(2026, 11, 16, 21, 30, tzinfo=dt.UTC))
    days = _days(shop_a, MONDAY, TUESDAY)
    assert (days[("Asha", MONDAY)].first_in, days[("Asha", MONDAY)].first_out) == (dt.time(0, 0), dt.time(18, 45))
    assert days[("Asha", MONDAY)].status == DayStatus.ON_TIME
    # Tuesday: an Ingia at 00:30 and no Toka, for a manager to decide.
    assert days[("Asha", TUESDAY)].first_in == dt.time(0, 30)
    assert days[("Asha", TUESDAY)].status == DayStatus.NEEDS_REVIEW


def test_an_unverified_tap_needs_review(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha's Ingia came from a laptop whose clock moved: no time is trusted (ATT-1), so no window can be read, and her
    # day goes to a manager, with no fine, whatever her Toka says. The Toka, trusted, is kept beside it.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20), check=TimeCheck.UNVERIFIED)
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    day = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    assert (day.status, day.fine) == (DayStatus.NEEDS_REVIEW, Decimal("0.00"))
    assert (day.first_in, day.first_out) == (None, dt.time(18, 45))
    assert day.review_reason == ReviewReason.TIME_UNKNOWN


def test_an_unverified_tap_falls_on_its_laptops_date(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # A tap with no trusted time has only the laptop's: its Monday, by the shop's clock, so the manager finds it on
    # Monday, and Tuesday holds nothing of it.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20), check=TimeCheck.UNVERIFIED)
    days = _days(shop_a, MONDAY, TUESDAY)
    assert days[("Asha", MONDAY)].status == DayStatus.NEEDS_REVIEW
    assert days[("Asha", TUESDAY)].status == DayStatus.ABSENT


def test_a_day_follows_a_rule_changed_later(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # A safety net. The settings page never starts a rule on a day gone by (setting.date_past, SHOP-3), and the book
    # keeps only days gone by, so the app can't do this today. But the book reads the rules as they stand each time it
    # runs, never its own copy, so a row for a past day, here written past the service, is followed: Asha's Monday,
    # late with no fine, as a shop starts with none (ATT-2), takes a first fine of 500 from 1 November, and the edit
    # history keeps the change (ADR-0036), from 0.00 to 500.00.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    before = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    assert (before.status, before.fine) == (DayStatus.LATE, Decimal("0.00"))
    _rule(shop_a, "500.00", dt.date(2026, 11, 1))
    after = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    assert after.pk == before.pk
    assert (after.fine, after.rules_used["late_fine"]) == (Decimal("500.00"), "500.00")
    with shop_context(shop_a):
        edits = list(EditEvent.objects.filter(subject_type="attendance_day", subject_id=before.pk))
    assert [(edit.before["fine"], edit.after["fine"]) for edit in edits] == [("0.00", "500.00")]


def test_a_day_follows_a_tap_that_came_late(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha's Toka sat on a laptop that was offline: her Monday has only her Ingia, for a manager. Her Toka arrives the
    # next day, and her Monday, worked out again, is on time.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    assert _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)].status == DayStatus.NEEDS_REVIEW
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    assert _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)].status == DayStatus.ON_TIME


def test_the_book_never_writes_over_a_decision(
    shop_a: Shop,
    device_a: Device,
    asha: StaffMember,
    give_role: Callable[[StaffMember, RoleTemplate, Side | None], None],
) -> None:
    # Asha's Monday waits with no Toka, and Baba decides it a half day (ATT-6). Her Toka then arrives from a laptop
    # that was offline: the book works the day out again, on time, and writes only what it works out (WORKED_OUT), so
    # Baba's decision stays as he made it, beside the book's new answer (A2).
    baba = _worker(shop_a, "Baba")
    give_role(baba, RoleTemplate.OWNER, None)
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    monday = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    with shop_context(shop_a):
        decide_day(monday, choice=DayChoice.HALF, reason="Aliondoka mchana", replaces=None, by=baba)
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    again = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    assert (again.status, again.review_reason) == (DayStatus.ON_TIME, "")
    assert (again.decided_status, again.decided_by_id, again.decision_reason) == (
        DayStatus.HALF,
        baba.pk,
        "Aliondoka mchana",
    )


def test_the_book_writes_as_nobody(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # Juma, a manager, opens the month in his visit, from the Dawa laptop: Asha's Monday changes, as her Toka came late,
    # and the edit history says the system changed it, from no device, never Juma (ADR-0036). His visit's note is his
    # again after the book: a row he changes himself still names him.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    with shop_context(shop_a), acting_as(juma, device=device_a):
        monday = work_out_days(shop_a, MONDAY, MONDAY)[0]
        tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
        work_out_days(shop_a, MONDAY, MONDAY)
        edit = EditEvent.objects.get(subject_type="attendance_day", subject_id=monday.pk)
        assert (edit.before["status"], edit.after["status"]) == (DayStatus.NEEDS_REVIEW, DayStatus.ON_TIME)
        assert (edit.created_by_id, edit.device_id) == (None, None)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('mpc.staff_id', true)")
            assert cursor.fetchone() == (str(juma.pk),)


def test_a_day_that_comes_out_the_same_is_not_written_again(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # A month asked for twice, as ATT-5 asks for it each time a manager opens it: the second time nothing has changed,
    # so the book writes nothing, and answers the rows it kept.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    first = _days(shop_a, MONDAY, TUESDAY)
    with CaptureQueriesContext(connection) as queries:
        second = _days(shop_a, MONDAY, TUESDAY)
    writes = [query["sql"] for query in queries if query["sql"].startswith(("INSERT", "UPDATE"))]
    assert writes == []
    assert {key: day.pk for key, day in second.items()} == {key: day.pk for key, day in first.items()}


def test_a_month_is_read_in_a_few_queries(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # The month page opens November (ATT-5): the book reads the jobs, the taps, the days kept, the closed days, the
    # switch and the rules once each for the whole month, and writes its new days in one go. However many days and
    # workers, the count stays small: never a read per day or per worker.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        days = work_out_days(shop_a, dt.date(2026, 10, 1), dt.date(2026, 10, 31))
    assert len(days) == 2 * 31
    assert len(queries) <= 12


def test_each_day_comes_with_its_worker(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # The month page names each day's worker (ATT-5). A month asked for again answers the days as kept, and each comes
    # with its job, so reading every worker's name takes no query at all.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    with shop_context(shop_a):
        work_out_days(shop_a, MONDAY, TUESDAY)
        again = work_out_days(shop_a, MONDAY, TUESDAY)
        with CaptureQueriesContext(connection) as queries:
            names = sorted(day.staff.display_name for day in again)
    assert names == ["Asha", "Asha", "Juma", "Juma"]
    assert len(queries) == 0


def test_working_out_twice_keeps_one_row(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # A month asked for again, by the next manager to open it: each job keeps one row per date, under its first id.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    first = _days(shop_a, MONDAY, TUESDAY)
    again = _days(shop_a, MONDAY, TUESDAY)
    with shop_context(shop_a):
        assert AttendanceDay.objects.count() == 4
    assert {key: day.pk for key, day in again.items()} == {key: day.pk for key, day in first.items()}


def _statuses_in_another_run(shop: Shop, day: dt.date) -> dict[str, str]:
    # The book run in its own transaction, as a second manager's visit would run it, on its own connection: its answer,
    # as the nickname and the status of each day, plain values the test reads once the thread has ended.
    with shop_context(shop):
        return {row.staff.display_name: row.status for row in work_out_days(shop, day, day)}


@pytest.mark.django_db(transaction=True)
def test_a_second_run_waits_for_the_first(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Two managers open November at once. The first run holds the shop's jobs, and meanwhile Asha's Toka arrives from
    # a laptop that was offline. The second run must wait for the first to commit, then read the taps as they are
    # then: her Toka is there, so her Monday is on time, never the first run's older "needs review". Here the test
    # holds the jobs' lock itself, as the first run would, so it can let the Toka in before it lets the second run go.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    with shop_context(shop_a), transaction.atomic():
        list(StaffMember.objects.filter(shop=shop_a).order_by("pk").select_for_update(no_key=True))
        second, ended = in_another_transaction(lambda: _statuses_in_another_run(shop_a, MONDAY))
        # The second run truly waits on the lock: without it, this fails, as nobody ever waits.
        wait_until_someone_waits_for_me()
        tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    second.join(timeout=10)
    assert ended == [{"Asha": DayStatus.ON_TIME}]


def test_two_jobs_on_one_day_read_their_own_taps(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Baraka leaves on Monday and is hired again the same day (PPL-11): two jobs, and a day each. He tapped Ingia on his
    # old job and Toka on his new one, so each job has half a day's taps, and each day goes to a manager: never a full
    # day paid twice, nor one made of two jobs' taps.
    old = _worker(shop_a, "Baraka")
    tap(device_a, old, ClockKind.IN, at(MONDAY, 7, 20))
    with shop_context(shop_a):
        mark_left(old, left_on=MONDAY, by=None, reason="Ameacha kazi")
        old.refresh_from_db()
        new = hire_again(old, display_name="Baraka", started_on=MONDAY, by=None)
    tap(device_a, new, ClockKind.OUT, at(MONDAY, 18, 45))
    with shop_context(shop_a):
        days = {day.staff_id: day for day in work_out_days(shop_a, MONDAY, MONDAY)}
    assert (days[old.pk].status, days[old.pk].first_in, days[old.pk].first_out) == (
        DayStatus.NEEDS_REVIEW,
        dt.time(7, 20),
        None,
    )
    assert (days[new.pk].status, days[new.pk].first_in, days[new.pk].first_out) == (
        DayStatus.NEEDS_REVIEW,
        None,
        dt.time(18, 45),
    )


def test_the_nights_job_keeps_another_shops_workers_out(
    shop_a: Shop, shop_b: Shop, device_a: Device, side_b: Side, asha: StaffMember
) -> None:
    # The night's job opens every shop at once (system_context, ATT-7), so the guard shows every shop's rows, and only
    # the book's own `shop=` keeps shop B out (T1). Bahati works at shop B and clocked in on Monday on B's laptop: shop
    # A's book answers Asha alone, and keeps no day for Bahati, under either shop.
    with shop_context(shop_b):
        laptop_b = Device.objects.create(
            shop=shop_b, home_side=side_b, name="Laptop ya Pembejeo", code=1, key_hash="b" * 64
        )
    bahati = _worker(shop_b, "Bahati")
    tap(laptop_b, bahati, ClockKind.IN, at(MONDAY, 7, 20))
    tap(laptop_b, bahati, ClockKind.OUT, at(MONDAY, 18, 45))
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    with system_context():
        days = work_out_days(shop_a, MONDAY, MONDAY)
        assert [(day.staff_id, day.status) for day in days] == [(asha.pk, DayStatus.LATE)]
        assert not AttendanceDay.objects.filter(staff=bahati).exists()
        assert not AttendanceDay.objects.filter(shop=shop_b).exists()


def test_work_out_days_refuses_a_moment_or_another_shop(shop_a: Shop, shop_b: Shop) -> None:
    # A datetime is a moment, not the shop's day; and another shop than the one open would read its taps through the
    # wrong guard. Both are bugs in the calling code, so both fail loudly, as get_setting and closed_days do.
    with shop_context(shop_a):
        with pytest.raises(TypeError):
            work_out_days(shop_a, at(MONDAY, 0, 0), MONDAY)
        with pytest.raises(ShopMismatch):
            work_out_days(shop_b, MONDAY, MONDAY)


def _closure(shop: Shop, first: dt.date, last: dt.date) -> None:
    # Days the shop is closed: checked, then saved, as the closure tests make them (test_closures.py), on days already
    # past, which the service refuses (ATT-8): these tests read days gone by.
    with shop_context(shop):
        row = Closure(shop=shop, first_day=first, last_day=last, name="Msiba wa bibi")
        row.full_clean()
        row.save()


def test_sunday_is_off(shop_a: Shop, asha: StaffMember) -> None:
    # The shop is shut on Sunday, so nobody comes and nobody is paid (01 §8.1): off, not absent, with no fine and no
    # rule read. Monday after it is a working day, absent with no tap.
    days = _days(shop_a, SUNDAY, MONDAY)
    sunday = days[("Asha", SUNDAY)]
    assert (sunday.status, sunday.fine, sunday.rules_used) == (DayStatus.OFF, Decimal("0.00"), {})
    assert days[("Asha", MONDAY)].status == DayStatus.ABSENT


def test_a_sunday_tap_is_still_off(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha came in on Sunday and tapped: Sunday work is a deal between the owner and the worker, outside the system
    # (01 §8.1), so her Sunday stays off, and her taps stay in the attendance book for anyone to see.
    tap(device_a, asha, ClockKind.IN, at(SUNDAY, 7, 20))
    tap(device_a, asha, ClockKind.OUT, at(SUNDAY, 18, 45))
    sunday = _days(shop_a, SUNDAY, SUNDAY)[("Asha", SUNDAY)]
    assert (sunday.status, sunday.first_in, sunday.first_out) == (DayStatus.OFF, None, None)


def test_a_closed_day_is_off(shop_a: Shop, asha: StaffMember) -> None:
    # The shop closes on Friday for a funeral (ATT-8): off, and not paid, like Sunday. Thursday before it is a working
    # day.
    _closure(shop_a, FRIDAY, FRIDAY)
    days = _days(shop_a, FRIDAY - dt.timedelta(days=1), FRIDAY)
    assert (days[("Asha", FRIDAY)].status, days[("Asha", FRIDAY)].rules_used) == (DayStatus.OFF, {})
    assert days[("Asha", FRIDAY - dt.timedelta(days=1))].status == DayStatus.ABSENT


def test_a_tap_on_a_closed_day_needs_review(
    shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember
) -> None:
    # The owner closes the shop at 10:00 on Friday for a funeral; Asha had clocked in at 07:20 and out at 10:05. Whether
    # her morning is paid is the owner's or a manager's to decide (Jack, ATT-10): her day needs review, with no fine,
    # her taps' minutes and the day's rules kept for whoever decides. Juma came all the same, 07:50 to 18:45: the rule
    # alone would call his day late, less 500, but a closed day takes no fine until someone decides it.
    _rule(shop_a, "500.00", JAN_1)
    _closure(shop_a, FRIDAY, FRIDAY)
    tap(device_a, asha, ClockKind.IN, at(FRIDAY, 7, 20))
    tap(device_a, asha, ClockKind.OUT, at(FRIDAY, 10, 5))
    tap(device_a, juma, ClockKind.IN, at(FRIDAY, 7, 50))
    tap(device_a, juma, ClockKind.OUT, at(FRIDAY, 18, 45))
    days = _days(shop_a, FRIDAY, FRIDAY)
    asha_friday, juma_friday = days[("Asha", FRIDAY)], days[("Juma", FRIDAY)]
    assert (asha_friday.status, asha_friday.fine) == (DayStatus.NEEDS_REVIEW, Decimal("0.00"))
    assert (asha_friday.first_in, asha_friday.first_out) == (dt.time(7, 20), dt.time(10, 5))
    assert asha_friday.rules_used["late_fine"] == "500.00"
    assert (juma_friday.status, juma_friday.fine) == (DayStatus.NEEDS_REVIEW, Decimal("0.00"))
    assert (juma_friday.first_in, juma_friday.first_out) == (dt.time(7, 50), dt.time(18, 45))
    # Why, for both: the shop was closed. Asha's left before midday too, but the closure is what to decide.
    assert asha_friday.review_reason == juma_friday.review_reason == ReviewReason.CLOSED_DAY


# Which days count. A week of November long past: Monday 9 to Friday 13.
NOV_9, NOV_10, NOV_11, NOV_12, NOV_13 = (dt.date(2026, 11, n) for n in (9, 10, 11, 12, 13))


def test_no_day_before_attendance_is_on(shop_a: Shop) -> None:
    # The owner switches attendance on from Tuesday 10th, and off again from Thursday 12th (ADR-0033): only Tuesday and
    # Wednesday count. Before the switch, nobody clocked in, so a day kept then would be an absence that never was;
    # the book keeps no day at all, not even an off one.
    _setting(shop_a, ATTENDANCE_ON, True, NOV_10)
    _setting(shop_a, ATTENDANCE_ON, False, NOV_12)
    _worker(shop_a, "Asha")
    days = _days(shop_a, NOV_9, NOV_13)
    assert sorted(date for _, date in days) == [NOV_10, NOV_11]
    with shop_context(shop_a):
        assert AttendanceDay.objects.count() == 2


def test_no_day_before_the_first_day_or_after_the_last(shop_a: Shop, attendance_on: None) -> None:
    # Neema's first day was Tuesday 10th, and she left on Thursday 12th: her days are those three, both ends counted.
    # Monday is before her job, and Friday after it, so neither is an absence of hers.
    neema = _worker(shop_a, "Neema", started_on=NOV_10)
    with shop_context(shop_a):
        mark_left(neema, left_on=NOV_12, by=None, reason="Amehamia mji mwingine")
    days = _days(shop_a, NOV_9, NOV_13)
    assert sorted(date for _, date in days) == [NOV_10, NOV_11, NOV_12]


def test_today_is_not_kept(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha clocked in this morning and hasn't tapped Toka yet: her day isn't over, and the rule would send it to a
    # manager. So a span reaching today stops at yesterday, and a span of today or later keeps nothing.
    today = shop_today(shop_a)
    tap(device_a, asha, ClockKind.IN, dt.datetime.combine(today, dt.time(7, 20), tzinfo=ARUSHA))
    yesterday = today - dt.timedelta(days=1)
    assert sorted(date for _, date in _days(shop_a, yesterday, today + dt.timedelta(days=1))) == [yesterday]
    assert _days(shop_a, today, today) == {}
    with shop_context(shop_a):
        assert not AttendanceDay.objects.filter(date__gte=today).exists()


def test_today_is_the_shops_today_not_utcs(
    shop_a: Shop, device_a: Device, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 21:30 UTC on Monday is already 00:30 on Tuesday in Arusha: Monday is over in the shop, though not in UTC. So the
    # book keeps Monday, and a book that read today by the server's UTC clock would keep nothing. The clock is fixed
    # there, so the test catches that at any hour it runs, not only in the three hours a day UTC is behind.
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 16, 21, 30, tzinfo=dt.UTC))
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    days = _days(shop_a, MONDAY, TUESDAY)
    assert sorted(date for _, date in days) == [MONDAY]
    assert days[("Asha", MONDAY)].status == DayStatus.ON_TIME


def test_a_day_no_longer_counted_is_not_answered(shop_a: Shop, attendance_on: None) -> None:
    # Neema was added with her first day on Monday 9th, and her days were kept. Then a manager fixes it to Wednesday
    # 11th, the day she really started (PPL-10): worked out again, Monday and Tuesday are no longer hers to answer.
    # Their rows stay, as nothing is deleted (rule 7), counted nowhere: she tapped on neither, or each would need
    # review (ATT-11, test_a_tap_before_the_first_day_needs_review).
    neema = _worker(shop_a, "Neema", started_on=NOV_9)
    assert len(_days(shop_a, NOV_9, NOV_13)) == 5
    with shop_context(shop_a):
        change_worker(neema, version=neema.version, reason="Alianza Jumatano", by=None, started_on=NOV_11)
    days = _days(shop_a, NOV_9, NOV_13)
    assert sorted(date for _, date in days) == [NOV_11, NOV_12, NOV_13]
    with shop_context(shop_a):
        assert AttendanceDay.objects.count() == 5


# The flagged taps (ATT-11): taps the book can't take as they are, each sending its day to a manager or the owner.


def _line_of(event: AttendanceEvent) -> ShopScoped:
    # The tap's line in the answer log, as the push writes it: its document_id is the event's own id, as
    # test_suspended_worker_clock_in_flagged (apps/sync/tests/test_clock_in.py) finds the push keeps it. The answer log
    # is a table of `sync`, a layer above `staffpay`, so it is named by its link code, never imported (ADR-0043), as the
    # book reads it; Any, as the type checker can't know the columns of a table it may not import.
    answer_log = cast(Any, table_of("pushed_document"))
    with shop_context(event.shop_id):
        return cast(
            ShopScoped,
            answer_log.objects.create(
                shop_id=event.shop_id,
                device=event.device,
                device_seq=event.device_seq,
                client_time=event.client_time,
                received_at=event.received_at,
                created_by=event.created_by,
                document_id=event.pk,
                type="clock",
                schema_version=2,
                status="accepted",
            ),
        )


def _flag_its_line(event: AttendanceEvent) -> Flag:
    # A flag about the tap's line, as the push raises one when the tap's maker wasn't working (SYNC-5, X2).
    line = _line_of(event)
    with shop_context(event.shop_id):
        return raise_flag(kind=FlagKind.SUSPENDED_STAFF_ACTIVITY, subject=line, people=[event.staff], by=None)


def test_a_suspended_workers_tap_needs_review(
    shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember
) -> None:
    # Baba suspends Juma on Monday at 11:00. The Dawa laptop is offline and doesn't know, so on Tuesday its PIN check
    # lets him in, at 07:20, out at 18:45. The push flags his Ingia on its line (X2), and his Tuesday needs review: the
    # owner or a manager decides whether it is paid. Asha, on time beside him, is not touched.
    ingia = tap(device_a, juma, ClockKind.IN, at(TUESDAY, 7, 20))
    tap(device_a, juma, ClockKind.OUT, at(TUESDAY, 18, 45))
    tap(device_a, asha, ClockKind.IN, at(TUESDAY, 7, 20))
    tap(device_a, asha, ClockKind.OUT, at(TUESDAY, 18, 45))
    _flag_its_line(ingia)
    days = _days(shop_a, TUESDAY, TUESDAY)
    assert days[("Juma", TUESDAY)].status == DayStatus.NEEDS_REVIEW
    assert days[("Juma", TUESDAY)].review_reason == ReviewReason.NOT_WORKING
    assert days[("Asha", TUESDAY)].status == DayStatus.ON_TIME


def test_a_gone_workers_tap_needs_review(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Neema's last day is Monday, and the owner records her leaving at 10:00 that morning: her PIN stops at once. The
    # laptop, offline, lets her Toka through at 18:45, and the push flags it, as leaving counts as a suspension does
    # (Jack, SYNC-5). Her Monday is still one of her days, but not one to pay unchecked.
    neema = _worker(shop_a, "Neema")
    tap(device_a, neema, ClockKind.IN, at(MONDAY, 7, 20))
    toka = tap(device_a, neema, ClockKind.OUT, at(MONDAY, 18, 45))
    with shop_context(shop_a):
        mark_left(neema, left_on=MONDAY, by=None, reason="Amehamia mji mwingine")
    _flag_its_line(toka)
    monday = _days(shop_a, MONDAY, MONDAY)[("Neema", MONDAY)]
    assert (monday.status, monday.review_reason) == (DayStatus.NEEDS_REVIEW, ReviewReason.NOT_WORKING)


def test_a_closed_suspension_flag_still_needs_review(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, juma: StaffMember
) -> None:
    # A manager looks at Juma's flag and closes it: "Baba let him back on Tuesday morning". The flag is about the tap,
    # not the day: deciding whether his Tuesday is paid is ATT-6's override, so the day still needs review.
    ingia = tap(device_a, juma, ClockKind.IN, at(TUESDAY, 7, 20))
    tap(device_a, juma, ClockKind.OUT, at(TUESDAY, 18, 45))
    flag = _flag_its_line(ingia)
    with shop_context(shop_a):
        dismiss_flag(flag, text="Baba alimrudisha Jumanne asubuhi", by=staff_a)
    assert _days(shop_a, TUESDAY, TUESDAY)[("Juma", TUESDAY)].status == DayStatus.NEEDS_REVIEW


def test_another_flag_on_the_line_sends_nothing(shop_a: Shop, device_a: Device, juma: StaffMember) -> None:
    # Juma's Ingia came with a number the laptop skipped before it: a device_gap flag about its line, a record still
    # missing. That says nothing of whether Juma came, so his Tuesday is on time.
    ingia = tap(device_a, juma, ClockKind.IN, at(TUESDAY, 7, 20))
    tap(device_a, juma, ClockKind.OUT, at(TUESDAY, 18, 45))
    line = _line_of(ingia)
    with shop_context(shop_a):
        raise_flag(kind=FlagKind.DEVICE_GAP, subject=line, expected=Decimal(1), actual=Decimal(3), by=None)
    assert _days(shop_a, TUESDAY, TUESDAY)[("Juma", TUESDAY)].status == DayStatus.ON_TIME


def test_a_voided_flagged_tap_sends_nothing(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, juma: StaffMember
) -> None:
    # Juma's flagged Ingia is voided by a manager (T2, ATT-13): a voided tap counts for nothing, so it sends nothing
    # either. With no tap left, his Tuesday is absent.
    ingia = tap(
        device_a,
        juma,
        ClockKind.IN,
        at(TUESDAY, 7, 20),
        voided_at=at(TUESDAY, 9, 0),
        voided_by=staff_a,
        void_reason="Alikuwa amesimamishwa",
    )
    _flag_its_line(ingia)
    assert _days(shop_a, TUESDAY, TUESDAY)[("Juma", TUESDAY)].status == DayStatus.ABSENT


def test_a_day_in_doubt_keeps_its_minutes_and_rules(shop_a: Shop, device_a: Device, juma: StaffMember) -> None:
    # Juma, suspended, came at 07:50 and left at 18:45. The rule alone would call his Tuesday late, less 500; sent to
    # review, it takes no fine until someone decides it, and keeps his minutes and the day's rules for whoever does,
    # as a closed day with a tap does (ATT-10).
    _rule(shop_a, "500.00", JAN_1)
    ingia = tap(device_a, juma, ClockKind.IN, at(TUESDAY, 7, 50))
    tap(device_a, juma, ClockKind.OUT, at(TUESDAY, 18, 45))
    _flag_its_line(ingia)
    day = _days(shop_a, TUESDAY, TUESDAY)[("Juma", TUESDAY)]
    assert (day.status, day.fine) == (DayStatus.NEEDS_REVIEW, Decimal("0.00"))
    assert (day.first_in, day.first_out) == (dt.time(7, 50), dt.time(18, 45))
    assert day.rules_used["late_fine"] == "500.00"


def test_the_tap_a_later_one_disagrees_with_needs_review(
    shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember
) -> None:
    # The Dawa laptop's clock goes wrong. Juma's Toka says 18:45, then Asha's, the record after it, says 18:30: one of
    # the two times is wrong, and nobody knows which. Hers has no trusted time, so her day needs review (ATT-4); his
    # keeps the laptop's, and alone would be a full day. Her tap keeps his id (`disagrees_with`, ATT-11), so his Monday
    # needs review too (Jack: A), with his minutes kept for whoever decides.
    tap(device_a, juma, ClockKind.IN, at(MONDAY, 7, 20))
    jumas_toka = tap(device_a, juma, ClockKind.OUT, at(MONDAY, 18, 45))
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 30), check=TimeCheck.UNVERIFIED, disagrees_with=jumas_toka.pk)
    days = _days(shop_a, MONDAY, MONDAY)
    jumas_monday = days[("Juma", MONDAY)]
    assert (jumas_monday.status, jumas_monday.fine) == (DayStatus.NEEDS_REVIEW, Decimal("0.00"))
    assert (jumas_monday.first_in, jumas_monday.first_out) == (dt.time(7, 20), dt.time(18, 45))
    assert days[("Asha", MONDAY)].status == DayStatus.NEEDS_REVIEW
    # Why: his because a later tap's time disagrees with his; hers because her own time can't be trusted.
    assert jumas_monday.review_reason == ReviewReason.CLOCK_DISAGREES
    assert days[("Asha", MONDAY)].review_reason == ReviewReason.TIME_UNKNOWN


def test_a_disagreement_reaches_another_day(
    shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember
) -> None:
    # Juma clocks in on Tuesday at 07:30. Then someone sets the laptop back a day, and Asha's Ingia says Monday 18:50,
    # after his on the laptop's numbers. Her tap falls on Monday, by the laptop's clock, the only time it has; his on
    # Tuesday. So the book, asked for Tuesday alone, still finds the tap that disagrees with his, wherever it fell.
    jumas_ingia = tap(device_a, juma, ClockKind.IN, at(TUESDAY, 7, 30))
    tap(device_a, juma, ClockKind.OUT, at(TUESDAY, 18, 45))
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 18, 50), check=TimeCheck.UNVERIFIED, disagrees_with=jumas_ingia.pk)
    assert _days(shop_a, TUESDAY, TUESDAY)[("Juma", TUESDAY)].status == DayStatus.NEEDS_REVIEW


def test_a_tap_timed_by_the_server_is_not_in_doubt(
    shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember
) -> None:
    # Juma's Toka was sent at once, so its time is the server's, 18:45, whatever the laptop's clock said (ATT-1): it
    # can't be the wrong one. Asha's tap after it says 18:30 by a laptop clock that moved, so hers alone is in doubt,
    # and his Monday is the full day it was.
    tap(device_a, juma, ClockKind.IN, at(MONDAY, 7, 20))
    jumas_toka = tap(
        device_a, juma, ClockKind.OUT, at(MONDAY, 19, 0), check=TimeCheck.SERVER, server_time=at(MONDAY, 18, 45)
    )
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 30), check=TimeCheck.UNVERIFIED, disagrees_with=jumas_toka.pk)
    assert _days(shop_a, MONDAY, MONDAY)[("Juma", MONDAY)].status == DayStatus.ON_TIME


def test_a_voided_tap_disagreed_with_sends_nothing(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, asha: StaffMember, juma: StaffMember
) -> None:
    # Juma's Toka, the one Asha's disagrees with, was a second Toka tapped by mistake, voided by a manager (T2): it
    # counts for nothing, so it sends nothing either. His Monday ends at his first Toka, on time.
    tap(device_a, juma, ClockKind.IN, at(MONDAY, 7, 20))
    tap(device_a, juma, ClockKind.OUT, at(MONDAY, 18, 40))
    second = tap(
        device_a,
        juma,
        ClockKind.OUT,
        at(MONDAY, 18, 45),
        voided_at=at(MONDAY, 19, 0),
        voided_by=staff_a,
        void_reason="Alitoka mara mbili",
    )
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 30), check=TimeCheck.UNVERIFIED, disagrees_with=second.pk)
    assert _days(shop_a, MONDAY, MONDAY)[("Juma", MONDAY)].status == DayStatus.ON_TIME


def test_another_shops_taps_never_send_this_shops_day(
    shop_a: Shop, shop_b: Shop, device_a: Device, side_b: Side, asha: StaffMember
) -> None:
    # Shop B's laptop sends a document whose id is Asha's Ingia at shop A: it is set aside (`id.taken`, 03 §5.4) and
    # keeps a line in B's answer log all the same, named by that id. B's push could flag that line, and B's next
    # clock-in, its time earlier, keeps that id as the record it disagrees with. The night's job opens every shop at
    # once (system_context, ATT-7), so the guard filters nothing, and only the book's own `shop=` keeps B's line, its
    # flag and its tap away from Asha's day (T1). Her Monday stays on time.
    with shop_context(shop_b):
        laptop_b = Device.objects.create(
            shop=shop_b, home_side=side_b, name="Laptop ya Pembejeo", code=1, key_hash="b" * 64
        )
    bahati = _worker(shop_b, "Bahati")
    ingia = tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    tap(device_a, asha, ClockKind.OUT, at(MONDAY, 18, 45))
    answer_log = cast(Any, table_of("pushed_document"))
    with shop_context(shop_b):
        line_b = answer_log.objects.create(
            shop_id=shop_b.pk,
            device=laptop_b,
            device_seq=1,
            client_time=at(MONDAY, 8, 0),
            received_at=at(MONDAY, 9, 0),
            created_by=None,
            document_id=ingia.pk,
            type="clock",
            schema_version=2,
            status="invalid",
            reason="id.taken",
        )
        raise_flag(kind=FlagKind.SUSPENDED_STAFF_ACTIVITY, subject=line_b, by=None)
    tap(laptop_b, bahati, ClockKind.IN, at(MONDAY, 7, 50), check=TimeCheck.UNVERIFIED, disagrees_with=ingia.pk)
    with system_context():
        days = work_out_days(shop_a, MONDAY, MONDAY)
    assert [(day.staff_id, day.status) for day in days] == [(asha.pk, DayStatus.ON_TIME)]


def _came(device: Device, staff: StaffMember, *days: dt.date) -> None:
    # A full day on each date: in at 07:20, out at 18:45.
    for day in days:
        tap(device, staff, ClockKind.IN, at(day, 7, 20))
        tap(device, staff, ClockKind.OUT, at(day, 18, 45))


def test_a_tap_before_the_first_day_needs_review(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Neema is added with a first day of Tuesday 10th, and comes on the 10th and the 11th. A manager then moves her
    # first day to Thursday 12th (PPL-10): her taps now fall before it. They say she came, her first day says she
    # didn't, so those two days need review (Jack, ATT-11: A): the manager puts her first day back, or decides whether
    # they are paid. Her minutes stay, for whoever decides. Monday 9th, with no tap, is still not one of hers.
    neema = _worker(shop_a, "Neema", started_on=NOV_10)
    _came(device_a, neema, NOV_10, NOV_11)
    with shop_context(shop_a):
        change_worker(neema, version=neema.version, reason="Alianza Alhamisi", by=None, started_on=NOV_12)
    days = _days(shop_a, NOV_9, NOV_13)
    assert {date: day.status for (_, date), day in days.items()} == {
        NOV_10: DayStatus.NEEDS_REVIEW,
        NOV_11: DayStatus.NEEDS_REVIEW,
        NOV_12: DayStatus.ABSENT,
        NOV_13: DayStatus.ABSENT,
    }
    assert (days[("Neema", NOV_10)].first_in, days[("Neema", NOV_10)].fine) == (dt.time(7, 20), Decimal("0.00"))
    assert days[("Neema", NOV_10)].review_reason == days[("Neema", NOV_11)].review_reason == ReviewReason.OUTSIDE_JOB


def test_a_tap_after_the_last_day_needs_review(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Neema's last day is Tuesday 10th, recorded on Thursday: the laptop, offline, still let her clock in on Wednesday.
    # Her tap after her last day is a day to decide, as one before her first is; Thursday, with no tap, is not hers.
    neema = _worker(shop_a, "Neema", started_on=NOV_9)
    _came(device_a, neema, NOV_11)
    with shop_context(shop_a):
        mark_left(neema, left_on=NOV_10, by=None, reason="Amehamia mji mwingine")
    days = _days(shop_a, NOV_9, NOV_12)
    assert {date: day.status for (_, date), day in days.items()} == {
        NOV_9: DayStatus.ABSENT,
        NOV_10: DayStatus.ABSENT,
        NOV_11: DayStatus.NEEDS_REVIEW,
    }
    assert days[("Neema", NOV_11)].review_reason == ReviewReason.OUTSIDE_JOB


def test_a_kept_day_before_a_moved_first_day_turns_to_review(
    shop_a: Shop, device_a: Device, attendance_on: None
) -> None:
    # Neema's Tuesday 10th was kept as on time, then her first day was moved to Thursday 12th. Worked out again, the
    # same row says needs review, and the edit history says so, as the book's own change: never a second row, never a
    # delete (rule 7). Monday 9th, kept as absent with no tap, stays as it was, and is no longer answered (ATT-10).
    neema = _worker(shop_a, "Neema", started_on=NOV_9)
    _came(device_a, neema, NOV_10)
    kept = _days(shop_a, NOV_9, NOV_10)
    assert (kept[("Neema", NOV_9)].status, kept[("Neema", NOV_10)].status) == (DayStatus.ABSENT, DayStatus.ON_TIME)
    with shop_context(shop_a):
        change_worker(neema, version=neema.version, reason="Alianza Alhamisi", by=None, started_on=NOV_12)
    again = _days(shop_a, NOV_9, NOV_10)
    assert list(again) == [("Neema", NOV_10)]
    tuesday = again[("Neema", NOV_10)]
    assert (tuesday.pk, tuesday.status) == (kept[("Neema", NOV_10)].pk, DayStatus.NEEDS_REVIEW)
    with shop_context(shop_a):
        assert AttendanceDay.objects.get(pk=kept[("Neema", NOV_9)].pk).status == DayStatus.ABSENT
        assert AttendanceDay.objects.count() == 2
        change = EditEvent.objects.get(subject_type="attendance_day", subject_id=tuesday.pk)
    assert (change.created_by_id, change.after["status"]) == (None, DayStatus.NEEDS_REVIEW)


def test_a_sunday_tap_in_doubt_is_still_off(
    shop_a: Shop, device_a: Device, attendance_on: None, juma: StaffMember
) -> None:
    # Sunday work is a deal outside the system (01 §8.1), so a Sunday stays off whatever its taps: Juma's, flagged as
    # made while he was suspended, and Neema's, made before a first day moved to Monday, which keeps no Sunday at all.
    ingia = tap(device_a, juma, ClockKind.IN, at(SUNDAY, 7, 20))
    _flag_its_line(ingia)
    neema = _worker(shop_a, "Neema", started_on=SUNDAY - dt.timedelta(days=7))
    _came(device_a, neema, SUNDAY)
    with shop_context(shop_a):
        change_worker(neema, version=neema.version, reason="Alianza Jumatatu", by=None, started_on=MONDAY)
    days = _days(shop_a, SUNDAY, SUNDAY)
    assert days[("Juma", SUNDAY)].status == DayStatus.OFF
    assert ("Neema", SUNDAY) not in days


# Why a day needs a decision (ATT-5): the book keeps one reason beside each day to decide, for the month page, the day's
# page (ATT-12) and whoever decides it (ATT-6). The rule's own reasons are its tests' (test_attendance_day.py).


def test_the_books_reason_comes_first(shop_a: Shop, device_a: Device, juma: StaffMember) -> None:
    # Juma never taps Toka on two days. On Friday the shop was closed for a funeral; on Tuesday Baba had suspended him,
    # and the offline laptop let his Ingia through. A missing Toka is the rule's reason, but what a person must decide
    # first is the book's: whether a closed day, or a suspended worker's day, is paid at all. Closed comes before
    # suspended, as nobody is paid for a closed day whoever came.
    _closure(shop_a, FRIDAY, FRIDAY)
    _flag_its_line(tap(device_a, juma, ClockKind.IN, at(FRIDAY, 7, 20)))
    _flag_its_line(tap(device_a, juma, ClockKind.IN, at(TUESDAY, 7, 20)))
    days = _days(shop_a, FRIDAY, TUESDAY)
    assert days[("Juma", FRIDAY)].review_reason == ReviewReason.CLOSED_DAY
    assert days[("Juma", TUESDAY)].review_reason == ReviewReason.NOT_WORKING


def test_a_day_not_to_decide_keeps_no_reason(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha's Sunday is off, her Monday on time, her Tuesday absent: none is on the list to decide, so none keeps a
    # reason. Her Wednesday, an Ingia and no Toka, keeps "no Toka".
    wednesday = TUESDAY + dt.timedelta(days=1)
    _came(device_a, asha, MONDAY)
    tap(device_a, asha, ClockKind.IN, at(wednesday, 7, 20))
    days = _days(shop_a, SUNDAY, wednesday)
    assert {date: day.review_reason for (_, date), day in days.items()} == {
        SUNDAY: "",
        MONDAY: "",
        TUESDAY: "",
        wednesday: ReviewReason.NO_OUT,
    }


def test_a_day_kept_before_gets_its_reason(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha's Monday, an Ingia and no Toka, was kept before ATT-5, as needing review with no reason: here, kept, then
    # its reason emptied by hand, as the column came empty on every row already there. The next time the book works it
    # out, the same row gets its reason, as a reason is one of the day's answers, and the edit history keeps the change
    # as the book's.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20))
    _days(shop_a, MONDAY, MONDAY)
    with shop_context(shop_a):
        AttendanceDay.objects.filter(staff=asha, date=MONDAY).update(review_reason="")
    again = _days(shop_a, MONDAY, MONDAY)[("Asha", MONDAY)]
    with shop_context(shop_a):
        kept = AttendanceDay.objects.get(staff=asha, date=MONDAY)
        change = EditEvent.objects.filter(subject_type="attendance_day", subject_id=kept.pk).latest("created_at")
    assert (again.pk, kept.review_reason) == (kept.pk, ReviewReason.NO_OUT)
    assert (change.created_by_id, change.after["review_reason"]) == (None, ReviewReason.NO_OUT)


def test_outside_the_jobs_days_comes_before_a_closed_day(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Neema's first day is Thursday 12th, but she tapped on Tuesday 10th, a day the shop was closed for a funeral. Two
    # of the book's reasons hold; the first in ReviewReason's order is said: the day wasn't one of her job's at all,
    # which the manager settles first, by her first day (ATT-5's review).
    neema = _worker(shop_a, "Neema", started_on=NOV_12)
    _closure(shop_a, NOV_10, NOV_10)
    _came(device_a, neema, NOV_10)
    assert _days(shop_a, NOV_10, NOV_10)[("Neema", NOV_10)].review_reason == ReviewReason.OUTSIDE_JOB


def test_a_suspension_comes_before_a_disagreement_on_one_day(
    shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember
) -> None:
    # On each of two days one of Juma's taps was made while he was suspended, and the other is one a later tap's time
    # disagrees with: on Monday the disputed one comes first, on Tuesday the flagged one. Whatever order the taps are
    # read in, the day says the suspension, as whether he is paid at all comes before his time (ATT-5's review).
    for day, flagged_first in ((MONDAY, False), (TUESDAY, True)):
        ingia = tap(device_a, juma, ClockKind.IN, at(day, 7, 20))
        toka = tap(device_a, juma, ClockKind.OUT, at(day, 18, 45))
        flagged, disputed = (ingia, toka) if flagged_first else (toka, ingia)
        _flag_its_line(flagged)
        tap(device_a, asha, ClockKind.OUT, at(day, 18, 30), check=TimeCheck.UNVERIFIED, disagrees_with=disputed.pk)
    days = _days(shop_a, MONDAY, TUESDAY)
    assert days[("Juma", MONDAY)].review_reason == ReviewReason.NOT_WORKING
    assert days[("Juma", TUESDAY)].review_reason == ReviewReason.NOT_WORKING
