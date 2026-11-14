"""apps/people/tests/test_device_health_route.py — the health page's route, GET /api/v1/people/devices/health/ (SYNC-14;
03 §5.17).

The office page *Hali ya vifaa* shows each laptop's last sync, the records still waiting on it, how far its clock is
from the server's, its app version, and its offline periods of the last week:

    Laptop ya Dawa (1)      synced 14:05, 3 waiting, clock -6 min, app 2026.11.1, offline 10:05-10:15 today
    Laptop ya Vyakula (2)   never synced yet: every report field empty, no periods

Who sees which laptops follows the device list (Jack, 2 Nov 2026): whoever works on a side sees its devices.

    Baba, the owner              Dawa, Vyakula
    Neema, manager of Vyakula    Vyakula
    Asha, seller on Dawa         Dawa

Fake data only: the repo is public (03 §10).
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import Outage, add_staff, confirm_pairing, record_outages, record_sync, start_pairing
from apps.shops.models import Shop, Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db

HEALTH = "/api/v1/people/devices/health/"

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def vyakula(shop_a: Shop, side_a: Side) -> Side:
    # Shop A's second side, beside Dawa (side_a).
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


@pytest.fixture
def baba(staff_a: StaffMember, give_role: GiveRole) -> StaffMember:
    # The owner: every key, on every side.
    give_role(staff_a, RoleTemplate.OWNER, None)
    return staff_a


def person(shop: Shop, name: str, role: RoleTemplate, side: Side, give_role: GiveRole) -> StaffMember:
    # A staff member of the shop with one role on one side.
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        staff = add_staff(shop=shop, user=user, display_name=name, by=None)
    give_role(staff, role, side)
    return staff


def client_of(staff: StaffMember) -> APIClient:
    # Logged in as this staff member, as the device route tests are (test_device_routes.py).
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def pair(by: StaffMember, side: Side, name: str) -> Device:
    code = start_pairing().request.code
    with shop_context(by.shop_id):
        return confirm_pairing(code, name=name, home_side=side, by=by)


@pytest.fixture
def laptops(baba: StaffMember, side_a: Side, vyakula: Side) -> tuple[Device, Device]:
    # The Dawa laptop (number 1) and the Vyakula one (number 2), paired by the owner.
    return pair(baba, side_a, "Laptop ya Dawa"), pair(baba, vyakula, "Laptop ya Vyakula")


def period(device: Device, went: datetime, came_back: datetime) -> uuid.UUID:
    # An offline period the laptop reported at a push, by its own clock (record_outages, as the push keeps it).
    outage = Outage(id=uuid.uuid7(), started_at=went, ended_at=came_back)
    with shop_context(device.shop_id):
        record_outages(device, [outage])
    return outage.id


def health(staff: StaffMember) -> list[dict[str, Any]]:
    answer = client_of(staff).get(HEALTH)
    assert answer.status_code == 200, answer.content
    rows: list[dict[str, Any]] = answer.json()
    return rows


def test_health_shows_each_laptops_last_report(baba: StaffMember, laptops: tuple[Device, Device]) -> None:
    # The Dawa laptop pushed at 14:05 with 3 records still waiting, its clock 6 minutes slow; the Vyakula one has
    # never pushed. Each by its number, one answer, no pages.
    dawa, vyakula = laptops
    at = timezone.now() - timedelta(minutes=20)
    with shop_context(dawa.shop_id):
        record_sync(dawa, at=at, unsent_count=3, app_version="2026.11.1", clock_error=timedelta(minutes=-6))

    rows = health(baba)

    assert [row["name"] for row in rows] == ["Laptop ya Dawa", "Laptop ya Vyakula"]
    first, second = rows
    assert parse_datetime(first.pop("last_synced_at")) == at
    assert first == {
        "id": str(dawa.pk),
        "name": "Laptop ya Dawa",
        "code": 1,
        "home_side": str(dawa.home_side_id),
        "status": "active",
        "unsent_count": 3,
        "app_version": "2026.11.1",
        "clock_error_seconds": -360,
        "outages": [],
    }
    # Never synced: nothing to show, rather than a 0 that would say "nothing waits" or "its clock is right".
    assert second == {
        "id": str(vyakula.pk),
        "name": "Laptop ya Vyakula",
        "code": 2,
        "home_side": str(vyakula.home_side_id),
        "status": "active",
        "last_synced_at": None,
        "unsent_count": None,
        "app_version": "",
        "clock_error_seconds": None,
        "outages": [],
    }


def test_health_shows_the_last_weeks_outages_newest_first_as_the_laptop_sent_them(
    baba: StaffMember, laptops: tuple[Device, Device]
) -> None:
    # Three cuts the Dawa laptop reported: one that ended 8 days ago, too old for the week; a long one that began 8
    # days ago and ended 6 days ago, which still counts; and one today whose end is before its start, as someone put
    # the laptop's clock back during it. The last is shown as the laptop said: the page says so.
    dawa, _vyakula = laptops
    now = timezone.now()
    period(dawa, now - timedelta(days=8, hours=1), now - timedelta(days=8))
    long_one = period(dawa, now - timedelta(days=8), now - timedelta(days=6))
    today = now - timedelta(hours=2)
    odd = period(dawa, today, today - timedelta(minutes=15))

    [row, _other] = health(baba)

    assert [period["id"] for period in row["outages"]] == [str(odd), str(long_one)]
    newest = row["outages"][0]
    assert parse_datetime(newest["started_at"]) == today
    assert parse_datetime(newest["ended_at"]) == today - timedelta(minutes=15)


def test_a_cut_ending_just_inside_the_week_counts(baba: StaffMember, laptops: tuple[Device, Device]) -> None:
    # The week is counted back from now, not from Monday: a cut that ended 6 days and 23 hours ago is in it.
    dawa, _vyakula = laptops
    ended = timezone.now() - timedelta(days=7) + timedelta(hours=1)
    kept = period(dawa, ended - timedelta(minutes=10), ended)

    [row, _other] = health(baba)

    assert [period["id"] for period in row["outages"]] == [str(kept)]


@pytest.mark.parametrize(
    ("who", "sees"),
    [
        ("baba", ["Laptop ya Dawa", "Laptop ya Vyakula"]),
        ("neema", ["Laptop ya Vyakula"]),
        ("asha", ["Laptop ya Dawa"]),
    ],
)
def test_health_shows_the_laptops_of_the_sides_the_person_sees(
    who: str,
    sees: list[str],
    baba: StaffMember,
    laptops: tuple[Device, Device],
    shop_a: Shop,
    side_a: Side,
    vyakula: Side,
    give_role: GiveRole,
) -> None:
    # As the device list (Jack, 2 Nov 2026): Neema, manager of Vyakula, sees the Vyakula laptop; Asha, a seller on
    # Dawa, sees the Dawa one, though she has no device.manage, as nothing here is a secret. A laptop of a side the
    # person doesn't see is left out, its offline periods with it.
    dawa, _vyakula = laptops
    period(dawa, timezone.now() - timedelta(hours=1), timezone.now() - timedelta(minutes=50))
    staff = {
        "baba": baba,
        "neema": person(shop_a, "Neema", RoleTemplate.MANAGER, vyakula, give_role),
        "asha": person(shop_a, "Asha", RoleTemplate.SELLER, side_a, give_role),
    }[who]

    rows = health(staff)

    assert [row["name"] for row in rows] == sees
    shown = [outage for row in rows for outage in row["outages"]]
    assert len(shown) == (1 if "Laptop ya Dawa" in sees else 0)


def test_health_reads_every_laptops_periods_at_once(
    baba: StaffMember, laptops: tuple[Device, Device], django_assert_max_num_queries: Any
) -> None:
    # A shop with five laptops, each cut off this morning: the page costs the same few queries as with one, as the
    # periods are read once for all of them, not once per laptop.
    dawa, vyakula = laptops
    for device in (dawa, vyakula):
        period(device, timezone.now() - timedelta(hours=3), timezone.now() - timedelta(hours=2))
    with django_assert_max_num_queries(12) as counted:
        health(baba)
    few = len(counted)
    for n in range(3):
        extra = pair(baba, dawa.home_side, f"Simu ya Dawa {n}")
        period(extra, timezone.now() - timedelta(hours=3), timezone.now() - timedelta(hours=2))
    with django_assert_max_num_queries(few):
        health(baba)
