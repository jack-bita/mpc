"""apps/staffpay/tests/test_mine.py — a worker's own days and pay, as they read them themselves (WAGE-4, 02 A4).

own_attendance and own_pay (apps/staffpay/services/mine.py) are the manager's own reads (worker_attendance, worker_pay),
asked as the worker, so Asha's page and Baba's never say two different things about her month. What they add: the
months a worker may ask for, from their job's first month up to the shop's own, and a tap's time as its worker reads
it. What the worker is shown of each answer is the serializers' list, tested with the routes (test_mine_routes.py).

November 2026 starts on a Sunday; Monday the 16th is the shared helpers' day (days.py). The fines are the demo's
made-up 500 and 1,500, the rate a made-up 10,000 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, hire_again, mark_left
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.models import ClockKind
from apps.staffpay.services import (
    WorkerAttendance,
    own_attendance,
    own_pay,
    set_pay_rate,
    worker_attendance,
    worker_pay,
)
from apps.staffpay.services.book import month_span
from apps.staffpay.tests.days import JAN_1, MONDAY, doubted_tap, job, switch_on, tapped

pytestmark = pytest.mark.django_db

NOVEMBER = MONDAY.replace(day=1)
TUESDAY = MONDAY + dt.timedelta(days=1)


@pytest.fixture
def juma(shop_a: Shop, device_a: Device) -> StaffMember:
    # Juma, at the shop since January, with attendance on from then; the shop's one laptop holds his taps.
    switch_on(shop_a)
    return job(shop_a, "Juma")


def own_month(shop: Shop, staff: StaffMember, month: dt.date = NOVEMBER) -> WorkerAttendance:
    # As the route asks it, inside the shop the visit opened.
    with shop_context(shop):
        return own_attendance(shop, staff, month)


def test_own_month_is_the_managers_month_asked_as_the_worker(shop_a: Shop, juma: StaffMember) -> None:
    # Juma came on Monday the 16th, in and out; on Tuesday he tapped Ingia and forgot Toka, so the day waits for a
    # decision. His own month has the very days and counts the manager's calendar of him has, and the same taps. But
    # asked as Juma, no day offers a choice: nobody decides their own day (ATT-6), so the page has nothing to offer him.
    tapped(juma, (ClockKind.IN, 7, 50), (ClockKind.OUT, 18, 45), date=MONDAY)
    tapped(juma, (ClockKind.IN, 7, 40), date=TUESDAY)
    own = own_month(shop_a, juma)
    with shop_context(shop_a):
        managers = worker_attendance(shop_a, juma, NOVEMBER, viewer=None)
    assert own.worker == managers.worker
    assert [(day.date, day.status, day.reason, day.fine) for day in own.days] == [
        (day.date, day.status, day.reason, day.fine) for day in managers.days
    ]
    assert [tap.id for tap in own.taps] == [tap.id for tap in managers.taps]
    # The manager may decide Tuesday; Juma may decide nothing of his own.
    assert next(day for day in managers.days if day.date == TUESDAY).choices
    assert all(day.choices == [] for day in own.days)
    assert own.yours


def test_any_day_of_the_month_asks_the_whole_month(shop_a: Shop, juma: StaffMember) -> None:
    # The page sends the month as "2026-11", and a service is given its first day; a day inside it, the 16th, asks the
    # same month, as every month read does.
    assert own_month(shop_a, juma, MONDAY).month == NOVEMBER


def test_laptop_time_only_where_no_time_is_trusted(shop_a: Shop, juma: StaffMember) -> None:
    # Monday's Ingia at 07:50 has a time the server trusts: Juma reads 07:50, and nothing of the laptop's own clock,
    # which only says whether that laptop's clock was off (the shop's check). Tuesday's Ingia came from a laptop whose
    # clock moved, so the server trusts no time for it (ATT-1): the laptop's 07:20 is then the only time there is, and
    # his page says it, as not trusted.
    tapped(juma, (ClockKind.IN, 7, 50), date=MONDAY)
    doubted_tap(juma, 7, 20, TUESDAY)
    taps = {tap.date: tap for tap in own_month(shop_a, juma).taps}
    assert (taps[MONDAY].time, taps[MONDAY].laptop_time) == (dt.time(7, 50), None)
    assert (taps[TUESDAY].time, taps[TUESDAY].laptop_time) == (None, dt.time(7, 20))


def test_own_pay_is_the_line_mishahara_shows(shop_a: Shop, juma: StaffMember) -> None:
    # Juma is paid 10,000 a day from January and came in and out on Monday the 16th: his own pay is the very answer his
    # page on Mishahara gives, line for line, total for total, so the two can never say two amounts.
    with shop_context(shop_a):
        set_pay_rate(juma, daily_rate=Decimal("10000"), effective_from=JAN_1, by=None)
    tapped(juma, (ClockKind.IN, 7, 50), (ClockKind.OUT, 18, 45), date=MONDAY)
    with shop_context(shop_a):
        own = own_pay(shop_a, juma, MONDAY)
        managers = worker_pay(shop_a, juma, NOVEMBER)
    assert own == managers
    assert own.paid_by_day
    assert own.worker.pay.total > 0


def test_a_month_before_the_job_is_refused(shop_a: Shop, device_a: Device) -> None:
    # Neema started on 15 March: March is her first month, so her page opens on it, its days before the 15th saying
    # they were before her job, as the manager's calendar says them. February is no month of hers: a typed address
    # asking for it is refused, never answered as a month she never came.
    switch_on(shop_a)
    user = User.objects.create_user(full_name="Neema Demo")
    with shop_context(shop_a):
        neema = add_staff(shop=shop_a, user=user, display_name="Neema", started_on=dt.date(2026, 3, 15), by=None)
    assert own_month(shop_a, neema, dt.date(2026, 3, 1)).started_on == dt.date(2026, 3, 15)
    for read in (own_attendance, own_pay):
        with shop_context(shop_a), pytest.raises(ValidationError) as refused:
            read(shop_a, neema, dt.date(2026, 2, 1))
        assert refused.value.code == "mine.before_job"


def test_a_month_to_come_is_refused(shop_a: Shop, juma: StaffMember) -> None:
    # The shop's own month is the last a worker's page offers: the next one has no day yet, and asking it is a slip.
    this_month = shop_today(shop_a).replace(day=1)
    _, last = month_span(this_month)
    next_month = last + dt.timedelta(days=1)
    assert own_month(shop_a, juma, this_month).month == this_month
    for read in (own_attendance, own_pay):
        with shop_context(shop_a), pytest.raises(ValidationError) as refused:
            read(shop_a, juma, next_month)
        assert refused.value.code == "mine.month_to_come"


def test_hired_again_reads_only_the_job_logged_in_as(shop_a: Shop, juma: StaffMember) -> None:
    # Juma left on Friday 9 October and Baba hired him again from Monday the 19th (PPL-11): one person, two jobs. Logged
    # in as the new job, his page reads that job alone: October's taps after he came back, never the old job's, and
    # September is no month of the new job's, so it is refused, as the card's default says (04 §20, 32).
    tapped(juma, (ClockKind.IN, 7, 50), date=dt.date(2026, 10, 1))
    with shop_context(shop_a):
        mark_left(juma, left_on=dt.date(2026, 10, 9), by=None, reason="Ameacha kazi")
        juma.refresh_from_db()
        again = hire_again(juma, display_name="Juma", started_on=dt.date(2026, 10, 19), by=None)
    tapped(again, (ClockKind.IN, 7, 45), date=dt.date(2026, 10, 20))
    october = own_month(shop_a, again, dt.date(2026, 10, 1))
    assert [tap.date for tap in october.taps] == [dt.date(2026, 10, 20)]
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        own_attendance(shop_a, again, dt.date(2026, 9, 1))
    assert refused.value.code == "mine.before_job"


def test_another_shops_job_fails_loudly(shop_a: Shop, shop_b: Shop, juma: StaffMember) -> None:
    # The route finds the job through the guard, so another shop's never comes here; given one all the same, by a bug,
    # each read refuses loudly (T1), never answering another shop's days or pay.
    for read in (own_attendance, own_pay):
        with shop_context(shop_b), pytest.raises(ShopMismatch):
            read(shop_b, juma, NOVEMBER)
