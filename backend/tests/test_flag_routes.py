"""backend/tests/test_flag_routes.py — the flags on their office pages, *Tofauti* (CTRL-4, 02 §13).

    GET  /api/v1/control/flags/?state=waiting     what waits, newest found first, in pages, and how many wait
    GET  /api/v1/control/flags/?state=closed      the closed ones

Each flag shows only to whoever may close it: `flag.review` on its side, or on the whole shop for a flag of no side, as
attendance's are. The rest are "not found". The rule itself, a side's rows shown behind a key of their own, is the
base's and has its own tests (backend/tests/test_route_permissions.py); these check that the flags keep it.

    shop      sides                    laptops            who asks
    MFANO     Dawa (D), Vyakula (F)    one on each side   Baba, the owner; a manager of one side; a seller

It lives outside `apps`, as the flags are `control`'s (layer 0), and what they are about, pushed records and taps, and
who may see them, roles, belong to higher apps, which its own tests may not import (ADR-0043). Fake data only: the repo
is public (03 §10).
"""

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.control.api.pagination import FlagPage
from apps.control.models import Flag, FlagKind
from apps.control.services import dismiss_flag, explain_flag, raise_flag, resolve_flag
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import grant_permission
from apps.shops.models import Shop, Side
from apps.shops.services import add_side
from apps.sync.models import PushedDocument, PushedStatus

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

FLAGS = "/api/v1/control/flags/"
SUNDAY_0752 = dt.datetime(2026, 11, 22, 4, 52, tzinfo=dt.UTC)  # 07:52 in Arusha


def client_for(staff: StaffMember) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


@pytest.fixture
def foods(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


@pytest.fixture
def foods_laptop(shop_a: Shop, foods: Side) -> Device:
    with shop_context(shop_a):
        return Device.objects.create(shop=shop_a, home_side=foods, name="Laptop ya Vyakula", code=2, key_hash="b" * 64)


@pytest.fixture
def baba(shop_a: Shop, staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.OWNER, None)
    return staff_a2


def pushed(device: Device, number: int, *, at: dt.datetime = SUNDAY_0752, **parts: Any) -> PushedDocument:
    # A pushed record's line in the answer log, as a flag of the push's names it (SYNC-5).
    with shop_context(device.shop_id):
        return PushedDocument.objects.create(
            shop_id=device.shop_id,
            device=device,
            device_seq=number,
            client_time=at,
            received_at=at + dt.timedelta(days=1),
            document_id=uuid.uuid7(),
            type="clock",
            schema_version=2,
            **{"status": PushedStatus.ACCEPTED, **parts},
        )


def flagged(line: PushedDocument, kind: FlagKind, *people: StaffMember, side: Side | None, **numbers: Any) -> Flag:
    with shop_context(line.shop_id):
        return raise_flag(kind=kind, subject=line, people=people, side=side, by=None, **numbers)


def shown(client: APIClient, **query: str) -> list[str]:
    return [line["id"] for line in client.get(FLAGS, query).json()["results"]]


def ids(*flags: Flag) -> list[str]:
    return [str(flag.pk) for flag in flags]


# --- The list


def test_the_list_shows_what_waits_newest_found_first(
    shop_a: Shop,
    side_a: Side,
    foods: Side,
    device_a: Device,
    foods_laptop: Device,
    staff_a: StaffMember,
    baba: StaffMember,
) -> None:
    # Juma, suspended, tapped on the Dawa laptop on Sunday; on Monday it sent record 43 before 42; then Vyakula's sent a
    # record the server couldn't keep. Newest found first: each says its kind, its side, who it names, and its record's
    # laptop and time, the time the laptop showed, not when the server found it.
    suspended = flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
    missing = flagged(pushed(device_a, 43), FlagKind.DEVICE_GAP, side=side_a, expected=42, actual=43)
    refused = flagged(
        pushed(foods_laptop, 1, status=PushedStatus.INVALID, reason="document.type_unknown"),
        FlagKind.INVALID_DOCUMENT,
        staff_a,
        side=None,
    )

    answer = client_for(baba).get(FLAGS).json()

    assert [line["id"] for line in answer["results"]] == ids(refused, missing, suspended)
    assert answer["waiting"] == 3
    assert answer["results"][2] == {
        "id": str(suspended.pk),
        "kind": "suspended_staff_activity",
        "status": "open",
        "side": "Dawa",
        "people": ["Staff A"],
        "device": "Laptop ya Dawa",
        "made_at": "2026-11-22T04:52:00Z",
        "raised_at": suspended.created_at.isoformat().replace("+00:00", "Z"),
    }
    # A flag that names nobody, and one of the whole shop.
    assert (answer["results"][1]["people"], answer["results"][0]["side"]) == ([], None)


def test_closed_flags_have_a_list_of_their_own(
    shop_a: Shop, side_a: Side, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # An explained flag still waits: only a close ends it (02 §13).
    opened, explained, resolved, dismissed = (
        flagged(pushed(device_a, number), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
        for number in range(1, 5)
    )
    with shop_context(shop_a):
        explain_flag(explained, text="Alikuja kuchukua vitu vyake", by=baba)
        resolve_flag(resolved, text="Tumezungumza naye", by=baba)
        dismiss_flag(dismissed, text="Alikuwa amerudishwa kazini", by=baba)
    client = client_for(baba)

    assert shown(client, state="waiting") == ids(explained, opened)
    assert shown(client, state="closed") == ids(dismissed, resolved)
    # No state asked: what waits, as the page opens on it.
    assert shown(client) == ids(explained, opened)
    assert client.get(FLAGS, {"state": "closed"}).json()["waiting"] == 2


def test_the_list_keeps_to_a_kind_and_a_side(
    shop_a: Shop,
    side_a: Side,
    foods: Side,
    device_a: Device,
    foods_laptop: Device,
    staff_a: StaffMember,
    baba: StaffMember,
) -> None:
    # *Chuja*: a side, the whole shop's own, a kind, or a side and a kind together. How many wait follows the filter,
    # as the tab counts the lines under it.
    dawa = flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
    dawa_gap = flagged(pushed(device_a, 43), FlagKind.DEVICE_GAP, side=side_a, expected=42, actual=43)
    vyakula = flagged(pushed(foods_laptop, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=foods)
    whole = flagged(pushed(foods_laptop, 2), FlagKind.INVALID_DOCUMENT, staff_a, side=None)
    client = client_for(baba)

    assert shown(client, side=str(side_a.pk)) == ids(dawa_gap, dawa)
    assert shown(client, side=str(foods.pk)) == ids(vyakula)
    assert shown(client, whole_shop="true") == ids(whole)
    assert shown(client, kind="suspended_staff_activity") == ids(vyakula, dawa)
    assert shown(client, kind="suspended_staff_activity", side=str(side_a.pk)) == ids(dawa)
    assert client.get(FLAGS, {"kind": "device_gap"}).json()["waiting"] == 1
    # A side no shop has, and another shop's, hold none, alike.
    assert shown(client, side=str(uuid.uuid7())) == []
    for wrong in ({"state": "open"}, {"kind": "no_such_kind"}, {"side": "Dawa"}):
        answer = client.get(FLAGS, wrong)
        assert (answer.status_code, list(answer.json()["fields"])) == (400, list(wrong)), wrong


def test_a_flag_shows_only_to_whoever_may_close_it(
    shop_a: Shop,
    side_a: Side,
    foods: Side,
    device_a: Device,
    foods_laptop: Device,
    staff_a: StaffMember,
    baba: StaffMember,
    give_role: GiveRole,
) -> None:
    # `flag.review` on Dawa alone: Dawa's flags, never Vyakula's, though she sells there too, and none of the whole
    # shop's (02 §13). Baba, on every side, sees the three.
    dawa = flagged(pushed(device_a, 1), FlagKind.PERMISSION_BREAK, baba, side=side_a)
    vyakula = flagged(pushed(foods_laptop, 1), FlagKind.PERMISSION_BREAK, baba, side=foods)
    whole = flagged(pushed(foods_laptop, 2), FlagKind.INVALID_DOCUMENT, baba, side=None)
    give_role(staff_a, RoleTemplate.SELLER, foods)

    # A seller holds it nowhere: refused, not shown an empty list that would say nothing waits.
    seller = client_for(staff_a).get(FLAGS)
    assert (seller.status_code, seller.json()["code"]) == (403, "permission_denied")

    with shop_context(shop_a):
        grant_permission(staff_a, Permission.FLAG_REVIEW, side=side_a, by=None)
    asha = client_for(staff_a)
    assert shown(asha) == ids(dawa)
    assert asha.get(FLAGS).json()["waiting"] == 1
    assert shown(asha, side=str(foods.pk)) == []
    assert shown(asha, whole_shop="true") == []
    assert shown(client_for(baba)) == ids(whole, vyakula, dawa)


def test_a_long_list_comes_in_pages(
    monkeypatch: pytest.MonkeyPatch, side_a: Side, device_a: Device, baba: StaffMember
) -> None:
    # *Onyesha zaidi* follows the page's own `next`, which keeps the state and the filters asked.
    monkeypatch.setattr(FlagPage, "page_size", 2)
    flags = [flagged(pushed(device_a, number), FlagKind.PERMISSION_BREAK, side=side_a) for number in range(1, 4)]
    client = client_for(baba)

    first = client.get(FLAGS, {"kind": "permission_break"}).json()
    second = client.get(first["next"]).json()

    assert [line["id"] for line in first["results"]] == ids(flags[2], flags[1])
    assert [line["id"] for line in second["results"]] == ids(flags[0])
    assert second["next"] is None
    assert (first["waiting"], second["waiting"]) == (3, 3)


def test_the_list_costs_the_same_queries_for_many(
    side_a: Side, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # One query per table for what the flags are about, never one per line (CTRL-1's note).
    def queries() -> int:
        with CaptureQueriesContext(
            connection,
        ) as asked:
            assert client_for(baba).get(FLAGS).status_code == 200
        return len(asked)

    flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
    for_one = queries()
    for number in range(2, 12):
        flagged(pushed(device_a, number), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)

    assert queries() == for_one
