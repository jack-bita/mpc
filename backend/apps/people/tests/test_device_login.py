"""apps/people/tests/test_device_login.py — a paired device logs in with its key (AUTH-2; 03 §5.4, §5.9; ADR-0018).

A device that a manager has paired holds its key in a cookie, `device_key`, which page scripts can't read. Every
request it sends carries the cookie, and the login (apps/people/api/authentication.py) turns it into the device:
found by the key's hash, in its own shop, which the visit then works for. These tests pin the card's rules, through
the device's own route, `GET /api/devices/v1/me/`, and the start of a pairing, `POST /api/devices/v1/pairing/`:

    the cookie holds              GET me                       POST pairing
    nothing                       401 not_authenticated        a new key (test_pairing_routes.py)
    a key no device has           401 not_authenticated        a new key
    a key still waiting           401 not_authenticated        a new key
    a paired device's key         200, its own shop            400 pairing.already_paired
    a blocked device's key        401 device.blocked           401 device.blocked
    a suspended shop's device     401 shop.suspended           401 shop.suspended

A device is a shop's machine, not a person, so its key opens no office route (CORE-6). Every change it sends needs
the CSRF token (ADR-0017), so another website can't send one in its name. Fake data only: the repo is public (03 §10).
"""

import secrets
from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, DeviceStatus, PairingRequest, StaffMember
from apps.people.services import block, confirm_pairing, start_pairing, unblock
from apps.shops.models import Shop, ShopStatus, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes and the cookie's name, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
ME = "/api/devices/v1/me/"
PAIRING = "/api/devices/v1/pairing/"
SIDES = "/api/v1/shops/sides/"
KEY_COOKIE = "device_key"


@pytest.fixture
def manager_a(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    # Shop A's manager on every side: the Manager role holds device.manage (apps/core/permissions.py).
    give_role(staff_a, RoleTemplate.MANAGER, None)
    return staff_a


@pytest.fixture
def manager_b(staff_b: StaffMember, side_b: Side, give_role: GiveRole) -> StaffMember:
    give_role(staff_b, RoleTemplate.MANAGER, None)
    return staff_b


def pair(by: StaffMember, side: Side, name: str = "Laptop ya Dawa") -> tuple[Device, str]:
    # A device paired the way the app pairs one: it asks and keeps its key, and the manager confirms its code.
    asked = start_pairing()
    with shop_context(by.shop_id):
        device = confirm_pairing(asked.request.code, name=name, home_side=side, by=by)
    return device, asked.key


def holding(key: str, *, csrf: bool = False) -> APIClient:
    # A browser that holds this key in its cookie, as the device's does. `csrf`: check CSRF as a real browser's
    # visit is checked; the test client skips that check unless asked.
    client = APIClient(enforce_csrf_checks=csrf)
    client.cookies[KEY_COOKIE] = key
    return client


def csrf_token(client: APIClient) -> str:
    # The CSRF token, as the app gets it: from the `csrftoken` cookie, which `me` hands out. The app sends it back in
    # the X-CSRFToken header; another website can't read our cookies, so it can't send the header.
    client.get(ME)
    return client.cookies["csrftoken"].value


def test_device_key_sets_current_shop(
    manager_a: StaffMember, side_a: Side, manager_b: StaffMember, side_b: Side, shop_a: Shop, shop_b: Shop
) -> None:
    # Each device's requests carry its own shop: the visit opens it, and the device is read through the guard there.
    _, key_a = pair(manager_a, side_a)
    _, key_b = pair(manager_b, side_b, name="Simu ya Pembejeo")

    answer_a = holding(key_a).get(ME)
    answer_b = holding(key_b).get(ME)

    assert answer_a.status_code == 200
    assert answer_a.json()["shop"]["id"] == str(shop_a.pk)
    assert answer_b.status_code == 200
    assert answer_b.json()["shop"]["id"] == str(shop_b.pk)


def test_blocked_device_refused(manager_a: StaffMember, side_a: Side) -> None:
    # A stolen device is stopped on its very next request (ADR-0018), with a code of its own, so the app can lock and
    # say why. 401, not 403: the key itself no longer opens anything.
    device, key = pair(manager_a, side_a)
    client = holding(key)
    assert client.get(ME).status_code == 200

    with shop_context(manager_a.shop_id):
        block(device, by=manager_a, reason="Imeibiwa kaunta")
    refused = client.get(ME)

    assert refused.status_code == 401
    assert refused.json()["code"] == "device.blocked"
    # DRF answers 401 only with a WWW-Authenticate header naming how to log in.
    assert refused.headers["WWW-Authenticate"]
    # Unblocked, the same key works again (Jack, AUTH-1).
    with shop_context(manager_a.shop_id):
        unblock(device, by=manager_a, reason="Polisi wameirudisha")
    assert client.get(ME).status_code == 200


def test_device_of_suspended_shop_refused(manager_a: StaffMember, side_a: Side, shop_a: Shop) -> None:
    # A suspended shop stops every way in, not only passwords (ADR-0038; AUTH-2 left this for the first card that checks
    # a shop's status).
    device, key = pair(manager_a, side_a)
    client = holding(key)
    assert client.get(ME).status_code == 200

    Shop.objects.filter(pk=shop_a.pk).update(status=ShopStatus.SUSPENDED)
    refused = client.get(ME)
    assert refused.status_code == 401
    assert refused.json()["code"] == "shop.suspended"
    # Even a new pairing: a device whose key already opens a device can't ask for a new one, here as elsewhere.
    asked_again = client.post(PAIRING)
    assert asked_again.status_code == 401
    assert asked_again.json()["code"] == "shop.suspended"
    # The device was not blocked, and its key still holds: the shop back, it works again.
    with shop_context(shop_a):
        assert Device.objects.get(pk=device.pk).status == DeviceStatus.ACTIVE
    Shop.objects.filter(pk=shop_a.pk).update(status=ShopStatus.ACTIVE)
    assert client.get(ME).status_code == 200


def test_device_requests_need_csrf(manager_a: StaffMember, side_a: Side) -> None:
    # A paired device's change without the CSRF token is refused, as a session's is (ADR-0017): its cookie goes with
    # every request to our address, even one another website makes the browser send.
    _, key = pair(manager_a, side_a)
    client = holding(key, csrf=True)

    without = client.post(PAIRING)
    assert without.status_code == 403
    assert "CSRF" in without.json()["message"]

    # With the token the request gets past the check, to the start's own rule: this key already opens a device.
    with_it = client.post(PAIRING, HTTP_X_CSRFTOKEN=csrf_token(client))
    assert with_it.status_code == 400
    assert with_it.json()["code"] == "pairing.already_paired"


def test_start_pairing_needs_csrf() -> None:
    # A new device has no key yet, so no login checks it; the start checks CSRF itself. Without it, another website
    # could make a paired laptop ask again, and the new cookie would wipe its working key for good.
    client = APIClient(enforce_csrf_checks=True)

    without = client.post(PAIRING)
    assert without.status_code == 403
    assert KEY_COOKIE not in without.cookies
    assert not PairingRequest.objects.exists()

    with_it = client.post(PAIRING, HTTP_X_CSRFTOKEN=csrf_token(client))
    assert with_it.status_code == 201
    assert KEY_COOKIE in with_it.cookies


def test_unknown_key_opens_nothing() -> None:
    # A key no device has, made up or from a database that was reset: no login, as with no cookie at all.
    answer = holding(secrets.token_urlsafe(32)).get(ME)

    assert answer.status_code == 401
    assert answer.json()["code"] == "not_authenticated"


def test_waiting_key_opens_nothing(manager_a: StaffMember, side_a: Side) -> None:
    # The key a device gets when it asks opens nothing until a manager says yes (03 §5.9); then it opens its device.
    asked = start_pairing()
    client = holding(asked.key)
    waiting = client.get(ME)
    assert waiting.status_code == 401
    assert waiting.json()["code"] == "not_authenticated"

    with shop_context(manager_a.shop_id):
        confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side_a, by=manager_a)

    assert client.get(ME).status_code == 200


def test_device_key_opens_no_office_route(manager_a: StaffMember, side_a: Side) -> None:
    # A device is a shop's machine, not a person: an office route records who made or changed each row, so a device
    # alone is refused there (CORE-6). Its cookie is not even read: office routes log in with a session only.
    _, key = pair(manager_a, side_a)

    answer = holding(key).get(SIDES)

    assert answer.status_code == 403
    assert answer.json()["code"] == "not_authenticated"
