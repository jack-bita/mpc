"""apps/staffpay/tests/test_attendance_book.py — the book of days: one row per worker per day, worked out by ATT-4's
rule from that day's taps and that day's rules, and kept (ATT-10; 02 §12).

    who    date        status        fine    in     out
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Asha   Sun 22 Nov  off           0.00    —      —

First the rules the database keeps on a day (AttendanceDay, apps/staffpay/models.py): one per job and date, a day that
fits its status, and never a delete. Then the book (work_out_days, apps/staffpay/services.py): which taps a day reads,
on which date, with which rules, and how a day worked out again is kept. What a day was, from its taps, is the rule's,
in test_attendance_day.py. Times are Arusha's, three hours ahead of UTC. The fines are the demo's made-up 500 and 1,500
(rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import itertools
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.control.models import EditEvent
from apps.core.settings_registry import ATTENDANCE_ON, LATE_FINE, SettingKey
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, change_worker, hire_again, mark_left
from apps.shops.models import Closure, Setting, Shop
from apps.shops.selectors import shop_today
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind, DayStatus, TimeCheck
from apps.staffpay.services import _keep, work_out_days

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


def test_each_status_saves_as_it_should(shop_a: Shop, staff_a: StaffMember) -> None:
    # The rule's other side: every status, as the book writes it, is kept. A late day with a fine of 0, as a shop
    # starts with (ATT-2); the morning's half with a late arrival's fine (the owner, ATT-4); and a day for review with
    # its taps, or with none.
    days = [
        {"status": DayStatus.LATE, "fine": Decimal("0.00")},
        {"status": DayStatus.HALF, "first_out": dt.time(13, 10)},
        {"status": DayStatus.ON_TIME, "fine": Decimal("0.00"), "first_in": dt.time(7, 20)},
        {"status": DayStatus.OFF, "fine": Decimal("0.00"), "first_in": None, "first_out": None, "rules_used": {}},
        {"status": DayStatus.ABSENT, "fine": Decimal("0.00"), "first_in": None, "first_out": None},
        {"status": DayStatus.NEEDS_REVIEW, "fine": Decimal("0.00"), "first_out": None},
        {"status": DayStatus.NEEDS_REVIEW, "fine": Decimal("0.00"), "first_in": None, "first_out": None},
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


def test_an_unverified_tap_falls_on_its_laptops_date(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # A tap with no trusted time has only the laptop's: its Monday, by the shop's clock, so the manager finds it on
    # Monday, and Tuesday holds nothing of it.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 20), check=TimeCheck.UNVERIFIED)
    days = _days(shop_a, MONDAY, TUESDAY)
    assert days[("Asha", MONDAY)].status == DayStatus.NEEDS_REVIEW
    assert days[("Asha", TUESDAY)].status == DayStatus.ABSENT


def test_a_day_follows_a_rule_changed_later(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha's Monday, late with no fine, as a shop starts with none (ATT-2). The owner then types a first fine of 500
    # from 1 November, a day already past: worked out again, her Monday takes it, and the edit history keeps the change
    # (ADR-0036), from 0.00 to 500.00.
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


def test_working_out_twice_keeps_one_row(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # Two runs at once (two managers open the month, or the night's job beside them): each reads no day kept, then
    # keeps its own. The second finds the first's rows by the rule of one day per job and date, and writes over them,
    # with the same answer, so one row stays per job and date, under its first id. _keep is handed no day kept, as the
    # second run read none.
    tap(device_a, asha, ClockKind.IN, at(MONDAY, 7, 50))
    first = _days(shop_a, MONDAY, TUESDAY)
    again = [
        AttendanceDay(
            shop=shop_a,
            staff=day.staff,
            date=day.date,
            status=day.status,
            fine=day.fine,
            first_in=day.first_in,
            first_out=day.first_out,
            rules_used=day.rules_used,
        )
        for day in first.values()
    ]
    with shop_context(shop_a):
        kept = _keep(again, {})
        assert AttendanceDay.objects.count() == 4
    assert sorted(day.pk for day in kept) == sorted(day.pk for day in first.values())


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


def test_a_day_no_longer_counted_is_not_answered(shop_a: Shop, attendance_on: None) -> None:
    # Neema was added with her first day on Monday 9th, and her days were kept. Then a manager fixes it to Wednesday
    # 11th, the day she really started (PPL-10): worked out again, Monday and Tuesday are no longer hers to answer.
    # Their rows stay, as nothing is deleted (rule 7), counted nowhere (ATT-11 decides what such a day shows).
    neema = _worker(shop_a, "Neema", started_on=NOV_9)
    assert len(_days(shop_a, NOV_9, NOV_13)) == 5
    with shop_context(shop_a):
        change_worker(neema, version=neema.version, reason="Alianza Jumatano", by=None, started_on=NOV_11)
    days = _days(shop_a, NOV_9, NOV_13)
    assert sorted(date for _, date in days) == [NOV_11, NOV_12, NOV_13]
    with shop_context(shop_a):
        assert AttendanceDay.objects.count() == 5
