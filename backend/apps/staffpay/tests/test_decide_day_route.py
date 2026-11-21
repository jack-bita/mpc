"""apps/staffpay/tests/test_decide_day_route.py — the route that decides a day, /api/v1/staffpay/attendance-days/{id}/
decide/ (ATT-6, 03 §5.10).

    POST attendance-days/{id}/decide/   {"choice": "late", "reason": "Alisahau kubonyeza Toka", "replaces": null}

Who may decide what, and how, is decide_day's, tested in test_decide_day.py; who may call the route is pinned in
backend/tests/test_route_permissions.py, beside every other route's. Here, the request and the answer as the sheet
sends and reads them, a day the route doesn't show, and the refusals as the sheet shows them. The client from
backend/conftest.py holds every key: shop A's owner, Staff A. The fine is a made-up 500 (rule 10). Fake data only.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop, Side
from apps.staffpay.models import AttendanceDay, ClockKind, DayStatus
from apps.staffpay.tests.days import MONDAY, job, kept_day, switch_on

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture(autouse=True)
def the_shops_day(shop_a: Shop, device_a: Device) -> None:
    # Shop A switched attendance on in January, with its fines, and keeps its laptop, where Juma's taps are made: the
    # route asks the book for the day before it decides it (days.py).
    switch_on(shop_a)


def decide_url(day_id: uuid.UUID | str) -> str:
    return f"/api/v1/staffpay/attendance-days/{day_id}/decide/"


def a_row_of(staff: StaffMember) -> AttendanceDay:
    # A day of another shop's, written past the book: shop A's route never reaches its book, as the guard finds no such
    # day for shop A, so its row alone is all these tests need.
    with shop_context(staff.shop_id):
        return AttendanceDay.objects.create(
            shop_id=staff.shop_id,
            staff=staff,
            date=MONDAY,
            status=DayStatus.ABSENT,
            fine=Decimal("0.00"),
            rules_used={"late_fine": "500.00"},
        )


def client_for(staff: StaffMember) -> APIClient:
    # Logged in as this person, at their shop, as the office screens call (backend/tests/test_route_permissions.py's).
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def sheet(choice: str = "late", reason: str = "Alisahau kubonyeza Toka", replaces: str | None = None) -> dict[str, Any]:
    # What the sheet sends: its choice, the reason typed, and when the decision it showed was made, or null for none.
    return {"choice": choice, "reason": reason, "replaces": replaces}


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    return job(shop_a, "Juma")


def test_a_decision_as_the_sheet_sends_it(staff_client_a: APIClient, juma: StaffMember) -> None:
    # Staff A, the owner, decides Juma's Monday late: the answer is the decision as the day shows it, its fine from the
    # day's own rules, his nickname, when and why. Sent again with that time, a change of mind is kept; sent again as
    # if no decision were there, it is refused, 409, as the page's copy is old.
    day = kept_day(juma)
    reply = staff_client_a.post(decide_url(day.pk), sheet(), format="json")
    assert reply.status_code == 200
    answer = reply.json()
    assert {key: answer[key] for key in ("status", "absence_type", "fine", "by", "reason")} == {
        "status": "late",
        "absence_type": None,
        "fine": "500.00",
        "by": "Staff A",
        "reason": "Alisahau kubonyeza Toka",
    }
    changed = staff_client_a.post(
        decide_url(day.pk), sheet("office_duty", "Alienda benki", replaces=answer["at"]), format="json"
    )
    assert changed.status_code == 200
    assert (changed.json()["status"], changed.json()["absence_type"]) == ("absent", "office_duty")
    stale = staff_client_a.post(decide_url(day.pk), sheet("half"), format="json")
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"


def test_refusals_come_beside_their_boxes(staff_client_a: APIClient, juma: StaffMember) -> None:
    # Juma's Monday with only a Toka: Amechelewa isn't offered, and the reason was left empty. Both refused at once,
    # each beside its box, with the codes the sheet says in words (ADR-0040).
    day = kept_day(juma, (ClockKind.OUT, 18, 45))
    reply = staff_client_a.post(decide_url(day.pk), sheet(reason="  "), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"choice": ["day.choice_not_offered"], "reason": ["day.reason_missing"]}


def test_a_request_the_sheet_never_sends_is_refused(staff_client_a: APIClient, juma: StaffMember) -> None:
    # A choice that is none of the six, a reason past 200 characters, and a time with no zone: refused by the
    # serializer, each beside its box, once the day is found.
    day = kept_day(juma)
    reply = staff_client_a.post(
        decide_url(day.pk), sheet("holiday", "x" * 201, replaces="2026-11-20T09:00:00"), format="json"
    )
    assert reply.status_code == 400
    assert reply.json()["fields"] == {
        "choice": ["invalid_choice"],
        "reason": ["max_length"],
        "replaces": ["invalid"],
    }


def test_ones_own_day_is_refused(shop_a: Shop, give_role: GiveRole, juma: StaffMember) -> None:
    # Meneja, a manager, holds the key, but his own Monday is the owner's to decide (Jack, ATT-6); Juma's he decides.
    meneja = job(shop_a, "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    reply = client_for(meneja).post(decide_url(kept_day(meneja).pk), sheet(), format="json")
    assert reply.status_code == 400
    assert reply.json()["code"] == "day.own"
    assert client_for(meneja).post(decide_url(kept_day(juma).pk), sheet(), format="json").status_code == 200


def test_another_shops_day_is_not_found(staff_client_a: APIClient, shop_b: Shop, side_b: Side) -> None:
    # Bahati's Monday is shop B's. Decided from shop A, it is "not found", exactly as a day no shop has: the answer
    # never tells that it exists (03 §5.4), and nothing is written. The tenancy sweep asks the same of every one of
    # A's days, as shop B.
    bahati_day = a_row_of(job(shop_b, "Bahati"))
    theirs = staff_client_a.post(decide_url(bahati_day.pk), sheet(), format="json")
    nobodys = staff_client_a.post(decide_url(uuid.uuid7()), sheet(), format="json")
    assert theirs.status_code == 404
    assert theirs.json() == nobodys.json()
    with shop_context(shop_b):
        assert AttendanceDay.objects.get(pk=bahati_day.pk).decided_status == ""


def test_another_shops_day_is_not_found_whatever_is_sent(staff_client_a: APIClient, shop_b: Shop) -> None:
    # An empty request, as the tenancy sweep sends one, about Bahati's day: "not found", as about a day no shop has. The
    # route looks for the day before it reads what was sent, so the guard is what answers, never the body's 400, which
    # would answer every day alike and hide whether the guard ever ran (ATT-6's review).
    bahati_day = a_row_of(job(shop_b, "Bahati"))
    theirs = staff_client_a.post(decide_url(bahati_day.pk), {}, format="json")
    nobodys = staff_client_a.post(decide_url(uuid.uuid7()), {}, format="json")
    assert theirs.status_code == 404
    assert theirs.json() == nobodys.json()
