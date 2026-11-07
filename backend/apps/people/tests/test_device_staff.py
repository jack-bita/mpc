"""apps/people/tests/test_device_staff.py — a shop's device lists who works there, for the PIN screen's picker (UI-4;
03 §5.9).

A shared laptop shows a tile for each person, and the person taps their own before typing their PIN. Sync will carry
this list onto the device (SYNC-2, SYNC-10), but it comes later: until then the device asks for it online, with its key.

    the cookie holds              GET /api/devices/v1/staff/
    nothing, or a made-up key     401 not_authenticated
    a blocked device's key        401 device.blocked
    a paired device's key         200: its own shop's people at work, A to Z, as id, full name and nickname

Names only: no PIN's hash, no phone and no email, as the next person at the laptop could read them. Shop B's device
seeing none of shop A's people is the tenancy sweep's check (test_no_device_route_leaks_across_shops). Fake data only:
the repo is public (03 §10).
"""

from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, block, confirm_pairing, mark_left, set_pin, start_pairing, suspend
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The route and the cookie's name, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
STAFF = "/api/devices/v1/staff/"
KEY_COOKIE = "device_key"


def hire(shop: Shop, full_name: str, nickname: str, **contact: str) -> StaffMember:
    # A person with a job at the shop, made the way the app makes one (PPL-2).
    user = User.objects.create_user(full_name=full_name, **contact)
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=nickname, by=None)


def a_browser(key: str) -> APIClient:
    # A browser that holds this device's key in its cookie, as the device's does.
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    return client


@pytest.fixture
def manager(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    # The manager who confirms the laptop. They work at the shop, so they are on its list too: "Staff Demo Two".
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def paired(manager: StaffMember, side_a: Side) -> tuple[Device, str]:
    # A laptop paired the way the app pairs one: it asks and keeps its key, and the manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        device = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side_a, by=manager)
    return device, asked.key


def test_device_lists_its_shops_active_staff(
    shop_a: Shop, manager: StaffMember, paired: tuple[Device, str], staff_b: StaffMember
) -> None:
    # Hired out of order, so the answer's order is the route's, not the database's.
    juma = hire(shop_a, "Juma Mfano", "Juma")
    asha = hire(shop_a, "Asha Mfano", "Asha")
    # Three who can't log in today, so no tile: suspended, left, and switched off (User.is_active), as pin_login refuses
    # each of them (apps/people/services.py).
    neema = hire(shop_a, "Neema Mfano", "Neema")
    baraka = hire(shop_a, "Baraka Mfano", "Baraka")
    zuhura = hire(shop_a, "Zuhura Mfano", "Zuhura")
    with shop_context(shop_a):
        suspend(neema, by=None, reason="Kwa mfano")
        # Left the day the job began: a leaving date is never before the start, nor in the future.
        mark_left(baraka, left_on=baraka.started_on, by=None, reason="Kwa mfano")
    zuhura.user.is_active = False
    zuhura.user.save(update_fields=["is_active"])
    _, key = paired

    response = a_browser(key).get(STAFF)

    assert response.status_code == 200
    # A to Z by full name, as the picker shows them. Shop B's person (staff_b) isn't here: another shop's.
    assert response.json() == [
        {"id": str(asha.pk), "full_name": "Asha Mfano", "display_name": "Asha"},
        {"id": str(juma.pk), "full_name": "Juma Mfano", "display_name": "Juma"},
        {"id": str(manager.pk), "full_name": "Staff Demo Two", "display_name": "Staff A2"},
    ]


def test_staff_list_sends_names_only(shop_a: Shop, paired: tuple[Device, str]) -> None:
    # A person with a PIN, a phone and an email: the list shows none of them, nor whether she has a PIN, as a person
    # with none gets the same answers as a wrong PIN (03 §5.9).
    asha = hire(shop_a, "Asha Mfano", "Asha", phone="+255700000001", email="asha@example.com")
    with shop_context(shop_a):
        set_pin(asha, "4829", by=None)
    asha.refresh_from_db()
    _, key = paired

    response = a_browser(key).get(STAFF)

    assert {frozenset(row) for row in response.json()} == {frozenset({"id", "full_name", "display_name"})}
    text = response.content.decode()
    for secret in (asha.pin_hash, "+255700000001", "asha@example.com"):
        assert secret not in text


def test_blocked_device_gets_no_staff_list(manager: StaffMember, paired: tuple[Device, str]) -> None:
    device, key = paired
    with shop_context(manager.shop_id):
        block(device, by=manager, reason="Imeibiwa")

    response = a_browser(key).get(STAFF)

    assert response.status_code == 401
    assert response.json()["code"] == "device.blocked"


@pytest.mark.parametrize("key", [None, "not-a-key"])
def test_no_device_gets_no_staff_list(key: str | None, paired: tuple[Device, str]) -> None:
    # A browser that isn't a paired device: a stranger's, or a manager's own phone. A shop's people are only for its
    # devices.
    client = APIClient() if key is None else a_browser(key)

    response = client.get(STAFF)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
