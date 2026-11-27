"""apps/staffpay/tests/test_correction_routes.py — Marekebisho as the office pages call it (WAGE-10; 03 §5.10).

    POST /api/v1/staffpay/pay-corrections/              {id, staff, month, amount, reason}   typed on a worker's pay
    POST /api/v1/staffpay/pay-corrections/<id>/void/    {reason}                             crossed out
    GET  /api/v1/staffpay/pay/<staff>/?month=2026-12    the pay with it, the list, and whether the month takes one

Each answers the correction as the worker's page lists it. Thin: what may be typed and by whom is record_correction's,
proven in test_record_correction.py; here, what each route takes, what it answers, and who reaches it. The amounts are
made up: the repo is public (rule 10).
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.staffpay.models import PayCorrection, PayRate, PayRun
from apps.staffpay.tests.days import JAN_1, job

pytestmark = pytest.mark.django_db

CORRECTIONS = "/api/v1/staffpay/pay-corrections/"
DECEMBER = dt.date(2026, 12, 1)
REASON = "Novemba: siku ya 12/11 haikuhesabiwa"


@pytest.fixture(autouse=True)
def third_of_december(monkeypatch: pytest.MonkeyPatch) -> None:
    # 10:05 on Thursday 3 December in Arusha: November is over, December runs.
    moment = dt.datetime(2026, 12, 3, 10, 5, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: moment)


def paid(shop: Shop, name: str) -> StaffMember:
    # A worker paid a made-up 10,000 a day since January, written past set_pay_rate.
    staff = job(shop, name)
    with shop_context(shop):
        PayRate(shop=shop, staff=staff, daily_rate=Decimal("10000.00"), effective_from=JAN_1).save()
    return staff


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    return paid(shop_a, "Juma")


def sheet(worker: StaffMember, **changes: Any) -> dict[str, Any]:
    # What the sheet sends: the row's id, made on the phone (ADR-0007), the worker, the page's month, the amount as a
    # string (rule 3), below 0 for Punguza malipo, and why.
    sent = {"id": str(uuid.uuid7()), "staff": str(worker.pk), "month": "2026-12", "amount": "9000.00", "reason": REASON}
    return sent | changes


def row_of(staff: StaffMember, by: StaffMember, amount: str = "9000.00") -> PayCorrection:
    # A row written past the service, which shop B's needs the keys for: shop A's routes never reach it.
    with shop_context(staff.shop_id):
        row = PayCorrection(
            shop_id=staff.shop_id, staff=staff, month=DECEMBER, amount=Decimal(amount), reason=REASON, created_by=by
        )
        row.save()
    return row


def void_url(row_id: uuid.UUID | str) -> str:
    return f"{CORRECTIONS}{row_id}/void/"


def pay_page(client: APIClient, staff: StaffMember, month: str = "2026-12") -> Any:
    reply = client.get(f"/api/v1/staffpay/pay/{staff.pk}/", {"month": month})
    assert reply.status_code == 200, reply.json()
    return reply.json()


# Typing one.


def test_one_typed_as_the_sheet_sends_it(staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember) -> None:
    # The answer is the row as the worker's page lists it. Sent again, as a phone whose answer was lost does, the same
    # row comes back, never a second one.
    sent = sheet(juma, amount="-5000", reason=f"  {REASON} ")
    reply = staff_client_a.post(CORRECTIONS, sent, format="json")
    assert reply.status_code == 201, reply.json()
    body = reply.json()
    assert {key: body[key] for key in ("id", "amount", "reason", "by", "voided")} == {
        "id": sent["id"],
        "amount": "-5000.00",
        "reason": REASON,
        "by": staff_a.display_name,
        "voided": None,
    }
    assert staff_client_a.post(CORRECTIONS, sent, format="json").json() == body
    with shop_context(juma.shop_id):
        assert PayCorrection.objects.count() == 1


def test_the_workers_pay_says_it(staff_client_a: APIClient, juma: StaffMember) -> None:
    # Juma's December: the + 9,000 in its pay and its total, the whole of it, as this shop has no attendance on, so no
    # day; listed with who typed it; and the month takes another.
    staff_client_a.post(CORRECTIONS, sheet(juma), format="json")
    page = pay_page(staff_client_a, juma)
    assert (page["worker"]["pay"]["corrections"], page["worker"]["total"]) == ("9000.00", "9000.00")
    ((listed),) = page["corrections"]
    assert (listed["amount"], listed["reason"], listed["voided"]) == ("9000.00", REASON, None)
    assert (page["no_correction"], page["correction_reasons"], page["correction_void_reasons"]) == (None, [], [])
    # Mishahara's line says the same sum.
    (line,) = staff_client_a.get("/api/v1/staffpay/pay/", {"month": "2026-12"}).json()["workers"]
    assert line["pay"]["corrections"] == "9000.00"


def test_an_approved_month_says_why_it_takes_none(
    shop_a: Shop, staff_a: StaffMember, staff_client_a: APIClient, juma: StaffMember
) -> None:
    # November approved: its page offers no Ongeza marekebisho, and the route refuses one, whole.
    with shop_context(shop_a):
        PayRun.objects.create(shop=shop_a, month=dt.date(2026, 11, 1), created_by=staff_a)
    assert pay_page(staff_client_a, juma, "2026-11")["no_correction"] == "pay.day_approved"
    reply = staff_client_a.post(CORRECTIONS, sheet(juma, month="2026-11"), format="json")
    assert (reply.status_code, reply.json()["code"], reply.json()["fields"]) == (400, "pay.day_approved", {})


def test_the_boxes_refusals_come_beside_them(staff_client_a: APIClient, juma: StaffMember) -> None:
    reply = staff_client_a.post(CORRECTIONS, sheet(juma, amount="0", reason=" "), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"amount": ["correction.amount_invalid"], "reason": ["correction.reason_missing"]}


def test_ones_own_is_refused_whole(shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember) -> None:
    # The owner paid by the day too: never his own pay (Jack: A).
    with shop_context(shop_a):
        PayRate(shop=shop_a, staff=staff_a, daily_rate=Decimal("10000.00"), effective_from=JAN_1).save()
    reply = staff_client_a.post(CORRECTIONS, sheet(staff_a), format="json")
    assert (reply.status_code, reply.json()["code"]) == (400, "correction.own")


def test_what_the_sheet_never_sends_is_refused(staff_client_a: APIClient, juma: StaffMember) -> None:
    # No id, an id of another kind, a month that is no month, an amount that is no number or has three places: refused
    # by the route's own checks, before the service is asked.
    for changes, field in (
        ({"id": str(uuid.uuid4())}, "id"),
        ({"month": "2026-12-01"}, "month"),
        ({"amount": "nine"}, "amount"),
        ({"amount": "9000.001"}, "amount"),
    ):
        reply = staff_client_a.post(CORRECTIONS, sheet(juma, **changes), format="json")
        assert (reply.status_code, set(reply.json()["fields"])) == (400, {field}), changes
    without = sheet(juma)
    del without["id"]
    assert staff_client_a.post(CORRECTIONS, without, format="json").status_code == 400


def test_another_shops_worker_is_not_found(staff_client_a: APIClient, shop_b: Shop, juma: StaffMember) -> None:
    # An id no shop has, and shop B's worker by their real id: refused alike, so nothing says that such a worker exists.
    for staff_id in (uuid.uuid7(), paid(shop_b, "Jirani").pk):
        reply = staff_client_a.post(CORRECTIONS, sheet(juma, staff=str(staff_id)), format="json")
        assert (reply.status_code, reply.json()["fields"]) == (400, {"staff": ["does_not_exist"]})


def test_another_shops_row_is_never_handed_back(
    shop_b: Shop, staff_b: StaffMember, staff_client_a: APIClient, juma: StaffMember
) -> None:
    # Shop B's row, its id sent as a new row's from shop A: the id is in use, and nothing of the row is said (03 §5.4).
    theirs = row_of(paid(shop_b, "Jirani"), staff_b)
    reply = staff_client_a.post(CORRECTIONS, sheet(juma, id=str(theirs.pk)), format="json")
    assert (reply.status_code, reply.json()["fields"]) == (400, {"id": ["id.taken"]})


# Crossing one out.


def test_one_crossed_out_as_the_sheet_sends_it(
    staff_client_a: APIClient, staff_a: StaffMember, staff_a2: StaffMember, juma: StaffMember
) -> None:
    # Typed by another who approves pay (staff_a2), crossed out by the owner: the answer is the row struck through.
    # Sent again, the same stamp comes back, never written twice.
    row = row_of(juma, staff_a2, "90000.00")
    reply = staff_client_a.post(void_url(row.pk), {"reason": "Kiasi kimekosewa"}, format="json")
    assert reply.status_code == 200, reply.json()
    voided = reply.json()["voided"]
    assert (voided["by"], voided["reason"]) == (staff_a.display_name, "Kiasi kimekosewa")
    again = staff_client_a.post(void_url(row.pk), {"reason": "Sababu nyingine"}, format="json")
    assert again.json()["voided"] == voided
    # The page lists it, struck through, and the pay counts nothing of it.
    page = pay_page(staff_client_a, juma)
    assert (page["corrections"][0]["voided"], page["worker"]["pay"]["corrections"]) == (voided, "0.00")


def test_crossing_out_with_no_reason_is_refused_beside_its_box(
    staff_client_a: APIClient, staff_a2: StaffMember, juma: StaffMember
) -> None:
    reply = staff_client_a.post(void_url(row_of(juma, staff_a2).pk), {"reason": ""}, format="json")
    assert (reply.status_code, reply.json()["fields"]) == (400, {"reason": ["correction.reason_missing"]})


@pytest.mark.parametrize("sent", [{}, {"reason": "Kosa"}])
def test_another_shops_row_is_not_found_whatever_is_sent(
    shop_b: Shop, staff_b: StaffMember, staff_client_a: APIClient, sent: dict[str, Any]
) -> None:
    # Before the body is read, so an empty request never answers differently for a row another shop has (03 §5.4).
    theirs = staff_client_a.post(void_url(row_of(paid(shop_b, "Jirani"), staff_b).pk), sent, format="json")
    nobodys = staff_client_a.post(void_url(uuid.uuid7()), sent, format="json")
    assert theirs.status_code == nobodys.status_code == 404
    assert theirs.json() == nobodys.json()


def test_nothing_else_is_taken(staff_client_a: APIClient, staff_a2: StaffMember, juma: StaffMember) -> None:
    # A ledger (rule 2): no address lists one, and a row has no address to read, edit or delete it by, so the router
    # knows none; the worker's pay lists them.
    row = row_of(juma, staff_a2)
    assert staff_client_a.get(CORRECTIONS).status_code == 405
    for send in (staff_client_a.get, staff_client_a.put, staff_client_a.patch, staff_client_a.delete):
        assert send(f"{CORRECTIONS}{row.pk}/", {"amount": "1.00"}, format="json").status_code == 404
    with shop_context(juma.shop_id):
        assert PayCorrection.objects.get(pk=row.pk).amount == Decimal("9000.00")


def test_on_the_demo_the_sheets_are_told_the_ready_reasons(
    settings: Settings, staff_client_a: APIClient, staff_a2: StaffMember, juma: StaffMember
) -> None:
    # A reason typed is refused beside its box; the ready ones, which the page names, are taken, kept as their codes.
    settings.DEMO_SEED = True
    reply = staff_client_a.post(CORRECTIONS, sheet(juma), format="json")
    assert reply.json()["fields"] == {"reason": ["demo.ready_reasons"]}
    page = pay_page(staff_client_a, juma)
    assert (page["correction_reasons"], page["correction_void_reasons"]) == (
        ["day_not_counted", "paid_too_much"],
        ["wrong_amount"],
    )
    made = staff_client_a.post(CORRECTIONS, sheet(juma, reason="day_not_counted"), format="json")
    assert made.status_code == 201
    reply = staff_client_a.post(void_url(made.json()["id"]), {"reason": "Kosa"}, format="json")
    assert reply.json()["fields"] == {"reason": ["demo.ready_reasons"]}
    assert (
        staff_client_a.post(void_url(made.json()["id"]), {"reason": "wrong_amount"}, format="json").status_code == 200
    )
