"""apps/people/tests/test_pairing_throttles.py — pairing is slowed down for whoever asks too often (AUTH-5; 03 §5.10).

Two limits, 10 an hour each (config/settings/base.py): starts of a pairing, per address, and a manager's confirms,
per person. Request 11 is refused with 429 throttled, and `wait`, the seconds until the next try. Every request counts,
a refused one too: a guessed code is a refused confirm. The address is the one the proxy in front saw, never one the
caller wrote: Caddy's X-Forwarded-For entry, or, on the demo, Cloudflare's own header. A device's own calls, and a
manager's daily work on the device list, are never slowed down.

The counts live in Django's database cache, in PostgreSQL (ADR-0023). Fake data only: the repo is public (03 §10). So
every address here is one set aside for documentation, which no real network uses (RFC 5737; RFC 3849 for IPv6):
203.0.113.10 is the shop's own, 198.51.100.20 another network, and 192.0.2.x what a caller writes in a header.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.core.cache import cache
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api.authentication import DEVICE_KEY_COOKIE
from apps.people.models import PairingRequest, StaffMember, User
from apps.people.services import add_staff, confirm_pairing, start_pairing
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

PAIRING = "/api/devices/v1/pairing/"
ME = "/api/devices/v1/me/"
DEVICES = "/api/v1/people/devices/"
# Each limit, an hour (config/settings/base.py).
LIMIT = 10

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture(autouse=True)
def empty_cache() -> None:
    # Each test counts from nothing: its own writes to the cache roll back with it, and this clears anything left
    # there before it began.
    cache.clear()


@pytest.fixture
def baba(staff_a: StaffMember, give_role: GiveRole) -> StaffMember:
    give_role(staff_a, RoleTemplate.OWNER, None)
    return staff_a


def client_of(staff: StaffMember) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def confirm_form(code: str, side: Side) -> dict[str, str]:
    return {"id": str(uuid.uuid7()), "pairing_code": code, "name": "Laptop ya Dawa", "home_side": str(side.pk)}


def refused_as_throttled(answer: Any) -> bool:
    # 429, the API's code for it, and the whole seconds until the next try, for "jaribu tena baada ya dakika 6".
    # Any: the test client adds json() to its answers as it hands them back, which no type names.
    body = answer.json()
    return bool(answer.status_code == 429 and body["code"] == "throttled" and body["params"]["wait"] > 0)


def test_pairing_throttled() -> None:
    # Ten starts from the shop's one address in an hour are plenty: every device of a shop shares it. The eleventh is
    # refused, and says how long to wait. Another address is not slowed down: each address counts its own.
    shop_laptop = APIClient(REMOTE_ADDR="203.0.113.10")
    for _ in range(LIMIT):
        assert shop_laptop.post(PAIRING).status_code == 201

    assert refused_as_throttled(shop_laptop.post(PAIRING))
    assert APIClient(REMOTE_ADDR="198.51.100.20").post(PAIRING).status_code == 201


def test_confirm_throttled_per_person(baba: StaffMember, side_a: Side, shop_a: Shop, give_role: GiveRole) -> None:
    # Ten wrong codes in an hour: each is refused (pairing.code_unknown), and each counts, so the eleventh try is slowed
    # down even with the right code, which still waits. Another manager of the shop is not: each person counts their
    # own tries.
    manager = client_of(baba)
    for _ in range(LIMIT):
        assert manager.post(DEVICES, confirm_form("WRONGCDE", side_a)).json()["code"] == "pairing.code_unknown"
    code = start_pairing().request.code

    assert refused_as_throttled(manager.post(DEVICES, confirm_form(code, side_a)))
    assert PairingRequest.objects.get(code=code).device_id is None
    user = User.objects.create_user(full_name="Juma Demo")
    with shop_context(shop_a):
        juma = add_staff(shop=shop_a, user=user, display_name="Juma", by=None)
    give_role(juma, RoleTemplate.MANAGER, None)
    assert client_of(juma).post(DEVICES, confirm_form(code, side_a)).status_code == 201


def test_start_throttle_reads_the_address_behind_the_proxy() -> None:
    # Caddy, the one proxy in front (NUM_PROXIES), adds the address it saw at the end of X-Forwarded-For. A phone that
    # writes a new address of its own there each time only changes the entries before Caddy's: they are all one
    # address, and slowed down as one.
    for fake in range(LIMIT):
        sent = APIClient().post(PAIRING, HTTP_X_FORWARDED_FOR=f"192.0.2.{fake}, 203.0.113.10")
        assert sent.status_code == 201

    assert refused_as_throttled(APIClient().post(PAIRING, HTTP_X_FORWARDED_FOR="192.0.2.99, 203.0.113.10"))


def test_start_throttle_reads_cloudflares_header_on_the_demo(settings: Settings) -> None:
    # On the demo, Render's Cloudflare writes the caller's address in its own header, over any the caller sent
    # (render.yaml), and Render's two proxies make X-Forwarded-For's count unsure: so the header is read instead, and
    # what X-Forwarded-For says changes nothing.
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    for fake in range(LIMIT):
        sent = APIClient().post(PAIRING, HTTP_CF_CONNECTING_IP="203.0.113.10", HTTP_X_FORWARDED_FOR=f"192.0.2.{fake}")
        assert sent.status_code == 201

    assert refused_as_throttled(APIClient().post(PAIRING, HTTP_CF_CONNECTING_IP="203.0.113.10"))
    assert APIClient().post(PAIRING, HTTP_CF_CONNECTING_IP="198.51.100.20").status_code == 201


def test_only_pairing_is_throttled(baba: StaffMember, side_a: Side, shop_a: Shop) -> None:
    # A paired laptop asks `me` many times a day, and sync will too: never slowed down. Nor is a manager's work on the
    # device list: only a confirm can be a guess.
    asked = start_pairing()
    with shop_context(shop_a):
        laptop = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side_a, by=baba)
    device = APIClient()
    device.cookies[DEVICE_KEY_COOKIE] = asked.key
    manager = client_of(baba)

    assert {device.get(ME).status_code for _ in range(LIMIT + 1)} == {200}
    assert {manager.get(DEVICES).status_code for _ in range(LIMIT + 1)} == {200}
    assert {manager.get(f"{DEVICES}{laptop.pk}/").status_code for _ in range(LIMIT + 1)} == {200}
