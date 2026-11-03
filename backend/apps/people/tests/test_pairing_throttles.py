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
from django.conf import settings as django_settings
from django.core.cache import caches
from django.db import connection
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api.authentication import DEVICE_KEY_COOKIE
from apps.people.api.throttles import caller_network
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
    # Each test counts from nothing: its own writes to the caches roll back with it, and this clears anything left
    # there before it began, in every cache.
    for name in django_settings.CACHES:
        caches[name].clear()


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


def test_refused_requests_never_use_up_the_shops_starts() -> None:
    # A bad web page opened on any phone at the shop can make it call the pairing route: hidden images send GETs, a
    # hidden form a POST with no CSRF token, which only our own app holds. Each is refused, and none counts: only the
    # shop's own starts use up its ten, so the page can't stop the shop pairing a laptop.
    shop = APIClient(REMOTE_ADDR="203.0.113.10")
    tricked = APIClient(REMOTE_ADDR="203.0.113.10", enforce_csrf_checks=True)
    for _ in range(LIMIT):
        assert shop.get(PAIRING).status_code == 405
        assert tricked.post(PAIRING).status_code == 403

    assert shop.post(PAIRING).status_code == 201


def test_a_confirm_sent_again_is_never_slowed_down(baba: StaffMember, side_a: Side) -> None:
    # Nine wrong codes, then the right one: the laptop is paired, but the answer is lost, so the phone sends the same
    # confirm again. That is no new try of a code: it gets the laptop the first send made, as any repeat does
    # (CreateOnceMixin), never "wait".
    manager = client_of(baba)
    for _ in range(LIMIT - 1):
        manager.post(DEVICES, confirm_form("WRONGCDE", side_a))
    sent = confirm_form(start_pairing().request.code, side_a)
    first = manager.post(DEVICES, sent)

    again = manager.post(DEVICES, sent)

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()


def test_a_send_with_no_code_does_not_count(baba: StaffMember, side_a: Side) -> None:
    # A send with no code can guess none: refused for what it lacks, and not counted. The manager's ten tries stay
    # whole. (The tenancy sweep sends such creates too, with nothing but an id.)
    manager = client_of(baba)
    for _ in range(LIMIT + 1):
        assert manager.post(DEVICES, {"id": str(uuid.uuid7())}).json()["fields"]["pairing_code"] == ["required"]

    assert manager.post(DEVICES, confirm_form(start_pairing().request.code, side_a)).status_code == 201


def test_a_flood_of_starts_never_clears_a_managers_count(settings: Settings, baba: StaffMember, side_a: Side) -> None:
    # A full cache table loses a third of its rows, picked by their keys' ABC order, not their age (Django's
    # DatabaseCache), and a manager's key (throttle_pairing.confirm_...) sorts before every start's. Each limit counts
    # in a table of its own, so a flood of starts from many networks clears only starts: the manager's ten wrong codes
    # still stand. Every table is shrunk to three rows here, so a small flood fills it.
    settings.CACHES = {name: {**config, "OPTIONS": {"MAX_ENTRIES": 3}} for name, config in settings.CACHES.items()}
    manager = client_of(baba)
    for _ in range(LIMIT):
        manager.post(DEVICES, confirm_form("WRONGCDE", side_a))
    for network in range(1, 9):
        APIClient(REMOTE_ADDR=f"198.51.100.{network}").post(PAIRING)

    assert refused_as_throttled(manager.post(DEVICES, confirm_form(start_pairing().request.code, side_a)))


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


def test_start_without_cloudflares_header_counts_with_the_proxys_address(settings: Settings) -> None:
    # On the demo every request comes through Cloudflare, which writes its header. One without it did not, so nothing
    # it carries is trusted, X-Forwarded-For included: it counts with the address it came from, the proxy in front,
    # shared by every such request. Slowed down sooner, never let through on an address it wrote itself.
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    for fake in range(LIMIT):
        sent = APIClient(REMOTE_ADDR="198.51.100.20").post(PAIRING, HTTP_X_FORWARDED_FOR=f"192.0.2.{fake}")
        assert sent.status_code == 201

    last = APIClient(REMOTE_ADDR="198.51.100.20").post(PAIRING, HTTP_X_FORWARDED_FOR="192.0.2.99")
    assert refused_as_throttled(last)


def test_start_throttle_counts_an_ipv6_network_as_one() -> None:
    # Under IPv6 each phone has an address of its own, and a caller can take a new one in their own network, its /64,
    # whenever they like: so the network is counted as one, as an IPv4 shop's one address is. Another network is not
    # slowed down.
    for phone in range(1, LIMIT + 1):
        assert APIClient(REMOTE_ADDR=f"2001:db8:5:7::{phone:x}").post(PAIRING).status_code == 201

    assert refused_as_throttled(APIClient(REMOTE_ADDR="2001:db8:5:7:abcd::99").post(PAIRING))
    assert APIClient(REMOTE_ADDR="2001:db8:5:8::1").post(PAIRING).status_code == 201


def test_start_counts_keep_no_address() -> None:
    # The counts sit in a table, and in its backups, long after their hour. An address can name a person, so they keep a
    # fingerprint of the caller's network instead, made with the server's secret key: the same network always gives
    # the same one, and nobody without the key can tell which network it was.
    APIClient(REMOTE_ADDR="203.0.113.10").post(PAIRING)

    with connection.cursor() as cursor:
        cursor.execute("SELECT cache_key FROM throttle_pairing_start")
        keys = [key for (key,) in cursor.fetchall()]
    assert [key for key in keys if "pairing.start" in key]
    assert not [key for key in keys if "203.0.113" in key]


@pytest.mark.parametrize(
    ("address", "network"),
    [
        ("203.0.113.10", "203.0.113.10"),
        ("2001:db8:5:7:abcd::99", "2001:db8:5:7::/64"),
        ("::ffff:203.0.113.10", "203.0.113.10"),
        # What only a broken proxy would send: counted as it is, so it still has a limit.
        ("not-an-address", "not-an-address"),
    ],
)
def test_caller_network(address: str, network: str) -> None:
    assert caller_network(address) == network


def test_start_throttle_counts_an_ipv4_address_written_as_ipv6_as_itself() -> None:
    # A proxy may write an IPv4 caller in IPv6's form, ::ffff:203.0.113.10: the same caller, counted once.
    for _ in range(LIMIT):
        assert APIClient(REMOTE_ADDR="203.0.113.10").post(PAIRING).status_code == 201

    assert refused_as_throttled(APIClient(REMOTE_ADDR="::ffff:203.0.113.10").post(PAIRING))


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
