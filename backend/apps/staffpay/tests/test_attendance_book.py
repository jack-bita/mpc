"""apps/staffpay/tests/test_attendance_book.py — the book of days: one row per worker per day, worked out by ATT-4's
rule from that day's taps and that day's rules, and kept (ATT-10; 02 §12).

    who    date        status        fine    in     out
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Asha   Sun 22 Nov  off           0.00    —      —

These tests pin the rules the database keeps on a day (AttendanceDay, apps/staffpay/models.py): one per job and date,
a day that fits its status, and never a delete. What a day was, from its taps, is the rule's, in
test_attendance_day.py. The fines are the demo's made-up 500 and 1,500 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.staffpay.models import AttendanceDay, DayStatus

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
