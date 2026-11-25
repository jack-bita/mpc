"""apps/staffpay/tests/test_meal_money_route.py — the routes of the day's meal money, /api/v1/staffpay/meal-money/
(WAGE-7, 03 §5.10).

    GET  meal-money/?first=2026-11-20&last=2026-11-23   the days, and the whole of them
    POST meal-money/             {"id": …, "date": "2026-11-23", "amount": "5000.00", "note": "Unga na maharage"}
    POST meal-money/{id}/void/   {"reason": "Sifuri moja zaidi"}

What may be typed, by whom, and how a mistake is mended are the services', tested in test_record_meal_money.py; which
days are answered, in test_meal_money_days.py; who may call the routes is pinned in backend/tests/test_route_permissions
.py, beside every other route's. Here, the requests and the answers as the pages and the sheets send and read them, a
row the routes don't show, and the refusals as the sheets show them. The client from backend/conftest.py holds every
key: shop A's owner, Staff A. The amounts are made up (rule 10). Fake data only: the repo is public.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.models import ClockKind, MealMoney
from apps.staffpay.services import set_pay_rate
from apps.staffpay.tests.days import JAN_1, MONDAY, SUNDAY, job, kept_day, switch_on

pytestmark = pytest.mark.django_db

MEAL_MONEY = "/api/v1/staffpay/meal-money/"
DAY = MONDAY.isoformat()


@pytest.fixture(autouse=True)
def the_shops_day(shop_a: Shop, device_a: Device) -> None:
    # Shop A switched attendance on in January, and keeps its laptop, where Juma's taps are made (days.py).
    switch_on(shop_a)


def void_url(row_id: uuid.UUID | str) -> str:
    return f"{MEAL_MONEY}{row_id}/void/"


def sheet(**changes: Any) -> dict[str, Any]:
    # What Andika hela ya chakula sends: the row's id, made on the phone (ADR-0007), the day, the amount as a string
    # (rule 3), and what it bought.
    sent = {"id": str(uuid.uuid7()), "date": DAY, "amount": "5000.00", "note": "Unga na maharage"}
    return sent | changes


def days(client: APIClient, first: str = DAY, last: str = DAY) -> Any:
    reply = client.get(MEAL_MONEY, {"first": first, "last": last})
    assert reply.status_code == 200, reply.json()
    return reply.json()


# The days.


def test_the_days_as_the_page_reads_them(shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember) -> None:
    # Juma came on Monday and shares the meals; its flour is typed, and 30,000 typed by mistake and crossed out. Money
    # is strings (rule 3), and the shop's today is the server's to say.
    juma = job(shop_a, "Juma")
    with shop_context(shop_a):
        set_pay_rate(juma, daily_rate=Decimal("10000"), effective_from=JAN_1, by=None)
    kept_day(juma, (ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
    flour = staff_client_a.post(MEAL_MONEY, sheet(), format="json").json()
    wrong = staff_client_a.post(MEAL_MONEY, sheet(amount="30000.00", note=""), format="json").json()
    staff_client_a.post(void_url(wrong["id"]), {"reason": "Sifuri moja zaidi"}, format="json")

    answer = days(staff_client_a)

    with shop_context(shop_a):
        assert answer.pop("today") == shop_today(shop_a).isoformat()
    (monday,) = answer.pop("days")
    # No month is approved yet, so none of its days is closed (WAGE-3).
    assert answer == {"first": DAY, "last": DAY, "total": "5000.00", "ready_void_reasons": [], "closed_to": None}
    first, second = monday.pop("rows")
    assert monday == {"date": DAY, "amount": "5000.00", "over": True, "sharers": 1, "share": "5000.00", "waiting": 0}
    assert first == flour
    at = second["voided"].pop("at")
    assert at.endswith("Z")
    assert second == {
        "id": wrong["id"],
        "date": DAY,
        "amount": "30000.00",
        "note": "",
        "by": staff_a.display_name,
        "at": second["at"],
        "voided": {"by": staff_a.display_name, "reason": "Sifuri moja zaidi"},
    }


@pytest.mark.parametrize(
    ("asked", "field", "code"),
    [
        ({}, "first", "required"),
        ({"first": DAY}, "last", "required"),
        ({"first": "jana", "last": DAY}, "first", "invalid"),
        # Hadi before Kuanzia, and more than a year: each beside Hadi, with its own sentence.
        ({"first": "2026-11-17", "last": DAY}, "last", "meal_money.days_backwards"),
        ({"first": "2025-11-01", "last": DAY}, "last", "meal_money.too_many_days"),
        # No shop's attendance is older, and near the calendar's first day a day in Arusha falls before UTC's first.
        ({"first": "1999-12-31", "last": "2000-01-01"}, "first", "invalid"),
    ],
)
def test_days_that_are_none_are_refused(
    staff_client_a: APIClient, asked: dict[str, str], field: str, code: str
) -> None:
    reply = staff_client_a.get(MEAL_MONEY, asked)
    assert reply.status_code == 400
    assert reply.json()["fields"][field] == [code]


def test_a_year_is_not_too_many_days(staff_client_a: APIClient) -> None:
    # 366 days, both ends counted: a leap year's whole.
    assert days(staff_client_a, (MONDAY - timedelta(days=365)).isoformat(), DAY)["last"] == DAY
    reply = staff_client_a.get(MEAL_MONEY, {"first": (MONDAY - timedelta(days=366)).isoformat(), "last": DAY})
    assert reply.status_code == 400


def test_the_calendars_last_day_is_only_days_to_come(staff_client_a: APIClient) -> None:
    # A span typed into the address at the end of time: nothing to show, never a server error (as the month page's,
    # ATT-5's review).
    answer = days(staff_client_a, "9999-12-01", "9999-12-31")
    assert (answer["days"], answer["total"]) == ([], "0.00")
    assert (answer["first"], answer["last"]) == ("9999-12-01", "9999-12-31")


# Typing the day's money.


def test_money_typed_as_the_sheet_sends_it(shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember) -> None:
    # The answer is the row as the day's page shows it. Sent again with the same id, as a phone whose answer was lost
    # does, the same row comes back, and only one is kept (CreateOnceMixin).
    sent = sheet()
    reply = staff_client_a.post(MEAL_MONEY, sent, format="json")
    assert reply.status_code == 201
    answer = reply.json()
    assert answer.pop("at").endswith("Z")
    assert answer == {**sent, "by": staff_a.display_name, "voided": None}
    again = staff_client_a.post(MEAL_MONEY, {**sent, "amount": "9000.00"}, format="json")
    assert (again.status_code, again.json()["amount"]) == (201, "5000.00")
    with shop_context(shop_a):
        assert MealMoney.objects.count() == 1


def test_typing_refusals_come_beside_their_boxes(staff_client_a: APIClient) -> None:
    # A Sunday and an amount with cents: both at once, each beside its box, with the codes the sheet says in words.
    reply = staff_client_a.post(MEAL_MONEY, sheet(date=SUNDAY.isoformat(), amount="5000.50"), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {
        "date": ["meal_money.not_working_day"],
        "amount": ["meal_money.amount_invalid"],
    }


def test_a_day_to_come_and_too_many_zeros(shop_a: Shop, staff_client_a: APIClient) -> None:
    with shop_context(shop_a):
        tomorrow = shop_today(shop_a) + timedelta(days=1)
    reply = staff_client_a.post(MEAL_MONEY, sheet(date=tomorrow.isoformat(), amount="50000000"), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"date": ["meal_money.in_future"], "amount": ["meal_money.amount_too_big"]}


def test_what_the_sheet_never_sends_is_refused(staff_client_a: APIClient) -> None:
    # An id that is no UUIDv7, an amount that is no number or has three places, a note past 200 characters, and a
    # missing id: refused by the serializer, each beside its box.
    reply = staff_client_a.post(
        MEAL_MONEY, sheet(id=str(uuid.uuid4()), amount="elfu tano", note="u" * 201), format="json"
    )
    assert reply.status_code == 400
    assert set(reply.json()["fields"]) == {"id", "amount", "note"}
    assert reply.json()["fields"]["note"] == ["max_length"]
    places = staff_client_a.post(MEAL_MONEY, sheet(amount="5000.005"), format="json")
    assert set(places.json()["fields"]) == {"amount"}
    without = sheet()
    del without["id"]
    assert staff_client_a.post(MEAL_MONEY, without, format="json").json()["fields"]["id"] == ["required"]


def test_money_typed_with_no_note(staff_client_a: APIClient) -> None:
    # Maelezo is optional: left out, or empty.
    without = sheet()
    del without["note"]
    assert staff_client_a.post(MEAL_MONEY, without, format="json").json()["note"] == ""
    assert staff_client_a.post(MEAL_MONEY, sheet(note=""), format="json").status_code == 201


def test_another_shops_row_is_never_handed_back(shop_b: Shop, staff_b: StaffMember, staff_client_a: APIClient) -> None:
    # Shop B's row, its id sent as a new row's from shop A: the id is in use, and nothing of the row is said (03 §5.4).
    theirs = row_of(shop_b, staff_b)
    reply = staff_client_a.post(MEAL_MONEY, sheet(id=str(theirs.pk)), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"id": ["id.taken"]}


def row_of(shop: Shop, by: StaffMember, day: date = MONDAY) -> MealMoney:
    # A row written past the service, which shop B's needs a key for: shop A's routes never reach it.
    with shop_context(shop):
        row = MealMoney(shop=shop, date=day, amount=Decimal("9000.00"), note="Siri ya Jirani", created_by=by)
        row.save()
    return row


# Crossing one out.


def test_money_crossed_out_as_the_sheet_sends_it(shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember) -> None:
    # The answer is the row as the day's page shows it, struck through. Sent again, as a phone whose answer was lost
    # does, the same stamp comes back, never written twice.
    row = row_of(shop_a, staff_a)
    reply = staff_client_a.post(void_url(row.pk), {"reason": "Sifuri moja zaidi"}, format="json")
    assert reply.status_code == 200
    voided = reply.json()["voided"]
    assert (voided["by"], voided["reason"]) == (staff_a.display_name, "Sifuri moja zaidi")
    again = staff_client_a.post(void_url(row.pk), {"reason": "Sababu nyingine"}, format="json")
    assert again.json()["voided"] == voided


def test_crossing_out_with_no_reason_is_refused_beside_its_box(
    shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember
) -> None:
    row = row_of(shop_a, staff_a)
    reply = staff_client_a.post(void_url(row.pk), {"reason": "  "}, format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"reason": ["meal_money.reason_missing"]}


@pytest.mark.parametrize("sent", [{}, {"reason": "Sifuri moja zaidi"}, {"reason": 5}])
def test_another_shops_row_is_not_found_whatever_is_sent(
    shop_b: Shop, staff_b: StaffMember, staff_client_a: APIClient, sent: dict[str, Any]
) -> None:
    # Before the body is read, so an empty request never answers differently for a row another shop has (03 §5.4).
    theirs = staff_client_a.post(void_url(row_of(shop_b, staff_b).pk), sent, format="json")
    nobodys = staff_client_a.post(void_url(uuid.uuid7()), sent, format="json")
    assert theirs.status_code == nobodys.status_code == 404
    assert theirs.json() == nobodys.json()


def test_on_the_demo_the_sheets_are_told_the_ready_reason(
    settings: Settings, shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember
) -> None:
    # A note typed and a reason typed are refused beside their boxes; the ready one is answered with the days.
    settings.DEMO_SEED = True
    reply = staff_client_a.post(MEAL_MONEY, sheet(), format="json")
    assert reply.json()["fields"] == {"note": ["demo.no_note"]}
    row = row_of(shop_a, staff_a)
    reply = staff_client_a.post(void_url(row.pk), {"reason": "Sifuri moja zaidi"}, format="json")
    assert reply.json()["fields"] == {"reason": ["demo.ready_reasons"]}
    (ready,) = days(staff_client_a)["ready_void_reasons"]
    assert staff_client_a.post(void_url(row.pk), {"reason": ready}, format="json").status_code == 200
