"""apps/staffpay/tests/test_pay_routes.py — the month's pay routes, /api/v1/staffpay/pay/ (WAGE-2, 03 §5.10).

    GET  pay/?month=2026-11        everyone's pay of the month, for Mishahara
    GET  pay/{id}/?month=2026-11   one worker's, for their pay page and the card on their own page

What the month pays is pay_month's and worker_pay's, tested in test_pay_month.py; who may open it is pinned in
backend/tests/test_route_permissions.py, beside every other route's. Here, the answer as the pages read it, its amounts
as strings, and what it refuses. The client from backend/conftest.py holds every key: shop A's owner, Staff A. Today is
Tuesday 24 November 2026, at 19:00. Fake data only.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop
from apps.staffpay.models import ClockKind
from apps.staffpay.services import record_meal_money, set_pay_rate
from apps.staffpay.tests.days import JAN_1, job, kept_day, switch_on, tapped

pytestmark = pytest.mark.django_db

PAY = "/api/v1/staffpay/pay/"
NOVEMBER = {"month": "2026-11"}
MONDAY = dt.date(2026, 11, 16)
TODAY = dt.date(2026, 11, 24)
FULL = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))


@pytest.fixture
def asha(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device, staff_a: StaffMember) -> StaffMember:
    # Asha, at 10,000 a day: a full day, a late one, half a day, and no Toka, the week before; 1,000 of meals on the
    # first; and a full day today. Her first of two names only, as everywhere.
    evening = dt.datetime(2026, 11, 24, 19, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: evening)
    switch_on(shop_a)
    staff = job(shop_a, "Asha")
    with shop_context(shop_a):
        set_pay_rate(staff, daily_rate=Decimal("10000"), effective_from=JAN_1, by=None)
        record_meal_money(shop_a, money_id=uuid.uuid7(), date=MONDAY, amount=Decimal("1000"), by=staff_a)
    kept_day(staff, *FULL, date=MONDAY)
    kept_day(staff, (ClockKind.IN, 7, 50), (ClockKind.OUT, 18, 45), date=dt.date(2026, 11, 17))
    kept_day(staff, (ClockKind.IN, 7, 20), (ClockKind.OUT, 13, 10), date=dt.date(2026, 11, 18))
    kept_day(staff, (ClockKind.IN, 7, 20), date=dt.date(2026, 11, 19))
    tapped(staff, *FULL, date=TODAY)
    return staff


def ashas_line(staff: StaffMember) -> dict[str, object]:
    """Asha's line, whole, as both routes answer it."""
    return {
        "staff": str(staff.pk),
        "display_name": "Asha",
        "left_on": None,
        "pay": {
            "lines": [
                {"paid_as": "full", "days": 2, "each": "10000.00", "amount": "20000.00"},
                {"paid_as": "half", "days": 1, "each": "5000.00", "amount": "5000.00"},
            ],
            "fined_days": 1,
            "fines": "500.00",
            "meal_days": 1,
            "meals": "1000.00",
            "advances": "0.00",
            "waiting": 1,
            "no_rate": 0,
            "total": "23500.00",
        },
        "today": {
            "lines": [{"paid_as": "full", "days": 1, "each": "10000.00", "amount": "10000.00"}],
            "fined_days": 0,
            "fines": "0.00",
            "meal_days": 0,
            "meals": "0.00",
            "advances": "0.00",
            "waiting": 0,
            "no_rate": 0,
            "total": "10000.00",
        },
        "total": "33500.00",
    }


def test_the_months_pay_as_the_page_reads_it(staff_client_a: APIClient, asha: StaffMember) -> None:
    # Every amount a string (rule 3), and nothing left for the page to add up. Staff A has no rate, so no line.
    reply = staff_client_a.get(PAY, NOVEMBER)
    assert reply.status_code == 200
    assert reply.json() == {
        "month": "2026-11",
        "today": "2026-11-24",
        "counted_to": "2026-11-23",
        "total": "33500.00",
        "workers": [ashas_line(asha)],
    }


def test_one_workers_pay_as_the_page_reads_it(staff_client_a: APIClient, asha: StaffMember) -> None:
    reply = staff_client_a.get(f"{PAY}{asha.pk}/", NOVEMBER)
    assert reply.status_code == 200
    assert reply.json() == {
        "month": "2026-11",
        "today": "2026-11-24",
        "counted_to": "2026-11-23",
        "paid_by_day": True,
        "worker": ashas_line(asha),
    }


def test_a_worker_with_no_rate_has_no_pay(staff_client_a: APIClient, staff_a: StaffMember, asha: StaffMember) -> None:
    answer = staff_client_a.get(f"{PAY}{staff_a.pk}/", NOVEMBER).json()
    assert (answer["paid_by_day"], answer["worker"]["today"]) == (False, None)
    assert (answer["worker"]["pay"]["lines"], answer["worker"]["total"]) == ([], "0.00")


def test_a_past_month_and_one_to_come(staff_client_a: APIClient, asha: StaffMember) -> None:
    # October counts to its end; December, and the calendar's last month, typed into the address, have nobody.
    october = staff_client_a.get(PAY, {"month": "2026-10"}).json()
    assert (october["counted_to"], october["total"]) == ("2026-10-31", "0.00")
    for month in ("2026-12", "9999-12"):
        reply = staff_client_a.get(PAY, {"month": month})
        assert reply.status_code == 200
        assert (reply.json()["counted_to"], reply.json()["workers"]) == (None, [])
        assert staff_client_a.get(f"{PAY}{asha.pk}/", {"month": month}).json()["paid_by_day"] is False


@pytest.mark.parametrize("month", [None, "", "2026-13", "2026-1", "2026-11-01", "1999-12", "novemba"])
def test_no_month_is_refused_beside_its_name(staff_client_a: APIClient, asha: StaffMember, month: str | None) -> None:
    sent = {} if month is None else {"month": month}
    for address in (PAY, f"{PAY}{asha.pk}/"):
        reply = staff_client_a.get(address, sent)
        assert reply.status_code == 400
        assert list(reply.json()["fields"]) == ["month"]


def test_a_worker_the_shop_doesnt_have_is_not_found(
    staff_client_a: APIClient, asha: StaffMember, staff_b: StaffMember
) -> None:
    # An id no shop has, and shop B's own worker by their real id: "not found" alike (03 §5.4).
    for staff_id in (uuid.uuid7(), staff_b.pk):
        reply = staff_client_a.get(f"{PAY}{staff_id}/", NOVEMBER)
        assert (reply.status_code, reply.json()["code"]) == (404, "not_found")


def test_the_pay_is_only_read(staff_client_a: APIClient, asha: StaffMember) -> None:
    # The draft is worked out, never sent (Jack, WAGE-2): no address takes one.
    for send in (staff_client_a.post, staff_client_a.put, staff_client_a.patch, staff_client_a.delete):
        for address in (PAY, f"{PAY}{asha.pk}/"):
            assert send(address, {}, format="json").status_code == 405
