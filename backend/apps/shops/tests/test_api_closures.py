"""apps/shops/tests/test_api_closures.py — the closures routes, /api/v1/shops/closures/ (ATT-8, 03 §5.10).

    GET  closures/                 the shop's today, and each active closure whose last day is today or later, soonest
                                   first (the page's list, ATT-9)
    POST closures/                 a new closure, through add_closure, with the id the client made (ADR-0007)
    POST closures/{id}/cancel/     Ondoa, with a reason, through cancel_closure
    POST closures/{id}/last-day/   a new last day, with a reason, through change_last_day

Who may do which is pinned in backend/tests/test_route_permissions.py, beside every other route's. Here the client from
backend/conftest.py holds every key. Fake data only: the repo is public.
"""

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.tenancy import shop_context
from apps.shops.models import Closure, ClosureStatus, Shop
from apps.shops.selectors import shop_today
from apps.shops.services import add_closure, cancel_closure

pytestmark = pytest.mark.django_db

CLOSURES = "/api/v1/shops/closures/"


def day(shop: Shop, offset: int) -> date:
    # A day counted from the shop's today: day(shop, -1) is yesterday.
    return shop_today(shop) + timedelta(days=offset)


def closure(shop: Shop, first: int, last: int, *, name: str, by: Any = None) -> Closure:
    # A closure saved straight to the table, so a list can show one that began in the past, which add_closure refuses.
    with shop_context(shop):
        row = Closure(shop=shop, first_day=day(shop, first), last_day=day(shop, last), name=name, created_by=by)
        row.full_clean()
        row.save()
        return row


def new_closure(shop: Shop, first: int, last: int, name: str = "Msiba wa bibi") -> dict[str, str]:
    # A new closure as the page sends it, with the id it made itself (ADR-0007).
    return {
        "id": str(uuid.uuid7()),
        "first_day": day(shop, first).isoformat(),
        "last_day": day(shop, last).isoformat(),
        "name": name,
    }


def test_closures_list_shows_those_to_come(staff_client_a: APIClient, staff_a: Any, shop_a: Shop) -> None:
    # The page's list: the funeral that began two days ago and runs to tomorrow, and Krismasi later, soonest first, each
    # with who added it, by the nickname the screens show. Not one already over, nor a cancelled one.
    funeral = closure(shop_a, -2, 1, name="Msiba wa bibi", by=staff_a)
    krismasi = closure(shop_a, 9, 10, name="Krismasi")
    closure(shop_a, -6, -3, name="Hesabu ya mwaka")
    with shop_context(shop_a):
        called_off = add_closure(shop_a, first_day=day(shop_a, 4), last_day=day(shop_a, 4), name="Sherehe", by=None)
        cancel_closure(called_off, reason="Imeahirishwa", by=None)

    answer = staff_client_a.get(CLOSURES).json()

    assert answer["today"] == shop_today(shop_a).isoformat()
    assert [row["id"] for row in answer["closures"]] == [str(funeral.pk), str(krismasi.pk)]
    first = answer["closures"][0]
    assert (first["first_day"], first["last_day"], first["name"], first["status"], first["added_by"]) == (
        day(shop_a, -2).isoformat(),
        day(shop_a, 1).isoformat(),
        "Msiba wa bibi",
        "active",
        "Staff A",
    )
    # Added by the system, as the seed adds the demo's: nobody's nickname.
    assert answer["closures"][1]["added_by"] is None


def test_create_closure_saves_and_answers_the_row(staff_client_a: APIClient, staff_a: Any, shop_a: Shop) -> None:
    sent = new_closure(shop_a, 0, 4)
    reply = staff_client_a.post(CLOSURES, sent, format="json")
    assert reply.status_code == 201
    body = reply.json()
    assert (body["id"], body["first_day"], body["last_day"], body["name"], body["status"], body["added_by"]) == (
        sent["id"],
        sent["first_day"],
        sent["last_day"],
        "Msiba wa bibi",
        "active",
        "Staff A",
    )


def test_create_closure_sent_twice_makes_one(staff_client_a: APIClient, shop_a: Shop) -> None:
    # A phone whose answer was lost sends the same closure again, with the same id: the stored one comes back, not a
    # clash with itself (CreateOnceMixin).
    sent = new_closure(shop_a, 1, 2)
    assert staff_client_a.post(CLOSURES, sent, format="json").status_code == 201
    again = staff_client_a.post(CLOSURES, sent, format="json")
    assert again.status_code == 201
    assert again.json()["id"] == sent["id"]
    with shop_context(shop_a):
        assert Closure.objects.filter(shop=shop_a).count() == 1


def test_create_closure_refused_answers_its_codes_beside_their_boxes(staff_client_a: APIClient, shop_a: Shop) -> None:
    # Yesterday, the last day before the first, and a name of spaces: every mistake at once, each beside its box, in the
    # service's own codes, which the page translates. A blank name is the service's to refuse, with its own sentence.
    sent = {**new_closure(shop_a, -1, -3), "name": "   "}
    reply = staff_client_a.post(CLOSURES, sent, format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {
        "first_day": ["closure.date_past"],
        "last_day": ["closure.ends_before_it_starts"],
        "name": ["closure.name_blank"],
    }


def test_create_closure_sharing_a_day_answers_its_code(staff_client_a: APIClient, shop_a: Shop) -> None:
    closure(shop_a, 3, 5, name="Krismasi")
    reply = staff_client_a.post(CLOSURES, new_closure(shop_a, 5, 6), format="json")
    assert reply.status_code == 400
    assert reply.json()["code"] == "closure.overlaps"


def test_cancel_closure_answers_the_row(staff_client_a: APIClient, shop_a: Shop) -> None:
    row = closure(shop_a, 3, 5, name="Krismasi")
    reply = staff_client_a.post(f"{CLOSURES}{row.pk}/cancel/", {"reason": "Imeahirishwa"}, format="json")
    assert reply.status_code == 200
    assert reply.json()["status"] == "cancelled"
    with shop_context(shop_a):
        assert Closure.objects.get(pk=row.pk).status == ClosureStatus.CANCELLED


def test_cancel_closure_refused_answers_its_code(staff_client_a: APIClient, shop_a: Shop) -> None:
    # A blank reason beside the reason's box; a started closure, a code of the whole action.
    row = closure(shop_a, -1, 2, name="Msiba wa bibi")
    blank = staff_client_a.post(f"{CLOSURES}{row.pk}/cancel/", {"reason": " "}, format="json")
    assert blank.status_code == 400
    assert blank.json()["fields"] == {"reason": ["closure.reason_required"]}
    started = staff_client_a.post(f"{CLOSURES}{row.pk}/cancel/", {"reason": "Tunafungua"}, format="json")
    assert started.status_code == 400
    assert started.json()["code"] == "closure.started"


def test_last_day_route_moves_it(staff_client_a: APIClient, shop_a: Shop) -> None:
    # The family finished yesterday: the shop opens today.
    row = closure(shop_a, -2, 2, name="Msiba wa bibi")
    sent = {"last_day": day(shop_a, -1).isoformat(), "reason": "Familia imemaliza"}
    reply = staff_client_a.post(f"{CLOSURES}{row.pk}/last-day/", sent, format="json")
    assert reply.status_code == 200
    assert reply.json()["last_day"] == day(shop_a, -1).isoformat()


def test_last_day_route_refused_answers_beside_the_box(staff_client_a: APIClient, shop_a: Shop) -> None:
    # Two days ago would open yesterday again, already past.
    row = closure(shop_a, -3, 2, name="Msiba wa bibi")
    sent = {"last_day": day(shop_a, -2).isoformat(), "reason": "Kosa"}
    reply = staff_client_a.post(f"{CLOSURES}{row.pk}/last-day/", sent, format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"last_day": ["closure.date_past"]}


def test_another_shops_closure_is_not_found(staff_client_b: APIClient, shop_a: Shop) -> None:
    # Shop B's manager can't cancel or move shop A's closure, nor learn that it exists: "not found", as for an id no
    # shop has, before what was sent is even read (03 §5.4).
    row = closure(shop_a, 3, 5, name="Krismasi")
    for action, sent in (
        ("cancel", {"reason": "Hapana"}),
        ("last-day", {"last_day": "2030-01-01", "reason": "Hapana"}),
    ):
        assert staff_client_b.post(f"{CLOSURES}{row.pk}/{action}/", sent, format="json").status_code == 404
    with shop_context(shop_a):
        assert Closure.objects.get(pk=row.pk).status == ClosureStatus.ACTIVE


def test_closures_list_is_one_answer_not_pages(staff_client_a: APIClient, shop_a: Shop) -> None:
    # A shop closes a handful of days a year, and the page shows them all at once.
    closure(shop_a, 3, 5, name="Krismasi")
    answer = staff_client_a.get(CLOSURES).json()
    assert set(answer) == {"today", "closures"}
