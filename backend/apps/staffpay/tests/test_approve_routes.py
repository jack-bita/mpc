"""apps/staffpay/tests/test_approve_routes.py — the routes that approve a month's pay, and one worker's alone (WAGE-3,
03 §5.10), and what the pay's routes answer around it.

    POST pay-runs/    {id, month, seen: [{staff, total}]}     a month, for everyone
    POST payslips/    {id, staff, month, seen}                one who left, alone
    GET  pay/?month=  GET pay/{id}/?month=                    what stops it, before; who approved it, after

What each service checks and keeps is test_approve_month.py's and test_approve_leaver.py's; who may is pinned in
backend/tests/test_route_permissions.py, beside every other route's. Here, what is sent and answered, its amounts as
strings, and a request sent twice. The client holds every key: shop A's owner, Staff A. Today is 1 December 2026, 19:05.
Fake data only.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import mark_left
from apps.shops.models import Shop
from apps.staffpay.models import ClockKind, PayRun, Payslip
from apps.staffpay.services import record_advance, record_meal_money, set_pay_rate
from apps.staffpay.tests.days import job, kept_day, rule, tapped

pytestmark = pytest.mark.django_db

BASE = "/api/v1/staffpay/"
PAY, RUNS, SLIPS = f"{BASE}pay/", f"{BASE}pay-runs/", f"{BASE}payslips/"
NOVEMBER = {"month": "2026-11"}
FULL = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
MON, TUE = dt.date(2026, 11, 16), dt.date(2026, 11, 17)
EVENING = dt.datetime(2026, 12, 1, 19, 5, tzinfo=dt.timezone(dt.timedelta(hours=3)))
# When it was approved, as the API writes a moment: UTC (03 §5.10).
AT = "2026-12-01T16:05:00Z"


@pytest.fixture(autouse=True)
def first_of_december(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device) -> None:
    monkeypatch.setattr(timezone, "now", lambda: EVENING)
    rule(shop_a, ATTENDANCE_ON, True, dt.date(2026, 11, 1))
    with shop_context(shop_a):
        Device.objects.update(last_synced_at=EVENING, created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))


def paid(shop: Shop, name: str, *, since: dt.date = dt.date(2026, 11, 1)) -> StaffMember:
    staff = job(shop, name)
    with shop_context(shop):
        set_pay_rate(staff, daily_rate=Decimal("10000"), effective_from=since, by=None)
    return staff


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    staff = paid(shop_a, "Asha")
    kept_day(staff, *FULL, date=MON)
    kept_day(staff, *FULL, date=TUE)
    return staff


def seen(*workers: tuple[StaffMember, str]) -> list[dict[str, str]]:
    return [{"staff": str(staff.pk), "total": total} for staff, total in workers]


def approve(client: APIClient, workers: list[dict[str, str]], **other: Any) -> Any:
    sent = {"id": str(uuid.uuid7()), "month": "2026-11", "seen": workers} | other
    return client.post(RUNS, sent, format="json")


def test_a_month_is_approved_as_it_was_read(
    staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember, asha: StaffMember
) -> None:
    before = staff_client_a.get(PAY, NOVEMBER).json()
    assert (before["approval"], before["workers"][0]["approval"]) == (None, None)
    assert before["to_approve"] == {
        "earlier": None,
        "waiting": [],
        "no_rate": [],
        "still_clocked_in": False,
        "quiet_laptops": [],
        "came_unpaid": [],
    }
    made = str(uuid.uuid7())
    reply = approve(staff_client_a, seen((asha, "20000.00")), id=made)
    assert reply.status_code == 201
    said = {"id": made, "month": "2026-11", "approved_by": staff_a.display_name, "approved_at": AT}
    assert reply.json() == said
    # Sent again, its answer lost on the way: the very same approval, whatever it carries now.
    again = approve(staff_client_a, seen((asha, "1.00")), id=made)
    assert (again.status_code, again.json()) == (201, said)
    after = staff_client_a.get(PAY, NOVEMBER).json()
    approval = {"by": staff_a.display_name, "at": AT}
    assert (after["approval"], after["to_approve"], after["counted_to"]) == (approval, None, "2026-11-30")
    # The line Baba read, now with who approved it, and its payslip, which waits for Lipa (WAGE-9).
    with shop_context(shop_a):
        slip = Payslip.objects.get()
    kept = {"approval": approval, "payslip": str(slip.pk), "to_hand_out": "20000.00"}
    assert after["workers"] == [before["workers"][0] | kept]
    assert after["still_to_pay"] == "20000.00"
    with shop_context(shop_a):
        assert (PayRun.objects.count(), Payslip.objects.count()) == (1, 1)


def test_what_stops_it_as_the_page_reads_it(
    staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember, asha: StaffMember, device_a: Device
) -> None:
    # An earlier month, a day that waits, a day with no rate, a laptop that has sent nothing since, and one who came
    # with no daily pay: each as the sheet names it.
    juma = paid(shop_a, "Juma", since=TUE)
    kept_day(juma, *FULL, date=MON)
    kept_day(juma, (ClockKind.IN, 7, 20), date=dt.date(2026, 11, 18))
    kept_day(job(shop_a, "Zawadi"), *FULL, date=MON)
    with shop_context(shop_a):
        record_advance(asha, advance_id=uuid.uuid7(), date=dt.date(2026, 10, 20), amount=Decimal("5000"), by=staff_a)
        Device.objects.update(last_synced_at=dt.datetime(2026, 11, 28, 15, 45, tzinfo=dt.UTC))
    assert staff_client_a.get(PAY, NOVEMBER).json()["to_approve"] == {
        "earlier": "2026-10",
        "waiting": [{"staff": str(juma.pk), "display_name": "Juma", "date": "2026-11-18"}],
        "no_rate": [{"staff": str(juma.pk), "display_name": "Juma", "date": "2026-11-16"}],
        "still_clocked_in": False,
        "quiet_laptops": [{"name": device_a.name, "last_synced_at": "2026-11-28T15:45:00Z"}],
        "came_unpaid": ["Zawadi"],
    }
    reply = approve(staff_client_a, seen((asha, "20000.00"), (juma, "0.00")))
    assert (reply.status_code, reply.json()["code"], reply.json()["params"]) == (
        400,
        "pay_run.earlier_month_open",
        {"month": "2026-10"},
    )


def test_a_debt_as_the_page_reads_it(
    staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember, asha: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A total below 0 is sent back as it was read, with its minus. December's line then says the debt and its month.
    with shop_context(shop_a):
        record_advance(asha, advance_id=uuid.uuid7(), date=MON, amount=Decimal("38000"), by=staff_a)
    assert staff_client_a.get(PAY, NOVEMBER).json()["total"] == "0.00"
    assert approve(staff_client_a, seen((asha, "-18000.00"))).status_code == 201
    line = staff_client_a.get(f"{PAY}{asha.pk}/", {"month": "2026-12"}).json()["worker"]
    assert (line["carried_from"], line["pay"]["carried"], line["total"]) == ("2026-11", "18000.00", "-18000.00")


def test_a_total_that_moved_is_refused_with_its_code(staff_client_a: APIClient, asha: StaffMember) -> None:
    reply = approve(staff_client_a, seen((asha, "19000.00")))
    assert (reply.status_code, reply.json()["code"]) == (400, "pay_run.totals_moved")


@pytest.mark.parametrize(
    ("sent", "field"),
    [
        ({"month": "2026-13"}, "month"),
        ({"month": None}, "month"),
        ({"seen": None}, "seen"),
        ({"seen": [{"staff": "x", "total": "1.00"}]}, "seen"),
        ({"id": str(uuid.uuid4())}, "id"),
    ],
)
def test_a_broken_request_is_refused(
    staff_client_a: APIClient, asha: StaffMember, sent: dict[str, Any], field: str
) -> None:
    reply = approve(staff_client_a, seen((asha, "20000.00")), **sent)
    assert reply.status_code == 400
    assert any(name.split(".")[0] == field for name in reply.json()["fields"])


def test_one_who_left_is_approved_alone_as_they_were_read(
    staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember, asha: StaffMember
) -> None:
    # Asha left on the 17th; on 1 December Baba approves her alone, before the others, whose day still waits.
    juma = paid(shop_a, "Juma")
    kept_day(juma, (ClockKind.IN, 7, 20), date=MON)
    assert staff_client_a.get(f"{PAY}{asha.pk}/", NOVEMBER).json()["to_approve"] is None
    with shop_context(shop_a):
        mark_left(asha, left_on=TUE, by=staff_a, reason="Amehama")
    page = staff_client_a.get(f"{PAY}{asha.pk}/", NOVEMBER).json()
    assert page["to_approve"] == {
        "earlier": None,
        "waiting": [],
        "no_rate": [],
        "still_clocked_in": False,
        "quiet_laptops": [],
        "came_unpaid": [],
    }
    made = str(uuid.uuid7())
    sent = {"id": made, "staff": str(asha.pk), "month": "2026-11", "seen": page["worker"]["total"]}
    reply = staff_client_a.post(SLIPS, sent, format="json")
    assert reply.status_code == 201
    said = {
        "id": made,
        "staff": str(asha.pk),
        "month": "2026-11",
        "total": "20000.00",
        "approved_by": staff_a.display_name,
        "approved_at": AT,
    }
    assert reply.json() == said
    again = staff_client_a.post(SLIPS, sent | {"seen": "1.00"}, format="json")
    assert (again.status_code, again.json()) == (201, said)
    after = staff_client_a.get(f"{PAY}{asha.pk}/", NOVEMBER).json()
    assert (after["worker"]["approval"], after["to_approve"]) == ({"by": staff_a.display_name, "at": AT}, None)
    # Another id, for the same worker and month, is another request: refused.
    other = staff_client_a.post(SLIPS, sent | {"id": str(uuid.uuid7())}, format="json")
    assert (other.status_code, other.json()["code"]) == (400, "payslip.already_approved")


def test_a_worker_of_another_shop_is_not_found(
    staff_client_a: APIClient, staff_b: StaffMember, asha: StaffMember
) -> None:
    # Another shop's worker, and an id no shop has, are refused alike (03 §5.4).
    answers = []
    for staff in (staff_b.pk, uuid.uuid7()):
        sent = {"id": str(uuid.uuid7()), "staff": str(staff), "month": "2026-11", "seen": "0.00"}
        reply = staff_client_a.post(SLIPS, sent, format="json")
        answers.append((reply.status_code, reply.json()["fields"]["staff"]))
    assert answers == [(400, ["does_not_exist"]), (400, ["does_not_exist"])]


def test_an_id_another_shop_holds_is_taken(
    staff_client_a: APIClient, shop_a: Shop, shop_b: Shop, staff_b: StaffMember, asha: StaffMember
) -> None:
    # Shop B's run and payslip, each one's id sent as a new one's from shop A: in use, and nothing of either is said,
    # nor anything kept (03 §5.4).
    with shop_context(shop_b):
        run = PayRun(shop=shop_b, month=dt.date(2026, 11, 1), created_by=staff_b)
        run.save()
        slip = Payslip(
            shop=shop_b,
            staff=staff_b,
            month=dt.date(2026, 11, 1),
            pay_run=run,
            total=Decimal("0.00"),
            created_by=staff_b,
        )
        slip.save()
    reply = approve(staff_client_a, seen((asha, "20000.00")), id=str(run.pk))
    assert (reply.status_code, reply.json()["fields"]) == (400, {"id": ["id.taken"]})
    with shop_context(shop_a):
        mark_left(asha, left_on=TUE, by=None, reason="Amehama")
    sent = {"id": str(slip.pk), "staff": str(asha.pk), "month": "2026-11", "seen": "20000.00"}
    reply = staff_client_a.post(SLIPS, sent, format="json")
    assert (reply.status_code, reply.json()["fields"]) == (400, {"id": ["id.taken"]})
    with shop_context(shop_a):
        assert not PayRun.objects.exists()
        assert not Payslip.objects.exists()


def test_another_shops_total_is_not_this_shops(
    staff_client_a: APIClient, staff_b: StaffMember, asha: StaffMember
) -> None:
    # A total sent for a worker the shop doesn't have is one more than it read: refused, saying nothing of whose it is.
    for staff in (staff_b.pk, uuid.uuid7()):
        sent = [*seen((asha, "20000.00")), {"staff": str(staff), "total": "0.00"}]
        reply = approve(staff_client_a, sent)
        assert (reply.status_code, reply.json()["code"]) == (400, "pay_run.totals_moved")


def test_the_other_pages_say_the_month_is_approved(
    staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember, asha: StaffMember
) -> None:
    # The worker's calendar, Hela ya chakula, Advansi and one advance: so each offers no change of November, and
    # December's do.
    with shop_context(shop_a):
        record_meal_money(shop_a, money_id=uuid.uuid7(), date=MON, amount=Decimal("1000"), by=staff_a)
        given = record_advance(asha, advance_id=uuid.uuid7(), date=MON, amount=Decimal("1000"), by=staff_a)

    def said(month: str) -> list[Any]:
        return [
            staff_client_a.get(f"{BASE}attendance-worker/{asha.pk}/", {"month": month}).json()["closed"],
            staff_client_a.get(f"{BASE}advances/", {"month": month}).json()["closed"],
            staff_client_a.get(f"{BASE}meal-money/", {"first": f"{month}-01", "last": f"{month}-02"}).json()[
                "closed_to"
            ],
        ]

    assert (said("2026-11"), said("2026-12")) == ([False, False, None], [False, False, None])
    assert staff_client_a.get(f"{BASE}advances/{given.pk}/").json()["closed"] is False
    total = staff_client_a.get(PAY, NOVEMBER).json()["workers"][0]["total"]
    assert approve(staff_client_a, seen((asha, total))).status_code == 201
    assert (said("2026-11"), said("2026-12")) == ([True, True, "2026-11-30"], [False, False, "2026-11-30"])
    # A span all to come says it too.
    to_come = staff_client_a.get(f"{BASE}meal-money/", {"first": "2027-02-01", "last": "2027-02-02"}).json()
    assert to_come["closed_to"] == "2026-11-30"
    assert staff_client_a.get(f"{BASE}advances/{given.pk}/").json()["closed"] is True


def test_the_pages_of_one_approved_alone_say_so(
    staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember, asha: StaffMember
) -> None:
    # Theirs alone: their calendar and their own advance; the month's list and the meal money stay open for the others.
    juma = paid(shop_a, "Juma")
    kept_day(juma, *FULL, date=MON)
    with shop_context(shop_a):
        hers = record_advance(asha, advance_id=uuid.uuid7(), date=MON, amount=Decimal("1000"), by=staff_a)
        his = record_advance(juma, advance_id=uuid.uuid7(), date=MON, amount=Decimal("1000"), by=staff_a)
        mark_left(asha, left_on=TUE, by=staff_a, reason="Amehama")
    sent = {"id": str(uuid.uuid7()), "staff": str(asha.pk), "month": "2026-11", "seen": "19000.00"}
    assert staff_client_a.post(SLIPS, sent, format="json").status_code == 201

    def closed(address: str, **query: str) -> Any:
        return staff_client_a.get(f"{BASE}{address}", query).json()["closed"]

    assert [closed(f"attendance-worker/{staff.pk}/", month="2026-11") for staff in (asha, juma)] == [True, False]
    assert [closed(f"advances/{row.pk}/") for row in (hers, his)] == [True, False]
    assert closed("advances/", month="2026-11") is False
    span = {"first": "2026-11-01", "last": "2026-11-30"}
    assert staff_client_a.get(f"{BASE}meal-money/", span).json()["closed_to"] is None


def test_an_approved_day_refuses_with_its_code(
    staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember, asha: StaffMember
) -> None:
    # As the sheets read it: beside the day's box where they ask for one, above the boxes where they don't.
    tapped(asha, *FULL, date=dt.date(2026, 12, 1))
    day = kept_day(asha, date=dt.date(2026, 11, 18))
    shown = staff_client_a.get(PAY, NOVEMBER).json()["workers"][0]["total"]
    waits = approve(staff_client_a, seen((asha, shown)))
    assert (waits.status_code, waits.json()["code"]) == (400, "pay_run.days_waiting")
    decided = {"choice": "half", "reason": "Aliumwa", "replaces": None}
    address = f"{BASE}attendance-days/{day.pk}/decide/"
    assert staff_client_a.post(address, decided, format="json").status_code == 200
    total = staff_client_a.get(PAY, NOVEMBER).json()["workers"][0]["total"]
    assert approve(staff_client_a, seen((asha, total))).status_code == 201
    late = staff_client_a.post(address, decided | {"choice": "on_time"}, format="json")
    assert (late.status_code, late.json()["code"]) == (400, "pay.day_approved")
    money = {"id": str(uuid.uuid7()), "date": "2026-11-16", "amount": "1000.00", "note": ""}
    beside = staff_client_a.post(f"{BASE}meal-money/", money, format="json")
    assert (beside.status_code, beside.json()["fields"]) == (400, {"date": ["pay.day_approved"]})
