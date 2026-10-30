"""apps/people/tests/test_device_authentication.py — the device key login's parts, one at a time (AUTH-2; 03 §5.4,
§5.9).

test_device_login.py checks the login through the device's routes, as the app meets it. These tests take it apart:

- the door (apps/people/login_doors.py), the one read that runs before any shop is open, reads a shop's id and
  nothing else, in one query;
- the login (apps/people/api/authentication.py) finds the device through the guard inside its own shop, closes that
  shop again after its read, and notes the device as seen, a blocked one too;
- a device is an Actor of its shop that is no person;
- the key's cookie never shows on Django's error pages.

Fake data only: the repo is public (03 §10).
"""

import secrets
from collections.abc import Callable

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.views.debug import SafeExceptionReporterFilter
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import NoShopSelected, current_shop, shop_context
from apps.people.api.authentication import DEVICE_KEY_COOKIE, DeviceKeyAuthentication
from apps.people.device_keys import hash_device_key
from apps.people.login_doors import shop_of_device_key
from apps.people.models import Device, StaffMember
from apps.people.services import block, confirm_pairing, start_pairing
from apps.shops.models import Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def manager_a(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    give_role(staff_a, RoleTemplate.MANAGER, None)
    return staff_a


def pair(by: StaffMember, side: Side) -> tuple[Device, str]:
    asked = start_pairing()
    with shop_context(by.shop_id):
        device = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side, by=by)
    return device, asked.key


def visit_with(key: str) -> Request:
    # A device's GET, as DRF hands it to a login class: the key in its cookie.
    django_request = APIRequestFactory().get("/api/devices/v1/me/")
    django_request.COOKIES[DEVICE_KEY_COOKIE] = key
    return Request(django_request)


def test_key_door_reads_only_a_shop_id(manager_a: StaffMember, side_a: Side) -> None:
    # The door reads past the guard, so it reads as little as a login needs: one shop's id, in one query, by the key's
    # hash. Everything else is read through the guard, once that shop is open.
    device, key = pair(manager_a, side_a)

    with CaptureQueriesContext(connection) as queries:
        found = shop_of_device_key(hash_device_key(key))

    assert found == device.shop_id
    [query] = queries.captured_queries
    # The one column, under the name values_list() gives it; then the table, and the hash, nothing else.
    assert query["sql"].startswith('SELECT "people_device"."shop_id" AS "shop_id" FROM "people_device" WHERE')
    assert '"people_device"."key_hash" =' in query["sql"]
    # A key no device holds, and one still waiting for a manager's yes, lead to no shop.
    assert shop_of_device_key(hash_device_key(secrets.token_urlsafe(32))) is None
    assert shop_of_device_key(hash_device_key(start_pairing().key)) is None


def test_login_finds_the_device_in_its_own_shop(manager_a: StaffMember, side_a: Side) -> None:
    # The login opens the device's shop for its own read, and closes it again: the route opens it for the whole visit,
    # with who acts (DeviceView). Nobody is the visit's person: a device is none.
    device, key = pair(manager_a, side_a)

    found = DeviceKeyAuthentication().authenticate(visit_with(key))

    assert found is not None
    user, logged_in = found
    assert logged_in.pk == device.pk
    assert not user.is_authenticated
    with pytest.raises(NoShopSelected):
        current_shop()


def test_device_is_an_actor_of_its_shop(manager_a: StaffMember, side_a: Side) -> None:
    # The Actor a device's visit names (apps/core/tenancy.py): its own shop, and no staff member, so office routes
    # refuse it and the edit history names nobody for it.
    device, _ = pair(manager_a, side_a)

    assert device.shop_id == manager_a.shop_id
    assert device.staff_id is None


def test_blocked_device_still_seen(manager_a: StaffMember, side_a: Side) -> None:
    # A blocked device is refused, and its call is still noted: a stolen phone that keeps calling shows when it last
    # did, on the manager's device list (02 v1.12).
    device, key = pair(manager_a, side_a)
    with shop_context(manager_a.shop_id):
        block(device, by=manager_a, reason="Imeibiwa kaunta")

    login = DeviceKeyAuthentication()
    with pytest.raises(AuthenticationFailed) as refused:
        login.authenticate(visit_with(key))

    assert refused.value.get_codes() == "device.blocked"
    assert login.seen
    with shop_context(manager_a.shop_id):
        assert Device.objects.get(pk=device.pk).last_seen_at is not None


def test_device_key_cookie_hidden_on_error_pages() -> None:
    # Django's error page (DEBUG) and its error reports list a failed request's cookies, and hide the value of any
    # whose name holds KEY, TOKEN or SECRET. The cookie's name holds "key" for that reason, so a crash in a device's
    # visit never prints its key.
    key = secrets.token_urlsafe(32)

    shown = SafeExceptionReporterFilter().get_safe_cookies(visit_with(key))

    assert set(shown) == {DEVICE_KEY_COOKIE}
    assert key not in str(shown[DEVICE_KEY_COOKIE])
    assert set(str(shown[DEVICE_KEY_COOKIE])) == {"*"}
