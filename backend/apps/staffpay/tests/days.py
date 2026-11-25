"""apps/staffpay/tests/days.py — real days for the tests of deciding a day (ATT-6): no test of its own.

Deciding a day asks the book of days for it first (decide_day, apps/staffpay/services.py), and the book works a day out
again from its taps, so a day written past the book, as the book's own rule tests write theirs, would come back absent.
These helpers make a day the way the shop does: taps on the shop's laptop, then the book (work_out_days).

    switch_on(shop)       attendance on from 1 January, the demo's made-up fines 500 and 1,500 (rule 10)
    job(shop, "Juma")     a job since 1 January, so every day decided here is one of its days
    kept_day(juma)        Monday 16 Nov: in at 07:50, no Toka, waiting for a decision
    kept_day(juma, (ClockKind.OUT, 18, 45))   the same Monday with the taps named instead
    tapped(juma, (ClockKind.IN, 7, 20), date=today)   the taps alone, for a day still running, never kept
    absent_day(juma)      a day with no tap: absent, or off on a Sunday
    doubted_tap(juma, 7, 20)  an Ingia whose time the server doesn't trust, for a day whose time is in doubt; or a
                              Toka, with kind=ClockKind.OUT

The shop must hold one laptop (the `device_a` fixture for shop A). Fake data only: the repo is public.
"""

import datetime as dt
import itertools
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from apps.core.settings_registry import ATTENDANCE_ON, LATE_FINE, SECOND_FINE, SettingKey
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Setting, Shop
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind, TimeCheck
from apps.staffpay.services import work_out_days

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")
JAN_1 = dt.date(2026, 1, 1)
MONDAY = dt.date(2026, 11, 16)
SUNDAY = dt.date(2026, 11, 15)
FIRST_FINE = Decimal("500.00")
SECOND_FINE_AMOUNT = Decimal("1500.00")
# Each tap's number on the laptop, one after another, as a laptop numbers its records (SYNC-4).
_numbers = itertools.count(1)


def rule(shop: Shop, key: SettingKey[Any], value: Any, effective_from: dt.date) -> None:
    """A rule of the shop's from a day, saved as set_setting saves one, but on a day gone by, which the service
    refuses, as test_attendance_book.py writes its rows: these tests decide days gone by."""
    with shop_context(shop):
        row = Setting(shop=shop, key=key.key, value=key.kind.to_text(value), effective_from=effective_from)
        row.full_clean()
        row.save()


def switch_on(shop: Shop) -> None:
    """The shop switched attendance on in January, with the owner's two fines (ADR-0033, ATT-2)."""
    rule(shop, ATTENDANCE_ON, True, JAN_1)
    rule(shop, LATE_FINE, FIRST_FINE, JAN_1)
    rule(shop, SECOND_FINE, SECOND_FINE_AMOUNT, JAN_1)


def job(shop: Shop, name: str) -> StaffMember:
    """A job made the way the app makes one: create_user, then the people service, inside the shop (PPL-2), since
    January, so every day decided here is one of its days."""
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, started_on=JAN_1, by=None)


def kept_day(staff: StaffMember, *taps: tuple[ClockKind, int, int], date: dt.date = MONDAY) -> AttendanceDay:
    """The day as the book keeps it, from taps made on the shop's laptop: Juma's Monday, in at 07:50 and no Toka, sent
    to review, unless the test names its own taps, as (ClockKind.OUT, 18, 45)."""
    tapped(staff, *(taps or ((ClockKind.IN, 7, 50),)), date=date)
    return absent_day(staff, date)


def tapped(staff: StaffMember, *taps: tuple[ClockKind, int, int], date: dt.date) -> None:
    """Taps made on the shop's laptop, and nothing else: the book isn't asked for their day, as it answers no day still
    running (WAGE-2)."""
    with shop_context(staff.shop_id):
        laptop = Device.objects.get(shop=staff.shop_id)
        for kind, hour, minute in taps:
            moment = dt.datetime(date.year, date.month, date.day, hour, minute, tzinfo=ARUSHA)
            AttendanceEvent(
                shop_id=staff.shop_id,
                device=laptop,
                device_seq=next(_numbers),
                client_time=moment,
                received_at=moment + dt.timedelta(hours=1),
                created_by=staff,
                staff=staff,
                kind=kind,
                trusted_time=moment,
                time_check=TimeCheck.DEVICE_OK,
                last_server_time=moment - dt.timedelta(minutes=30),
                clock_error=dt.timedelta(0),
                no_photo="demo",
            ).save()


def doubted_tap(
    staff: StaffMember, hour: int, minute: int, date: dt.date = MONDAY, *, kind: ClockKind = ClockKind.IN
) -> None:
    """An Ingia, or a Toka, whose time the server doesn't trust (`unverified`, ATT-1): the laptop's clock moved for it,
    so it keeps only the laptop's time, and its day waits for a decision with the reason time_unknown (ATT-4)."""
    moment = dt.datetime(date.year, date.month, date.day, hour, minute, tzinfo=ARUSHA)
    with shop_context(staff.shop_id):
        AttendanceEvent(
            shop_id=staff.shop_id,
            device=Device.objects.get(shop=staff.shop_id),
            device_seq=next(_numbers),
            client_time=moment,
            received_at=moment + dt.timedelta(hours=1),
            created_by=staff,
            staff=staff,
            kind=kind,
            trusted_time=None,
            time_check=TimeCheck.UNVERIFIED,
            last_server_time=moment - dt.timedelta(minutes=30),
            clock_error=dt.timedelta(0),
            no_photo="demo",
        ).save()


def absent_day(staff: StaffMember, date: dt.date = MONDAY) -> AttendanceDay:
    """The day as the book keeps it, from the taps there are: with none, absent, or off on a Sunday."""
    with shop_context(staff.shop_id):
        shop = Shop.objects.get(pk=staff.shop_id)
        return next(day for day in work_out_days(shop, date, date) if day.staff_id == staff.pk)
