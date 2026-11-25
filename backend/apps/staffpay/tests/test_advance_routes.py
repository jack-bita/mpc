"""apps/staffpay/tests/test_advance_routes.py — the routes of money given to a worker before payday,
/api/v1/staffpay/advances/ (WAGE-8, 03 §5.10).

    GET  advances/?month=2026-11   the month's, newest first, with their total and whom one may be typed for
    GET  advances/{id}/            one, for its own page
    POST advances/                 {"id": …, "staff": …, "date": "2026-11-10", "amount": "20000.00", "note": "Ada"}
    POST advances/{id}/void/       {"reason": "Sifuri moja zaidi"}

What may be typed, by whom, and how a mistake is mended are the services', tested in test_record_advance.py; what the
pay makes of one, in test_pay_month.py; who may call the routes is pinned in backend/tests/test_route_permissions.py,
beside every other route's. Here, the requests and the answers as the pages and the sheets send and read them, and the
refusals as the sheets show them. The client from backend/conftest.py holds every key: shop A's owner, Staff A. Today is
Wednesday 25 November 2026. The amounts are made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import StaffMember
from apps.people.services import hire_again, mark_left, suspend
from apps.shops.models import Shop, Side
from apps.staffpay.models import Advance, PayRate
from apps.staffpay.services import advances_month, record_advance
from apps.staffpay.tests.days import JAN_1, job

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

ADVANCES = "/api/v1/staffpay/advances/"
NOVEMBER = {"month": "2026-11"}
TENTH = dt.date(2026, 11, 10)
TODAY = dt.date(2026, 11, 25)
ARUSHA = dt.timezone(dt.timedelta(hours=3))


@pytest.fixture(autouse=True)
def the_25th(monkeypatch: pytest.MonkeyPatch) -> None:
    # 10:00 on Wednesday 25 November in Arusha, for every read of the clock.
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 25, 10, 0, tzinfo=ARUSHA))


def paid(shop: Shop, name: str) -> StaffMember:
    # Paid a made-up 10,000 a day since January (WAGE-1), written past set_pay_rate, whose maker would need the keys.
    staff = job(shop, name)
    with shop_context(shop):
        PayRate(shop=shop, staff=staff, daily_rate=Decimal("10000.00"), effective_from=JAN_1).save()
    return staff


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    return paid(shop_a, "Juma")


def row_of(staff: StaffMember, by: StaffMember, day: dt.date = TENTH, amount: str = "20000.00") -> Advance:
    # A row written past the service, which shop B's needs a key for: shop A's routes never reach it.
    with shop_context(staff.shop_id):
        row = Advance(
            shop_id=staff.shop_id, staff=staff, date=day, amount=Decimal(amount), note="Ada ya shule", created_by=by
        )
        row.save()
    return row


def sheet(staff: StaffMember, **changes: Any) -> dict[str, Any]:
    # What Andika advansi sends: the row's id, made on the phone (ADR-0007), the worker, the day, the amount as a string
    # (rule 3), and what it was for.
    sent = {"id": str(uuid.uuid7()), "staff": str(staff.pk), "date": "2026-11-10", "amount": "20000.00", "note": "Ada"}
    return sent | changes


def void_url(row_id: uuid.UUID | str) -> str:
    return f"{ADVANCES}{row_id}/void/"


def november(client: APIClient, month: str = "2026-11") -> Any:
    reply = client.get(ADVANCES, {"month": month})
    assert reply.status_code == 200, reply.json()
    return reply.json()


# The month.


def test_the_month_as_the_page_reads_it(
    shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember
) -> None:
    # Juma's 20,000 of the 10th, and 300,000 of the 16th typed by mistake and crossed out; Asha's 30,000 of the 16th.
    # Newest first, and the last typed first on one day; the crossed-out one still there (A2), and not in the total.
    # Money is strings (rule 3), and the shop's today is the server's to say.
    asha = paid(shop_a, "Asha")
    first = staff_client_a.post(ADVANCES, sheet(juma), format="json").json()
    wrong = staff_client_a.post(
        ADVANCES, sheet(juma, date="2026-11-16", amount="300000.00", note=""), format="json"
    ).json()
    hers = staff_client_a.post(ADVANCES, sheet(asha, date="2026-11-16", amount="30000.00"), format="json").json()
    staff_client_a.post(void_url(wrong["id"]), {"reason": "Sifuri moja zaidi"}, format="json")

    answer = november(staff_client_a)

    rows = answer.pop("rows")
    assert answer == {
        "month": "2026-11",
        "today": "2026-11-25",
        "total": "50000.00",
        # By name; only those paid by the day, so not Staff A, the owner.
        "workers": [
            {"staff": str(asha.pk), "display_name": "Asha", "left_on": None},
            {"staff": str(juma.pk), "display_name": "Juma", "left_on": None},
        ],
    }
    assert [row["id"] for row in rows] == [hers["id"], wrong["id"], first["id"]]
    assert rows[0] == hers
    assert rows[2] == first
    assert rows[1]["voided"].pop("at").endswith("Z")
    assert rows[1] == {
        "id": wrong["id"],
        "staff": str(juma.pk),
        "display_name": "Juma",
        "date": "2026-11-16",
        "amount": "300000.00",
        "note": "",
        "by": staff_a.display_name,
        "at": rows[1]["at"],
        "voided": {"by": staff_a.display_name, "reason": "Sifuri moja zaidi"},
    }


def test_one_days_come_last_typed_first(
    staff_client_a: APIClient, juma: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two of one day, by when the server took each, never by their ids: a phone whose clock is wrong makes an id that
    # says another moment (UUIDv7), and the list must not put its line elsewhere (the review).
    earlier_id, later_id = str(uuid.uuid7()), str(uuid.uuid7())
    for minute, sent_id in ((0, later_id), (5, earlier_id)):
        moment = dt.datetime(2026, 11, 25, 10, minute, tzinfo=ARUSHA)
        monkeypatch.setattr(timezone, "now", lambda moment=moment: moment)
        assert staff_client_a.post(ADVANCES, sheet(juma, id=sent_id), format="json").status_code == 201
    assert [row["id"] for row in november(staff_client_a)["rows"]] == [earlier_id, later_id]


def test_a_month_is_its_own_days(staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember) -> None:
    # The first and the last day of each, counted.
    for day in (dt.date(2026, 10, 1), dt.date(2026, 10, 31), dt.date(2026, 11, 1), TODAY):
        row_of(juma, staff_a, day)
    assert [row["date"] for row in november(staff_client_a, "2026-10")["rows"]] == ["2026-10-31", "2026-10-01"]
    assert [row["date"] for row in november(staff_client_a)["rows"]] == ["2026-11-25", "2026-11-01"]
    # A month to come, and the calendar's last, typed into the address: nothing to show, never a server error.
    for to_come in ("2026-12", "9999-12"):
        answer = november(staff_client_a, to_come)
        assert (answer["rows"], answer["total"]) == ([], "0.00")


@pytest.mark.parametrize("month", [None, "", "2026-13", "2026-1", "2026-11-01", "1999-12", "novemba"])
def test_no_month_is_refused_beside_its_name(staff_client_a: APIClient, month: str | None) -> None:
    reply = staff_client_a.get(ADVANCES, {} if month is None else {"month": month})
    assert reply.status_code == 400
    assert list(reply.json()["fields"]) == ["month"]


def test_whom_one_may_be_typed_for(shop_a: Shop, staff_a: StaffMember, staff_client_a: APIClient) -> None:
    # Those the shop pays by the day, who had a day of the job in the month, up to today: a suspended one; Neema, who
    # left on the 14th, with the day said, as a forgotten one of hers may still be typed. Not Halima, gone in October;
    # nor Zawadi, who starts on the 28th; nor the cook's helper with no daily pay; nor oneself. "asha" beside "Baraka".
    # And not Amani in October, who started on 5 November.
    asha, neema, halima, zawadi = (paid(shop_a, name) for name in ("asha", "Neema", "Halima", "Zawadi"))
    amani = paid(shop_a, "Amani")
    baraka = paid(shop_a, "Baraka")
    job(shop_a, "Msaidizi")
    with shop_context(shop_a):
        suspend(baraka, by=None, reason="Uchunguzi")
        mark_left(neema, left_on=dt.date(2026, 11, 14), by=None, reason="Amehama")
        mark_left(halima, left_on=dt.date(2026, 10, 31), by=None, reason="Amehama")
        StaffMember.objects.filter(pk=zawadi.pk).update(started_on=dt.date(2026, 11, 28))
        StaffMember.objects.filter(pk=amani.pk).update(started_on=dt.date(2026, 11, 5))
        # The owner, paid by the day too here: never offered their own (Jack: A).
        PayRate(shop=shop_a, staff=staff_a, daily_rate=Decimal("10000.00"), effective_from=JAN_1).save()
    assert november(staff_client_a)["workers"] == [
        {"staff": str(amani.pk), "display_name": "Amani", "left_on": None},
        {"staff": str(asha.pk), "display_name": "asha", "left_on": None},
        {"staff": str(baraka.pk), "display_name": "Baraka", "left_on": None},
        {"staff": str(neema.pk), "display_name": "Neema", "left_on": "2026-11-14"},
    ]
    october = november(staff_client_a, "2026-10")["workers"]
    assert [worker["display_name"] for worker in october] == ["asha", "Baraka", "Halima", "Neema"]


def test_the_person_is_never_offered_their_other_job(shop_a: Shop) -> None:
    # Baraka sold until the 14th and came back on the 16th as a manager (PPL-11): one person, two jobs, and neither's
    # advance is theirs to type (Jack: A). By the person, as record_advance asks. Juma is offered the old one.
    old = paid(shop_a, "Baraka")
    juma = paid(shop_a, "Juma")
    with shop_context(shop_a):
        mark_left(old, left_on=dt.date(2026, 11, 14), by=None, reason="Ameacha kazi")
        new = hire_again(old, display_name="Baraka", started_on=dt.date(2026, 11, 16), by=None)
        offered = {
            viewer.pk: [worker.staff_id for worker in advances_month(shop_a, TENTH, viewer=viewer).workers]
            for viewer in (new, juma)
        }
    assert offered == {new.pk: [juma.pk], juma.pk: [old.pk]}


def test_the_month_is_read_in_a_few_queries(
    shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember
) -> None:
    # However many advances: the names come in the rows' own read.
    asha = paid(shop_a, "Asha")
    for staff in (juma, asha):
        for day in range(1, 11):
            row_of(staff, staff_a, dt.date(2026, 11, day))
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        answer = advances_month(shop_a, dt.date(2026, 11, 1), viewer=staff_a)
    assert len(answer.rows) == 20
    assert len(queries) <= 2


def test_another_shop_is_refused(shop_a: Shop, shop_b: Shop, staff_a: StaffMember) -> None:
    # Asked inside another shop's visit, the guard would hide every row, and the month would be empty without a word:
    # so it fails loudly (ADR-0022). And a moment is no month.
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        advances_month(shop_a, dt.date(2026, 11, 1), viewer=staff_a)
    with shop_context(shop_a), pytest.raises(TypeError, match="advances_month"):
        advances_month(shop_a, dt.datetime(2026, 11, 1, tzinfo=dt.UTC), viewer=staff_a)


# One.


def test_one_as_its_own_page_reads_it(
    shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember
) -> None:
    # The very row of the list, and whether it is the asker's own, whom the page offers no Batilisha.
    made = staff_client_a.post(ADVANCES, sheet(juma), format="json").json()
    reply = staff_client_a.get(f"{ADVANCES}{made['id']}/")
    assert reply.status_code == 200
    assert reply.json() == {"advance": made, "own": False, "ready_void_reasons": []}


def test_ones_own_says_so(shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # Meneja (Staff A) may see what they were given, and the page offers no Batilisha on it.
    row = row_of(staff_a, staff_a2)
    assert staff_client_a.get(f"{ADVANCES}{row.pk}/").json()["own"] is True


def test_ones_own_is_the_persons(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, staff_a_again: StaffMember, give_role: GiveRole
) -> None:
    # Hired again (PPL-11): the old job's is the person's own too.
    row = row_of(staff_a, staff_a2)
    give_role(staff_a_again, RoleTemplate.OWNER, None)
    client = APIClient()
    client.force_authenticate(user=staff_a_again.user, token=staff_a_again)  # type: ignore[arg-type]
    with shop_context(shop_a):
        assert Advance.objects.get(pk=row.pk).staff_id != staff_a_again.pk
    reply = client.get(f"{ADVANCES}{row.pk}/")
    assert (reply.status_code, reply.json()["own"]) == (200, True)


def test_one_the_shop_doesnt_have_is_not_found(staff_client_a: APIClient, shop_b: Shop, staff_b: StaffMember) -> None:
    # An id no shop has, and shop B's own by its real id: "not found" alike (03 §5.4).
    theirs = row_of(paid(shop_b, "Jirani"), staff_b)
    replies = [staff_client_a.get(f"{ADVANCES}{row_id}/") for row_id in (uuid.uuid7(), theirs.pk)]
    assert [reply.status_code for reply in replies] == [404, 404]
    assert replies[0].json() == replies[1].json()


# Typing one.


def test_one_typed_as_the_sheet_sends_it(
    shop_a: Shop, staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember
) -> None:
    # The answer is the row as the pages show it. Sent again with the same id, as a phone whose answer was lost does,
    # the same row comes back, and only one is kept (CreateOnceMixin).
    sent = sheet(juma)
    reply = staff_client_a.post(ADVANCES, sent, format="json")
    assert reply.status_code == 201
    answer = reply.json()
    assert answer.pop("at").endswith("Z")
    assert answer == {**sent, "display_name": "Juma", "by": staff_a.display_name, "voided": None}
    again = staff_client_a.post(ADVANCES, {**sent, "amount": "90000.00"}, format="json")
    assert (again.status_code, again.json()["amount"]) == (201, "20000.00")
    with shop_context(shop_a):
        assert Advance.objects.count() == 1


def test_typing_refusals_come_beside_their_boxes(
    staff_client_a: APIClient, shop_a: Shop, staff_a2: StaffMember
) -> None:
    # One with no daily pay, a day to come, and an amount with cents: all at once, each beside its box, with the codes
    # the sheet says in words.
    reply = staff_client_a.post(ADVANCES, sheet(staff_a2, date="2026-11-26", amount="20000.50"), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {
        "staff": ["advance.not_paid_by_day"],
        "date": ["advance.in_future"],
        "amount": ["advance.amount_invalid"],
    }


def test_a_day_outside_the_job_and_too_many_zeros(staff_client_a: APIClient, juma: StaffMember) -> None:
    reply = staff_client_a.post(ADVANCES, sheet(juma, date="2025-12-31", amount="50000000"), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"date": ["advance.outside_job"], "amount": ["advance.amount_too_big"]}


def test_ones_own_is_refused_whole(staff_client_a: APIClient, shop_a: Shop, staff_a: StaffMember) -> None:
    # The sheet never offers it; a request that sends it all the same is refused, beside no box.
    with shop_context(shop_a):
        PayRate(shop=shop_a, staff=staff_a, daily_rate=Decimal("10000.00"), effective_from=JAN_1).save()
    reply = staff_client_a.post(ADVANCES, sheet(staff_a), format="json")
    assert (reply.status_code, reply.json()["code"]) == (400, "advance.own")


def test_what_the_sheet_never_sends_is_refused(staff_client_a: APIClient, juma: StaffMember) -> None:
    # An id that is no UUIDv7, an amount that is no number or has three places, a note past 200 characters, and a
    # missing worker or id: refused by the serializer, each beside its box.
    reply = staff_client_a.post(
        ADVANCES, sheet(juma, id=str(uuid.uuid4()), amount="elfu tano", note="u" * 201), format="json"
    )
    assert reply.status_code == 400
    assert set(reply.json()["fields"]) == {"id", "amount", "note"}
    places = staff_client_a.post(ADVANCES, sheet(juma, amount="5000.005"), format="json")
    assert set(places.json()["fields"]) == {"amount"}
    for name in ("id", "staff", "date", "amount"):
        without = sheet(juma)
        del without[name]
        assert staff_client_a.post(ADVANCES, without, format="json").json()["fields"] == {name: ["required"]}


def test_another_shops_worker_is_not_found(staff_client_a: APIClient, shop_b: Shop) -> None:
    # An id no shop has, and shop B's worker by their real id: refused alike, so nothing says that such a worker exists.
    for staff_id in (uuid.uuid7(), paid(shop_b, "Jirani").pk):
        sent = {"id": str(uuid.uuid7()), "staff": str(staff_id), "date": "2026-11-10", "amount": "20000.00"}
        reply = staff_client_a.post(ADVANCES, sent, format="json")
        assert (reply.status_code, reply.json()["fields"]) == (400, {"staff": ["does_not_exist"]})


def test_one_typed_with_no_note(staff_client_a: APIClient, juma: StaffMember) -> None:
    # Maelezo is optional: left out, or empty.
    without = sheet(juma)
    del without["note"]
    assert staff_client_a.post(ADVANCES, without, format="json").json()["note"] == ""
    assert staff_client_a.post(ADVANCES, sheet(juma, note=""), format="json").status_code == 201


def test_another_shops_row_is_never_handed_back(
    shop_b: Shop, staff_b: StaffMember, staff_client_a: APIClient, juma: StaffMember
) -> None:
    # Shop B's row, its id sent as a new row's from shop A: the id is in use, and nothing of the row is said (03 §5.4).
    theirs = row_of(paid(shop_b, "Jirani"), staff_b)
    reply = staff_client_a.post(ADVANCES, sheet(juma, id=str(theirs.pk)), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"id": ["id.taken"]}


# Crossing one out.


def test_one_crossed_out_as_the_sheet_sends_it(
    staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember
) -> None:
    # The answer is the row as its page shows it, struck through. Sent again, as a phone whose answer was lost does, the
    # same stamp comes back, never written twice.
    row = row_of(juma, staff_a)
    reply = staff_client_a.post(void_url(row.pk), {"reason": "Sifuri moja zaidi"}, format="json")
    assert reply.status_code == 200
    voided = reply.json()["voided"]
    assert (voided["by"], voided["reason"]) == (staff_a.display_name, "Sifuri moja zaidi")
    again = staff_client_a.post(void_url(row.pk), {"reason": "Sababu nyingine"}, format="json")
    assert again.json()["voided"] == voided


def test_crossing_out_with_no_reason_is_refused_beside_its_box(
    staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember
) -> None:
    row = row_of(juma, staff_a)
    reply = staff_client_a.post(void_url(row.pk), {"reason": "  "}, format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"reason": ["advance.reason_missing"]}


@pytest.mark.parametrize("sent", [{}, {"reason": "Sifuri moja zaidi"}, {"reason": 5}])
def test_another_shops_row_is_not_found_whatever_is_sent(
    shop_b: Shop, staff_b: StaffMember, staff_client_a: APIClient, sent: dict[str, Any]
) -> None:
    # Before the body is read, so an empty request never answers differently for a row another shop has (03 §5.4).
    theirs = staff_client_a.post(void_url(row_of(paid(shop_b, "Jirani"), staff_b).pk), sent, format="json")
    nobodys = staff_client_a.post(void_url(uuid.uuid7()), sent, format="json")
    assert theirs.status_code == nobodys.status_code == 404
    assert theirs.json() == nobodys.json()


def test_nothing_else_is_taken(staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember) -> None:
    # A ledger (rule 2): no address edits or deletes one.
    row = row_of(juma, staff_a)
    for send in (staff_client_a.put, staff_client_a.patch, staff_client_a.delete):
        assert send(f"{ADVANCES}{row.pk}/", {"amount": "1.00"}, format="json").status_code == 405
    with shop_context(juma.shop_id):
        assert Advance.objects.get(pk=row.pk).amount == Decimal("20000.00")


def test_on_the_demo_the_sheets_are_told_the_ready_reason(
    settings: Settings, staff_client_a: APIClient, staff_a: StaffMember, juma: StaffMember
) -> None:
    # A note typed and a reason typed are refused beside their boxes; the ready one is answered with the one, whose page
    # crosses it out.
    settings.DEMO_SEED = True
    reply = staff_client_a.post(ADVANCES, sheet(juma), format="json")
    assert reply.json()["fields"] == {"note": ["demo.no_note"]}
    with shop_context(juma.shop_id):
        row = record_advance(juma, advance_id=uuid.uuid7(), date=TENTH, amount=Decimal("20000"), by=staff_a)
    reply = staff_client_a.post(void_url(row.pk), {"reason": "Sifuri moja zaidi"}, format="json")
    assert reply.json()["fields"] == {"reason": ["demo.ready_reasons"]}
    (ready,) = staff_client_a.get(f"{ADVANCES}{row.pk}/").json()["ready_void_reasons"]
    assert staff_client_a.post(void_url(row.pk), {"reason": ready}, format="json").status_code == 200
