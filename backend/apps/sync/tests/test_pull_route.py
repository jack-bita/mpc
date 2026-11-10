"""apps/sync/tests/test_pull_route.py — the address a shop device asks "what changed after N?" (SYNC-3; 03 §6.4).

    the cookie holds              GET /api/sync/v1/pull/?cursor=41
    nothing, or a made-up key     401 not_authenticated
    a blocked device's key        401 device.blocked
    a paired device's key         200: the changes after 41, the cursor to ask from next, whether more wait, the
                                  server's time and the oldest app that may still sync
    ... and a cursor that is no   400 invalid, under `cursor`
    change number ("abc", -1)

What a page holds is test_pull.py's; these test the route that sends it. Shop B's device seeing nothing of shop A's is
the tenancy sweep's check (test_no_device_route_leaks_across_shops), which calls this route with no cursor, so from the
start of the log. Fake data only: the repo is public (03 §10).
"""

import gzip
import json
from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import block, confirm_pairing, start_pairing
from apps.shops.models import Shop, Side
from apps.shops.services import add_side, rename_side
from apps.sync.api.serializers import CHANGE_RECORDS, PullAnswer
from apps.sync.registry import REGISTRY
from tests.change_log import last_line

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The route and the cookie's name, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
PULL = "/api/sync/v1/pull/"
KEY_COOKIE = "device_key"


def a_browser(key: str) -> APIClient:
    # A browser that holds this device's key in its cookie, as the device's does.
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    return client


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="D", name="Dawa", by=None)


@pytest.fixture
def manager(staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    # The manager who confirms the laptop, on every side.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def paired(manager: StaffMember, dawa: Side) -> tuple[Device, str]:
    # A Dawa laptop, paired the way the app pairs one: it asks and keeps its key, and the manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        device = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=dawa, by=manager)
    return device, asked.key


def test_pull_sends_the_changes_after_the_cursor(shop_a: Shop, dawa: Side, paired: tuple[Device, str]) -> None:
    # The owner renames Dawa on the office laptop; the Dawa laptop, at the mark, asks and gets the new name, and the
    # number to ask from next. Asked from there, it gets nothing more.
    _device, key = paired
    start = last_line(shop_a)
    with shop_context(shop_a):
        rename_side(dawa, version=dawa.version, name="Dawa Kuu", by=None)
    response = a_browser(key).get(PULL, {"cursor": start})
    assert response.status_code == 200
    page = response.json()
    assert list(page) == ["changes", "cursor", "has_more", "server_time", "min_app_version"]
    (change,) = page["changes"]
    assert {key: change[key] for key in ("seq", "entity", "id", "op")} == {
        "seq": start + 1,
        "entity": "side",
        "id": str(dawa.pk),
        "op": "upsert",
    }
    assert change["data"]["name"] == "Dawa Kuu"
    assert (page["cursor"], page["has_more"]) == (start + 1, False)
    assert a_browser(key).get(PULL, {"cursor": page["cursor"]}).json()["changes"] == []


def test_every_page_carries_the_server_time(shop_a: Shop, paired: tuple[Device, str]) -> None:
    # Done when: every page carries the server time, an empty one too, so a quiet shop's laptop still checks its clock
    # at every sync (03 §6.6). In UTC, as every time the API sends.
    _device, key = paired
    page = a_browser(key).get(PULL, {"cursor": last_line(shop_a)}).json()
    assert page["changes"] == []
    assert page["server_time"].endswith("Z")
    assert page["min_app_version"] is None


def test_a_pull_with_no_cursor_starts_from_the_beginning(shop_a: Shop, paired: tuple[Device, str]) -> None:
    # 0 means nothing read yet, as numbers start at 1 (SYNC-1), and a cursor left out means 0: the whole log, from its
    # first line, as a laptop that never bootstrapped would need it.
    _device, key = paired
    browser = a_browser(key)
    from_nothing = browser.get(PULL).json()
    assert from_nothing["changes"] == browser.get(PULL, {"cursor": 0}).json()["changes"]
    assert from_nothing["changes"][0]["seq"] == 1
    assert from_nothing["cursor"] == last_line(shop_a)


@pytest.mark.parametrize("cursor", ["abc", "-1", "1.5", "9223372036854775808", ""])
def test_a_cursor_that_is_no_change_number_is_refused(paired: tuple[Device, str], cursor: str) -> None:
    # A cursor is a change number the device was given, or 0: whole, from 0, and no bigger than the log's numbers can
    # be (a big integer). Anything else is a bug in the device, refused under its field, never read as some number,
    # which would send the device lines it has, or skip lines it hasn't, and hide the bug. A blank one too (`?cursor=`):
    # a device that lost its cursor and sent it anyway would otherwise read the whole log again at every sync, page
    # after page, and nobody would notice the cost. Left out altogether, it is 0 (the test above).
    _device, key = paired
    response = a_browser(key).get(PULL, {"cursor": cursor})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid"
    assert list(response.json()["fields"]) == ["cursor"]


def test_pull_needs_a_paired_device(manager: StaffMember, paired: tuple[Device, str], shop_a: Shop) -> None:
    # The shop's people and their keys travel on a page, as on the bootstrap, so a device's key alone opens it: no key,
    # a made-up one, or a person's own login gets nothing (DeviceView). A blocked laptop, a stolen one, say, gets
    # nothing either, and learns why.
    assert APIClient().get(PULL).json()["code"] == "not_authenticated"
    made_up = a_browser("a" * 43).get(PULL)
    assert (made_up.status_code, made_up.json()["code"]) == (401, "not_authenticated")
    phone = APIClient()
    phone.force_login(manager.user)
    from_a_phone = phone.get(PULL)
    assert (from_a_phone.status_code, from_a_phone.json()["code"]) == (401, "not_authenticated")
    device, key = paired
    with shop_context(shop_a):
        block(device, by=manager, reason="Laptop imeibiwa")
    blocked = a_browser(key).get(PULL)
    assert (blocked.status_code, blocked.json()["code"]) == (401, "device.blocked")


def test_pull_is_compressed(paired: tuple[Device, str]) -> None:
    # A page of 1,000 changes over a shop's slow line: gzip, for a client that says it reads it, as every browser does.
    # The same JSON once unpacked, but for the server's time, read again for each answer.
    _device, key = paired
    browser = a_browser(key)
    plain = browser.get(PULL)
    packed = browser.get(PULL, HTTP_ACCEPT_ENCODING="gzip")
    assert "Content-Encoding" not in plain.headers
    assert packed.headers["Content-Encoding"] == "gzip"
    # A cache in between must keep the two apart.
    assert "Accept-Encoding" in packed.headers["Vary"]
    unpacked: dict[str, Any] = json.loads(gzip.decompress(packed.content))
    assert {**unpacked, "server_time": None} == {**plain.json(), "server_time": None}


def test_pull_is_never_cached(paired: tuple[Device, str]) -> None:
    # A page holds the shop's people and their keys, so no browser cache, nor any proxy on the way, may keep a copy for
    # the next person; and a cached page would tell a laptop nothing changed when something did.
    _device, key = paired
    cache_control = a_browser(key).get(PULL).headers["Cache-Control"]
    assert {"no-store", "no-cache", "private"} <= {part.strip() for part in cache_control.split(",")}


def test_answer_shape_names_every_registry_table() -> None:
    # The answer's documented shape (the API schema, and the app's types made from it) names a change of each registry
    # table, by its code, with that table's own record as its data, so a table a later card adds can't reach devices
    # undocumented, or the other way round.
    assert list(PullAnswer().fields) == ["changes", "cursor", "has_more", "server_time", "min_app_version"]
    assert list(CHANGE_RECORDS) == list(REGISTRY)
    for code, entry in REGISTRY.items():
        fields = CHANGE_RECORDS[code]().fields
        assert list(fields) == ["seq", "entity", "id", "op", "data"]
        assert type(fields["data"]) is entry.serializer
        assert fields["data"].allow_null  # an archive carries no record
