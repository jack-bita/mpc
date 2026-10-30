"""apps/people/tests/test_pairing_routes.py — the two routes a device calls before and after a manager's yes (AUTH-2;
03 §5.9, §5.10).

    POST /api/devices/v1/pairing/   a new device asks to join: it gets a code to show, and its key in a cookie
    GET  /api/devices/v1/me/        a paired device learns its shop, its name, its code and its home side

The key travels only in the cookie, never in an answer's body, and the cookie is one page scripts can't read
(HttpOnly), that never goes to another website (SameSite Strict) or with anything but the API (`/api/`), and that
lasts as long as a browser lets one last (400 days), set again as the device is seen, so a device in use never
loses it. A device that already holds a working key never gets another: its key would be lost for good. The
manager's side of pairing, the confirm, is an office route (AUTH-5); here it is the service, as a manager's visit
would call it. Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.http import HttpResponseBase
from django.utils import timezone
from django.views.debug import ExceptionReporter
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api import views
from apps.people.device_keys import hash_device_key
from apps.people.models import Device, PairingRequest, StaffMember
from apps.people.services import NewPairing, block, confirm_pairing, start_pairing
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# Written out, not imported: a promise to the app and to the browser (as in test_device_login.py).
ME = "/api/devices/v1/me/"
PAIRING = "/api/devices/v1/pairing/"
KEY_COOKIE = "device_key"
# Chrome keeps a cookie 400 days at most, whatever the server asks for (RFC 6265bis), so the server asks for that.
COOKIE_DAYS = 400


@pytest.fixture
def manager_a(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    give_role(staff_a, RoleTemplate.MANAGER, None)
    return staff_a


def pair(by: StaffMember, side: Side, name: str = "Laptop ya Dawa") -> tuple[Device, str]:
    asked = start_pairing()
    with shop_context(by.shop_id):
        device = confirm_pairing(asked.request.code, name=name, home_side=side, by=by)
    return device, asked.key


def holding(key: str) -> APIClient:
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    return client


def keys_set(answer: object) -> set[str]:
    # The keys an answer put in the device's cookie, if any. An answer may send the device's own key again, to keep
    # the cookie from expiring (DeviceView); what must never happen is a new one in its place.
    cookies = getattr(answer, "cookies", {})
    return {cookie.value for name, cookie in cookies.items() if name == KEY_COOKIE}


def test_start_pairing_sets_the_key_cookie() -> None:
    answer = APIClient().post(PAIRING)

    assert answer.status_code == 201
    body = answer.json()
    # The code to show, and until when. Never the key: an answer's body is what page scripts can read.
    assert set(body) == {"code", "expires_at"}
    request = PairingRequest.objects.get(code=body["code"])
    cookie = answer.cookies[KEY_COOKIE]
    assert hash_device_key(cookie.value) == request.key_hash
    assert cookie.value.encode() not in answer.content
    # Out of page scripts' reach; never sent with another website's requests; sent with the API's requests only.
    assert cookie["httponly"]
    assert cookie["samesite"] == "Strict"
    assert cookie["path"] == "/api/"
    assert int(cookie["max-age"]) == COOKIE_DAYS * 24 * 60 * 60
    # Plain HTTP on a laptop and in tests (SESSION_COOKIE_SECURE is off there); see the next test.
    assert not cookie["secure"]


def test_key_cookie_secure_in_production(settings: Settings) -> None:
    # In production the cookie travels over HTTPS only, as the session's does (config/settings/prod.py), so nobody on
    # the shop's Wi-Fi can read it.
    settings.SESSION_COOKIE_SECURE = True

    answer = APIClient().post(PAIRING)

    assert answer.cookies[KEY_COOKIE]["secure"]


def test_paired_device_cannot_start_again(manager_a: StaffMember, side_a: Side) -> None:
    # A tap on "Sajili kifaa hiki" on a device that works, or a request another website made it send, must not swap its
    # key for a new one: the old key is in no other place, and the device would have to be paired again.
    device, key = pair(manager_a, side_a)
    client = holding(key)

    answer = client.post(PAIRING)

    assert answer.status_code == 400
    assert answer.json()["code"] == "pairing.already_paired"
    assert keys_set(answer) <= {key}
    assert PairingRequest.objects.count() == 1
    assert client.get(ME).json()["device"]["id"] == str(device.pk)


def test_blocked_device_cannot_start_again(manager_a: StaffMember, side_a: Side) -> None:
    # A blocked device keeps its key, so unblocking brings it back with what it holds (Jack, AUTH-1): asking again
    # would throw it away. Refused as any of its requests is.
    device, key = pair(manager_a, side_a)
    with shop_context(manager_a.shop_id):
        block(device, by=manager_a, reason="Imeibiwa kaunta")

    answer = holding(key).post(PAIRING)

    assert answer.status_code == 401
    assert answer.json()["code"] == "device.blocked"
    assert keys_set(answer) <= {key}
    assert PairingRequest.objects.count() == 1


def test_waiting_device_may_ask_again() -> None:
    # A key still waiting opens nothing, so a device whose code expired, or was never typed, simply asks again: a new
    # code, and a new key in place of the old, which never opened anything.
    client = APIClient()
    first = client.post(PAIRING)
    second = client.post(PAIRING)

    assert second.status_code == 201
    assert second.json()["code"] != first.json()["code"]
    assert keys_set(second) and keys_set(second) != keys_set(first)
    assert PairingRequest.objects.count() == 2


def test_start_pairing_keeps_the_key_out_of_error_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    # The key passes through the start route on its way to the cookie (04 v1.26's note). A crash there, here inside
    # Django's set_cookie, must not print it: Django's error page and its error reports list each function's
    # variables, the crashed one's too, where the key sits under a name of Django's own choosing.
    asked: list[NewPairing] = []

    def recorded() -> NewPairing:
        asked.append(start_pairing())
        return asked[0]

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("no cookie")

    monkeypatch.setattr(views, "start_pairing", recorded)
    monkeypatch.setattr(HttpResponseBase, "set_cookie", broken)
    with pytest.raises(RuntimeError) as crash:
        APIClient().post(PAIRING)

    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    shown = {name: str(value) for frame in frames for name, value in frame["vars"]}
    assert all(asked[0].key not in value for value in shown.values())
    # Where the key sits in a variable on its own, it shows as stars.
    assert set(shown["key"]) == {"*"}


def seen_long_ago(device: Device) -> None:
    # As if the device was last seen 6 minutes ago: past LAST_SEEN_EVERY, so its next request is noted again.
    with shop_context(device.shop_id):
        Device.objects.filter(pk=device.pk).update(last_seen_at=timezone.now() - timedelta(minutes=6))


def test_cookie_sent_again_when_seen(manager_a: StaffMember, side_a: Side) -> None:
    # Browsers drop a cookie 400 days after it was last set. A device in use is seen every few minutes, and each time
    # its answer sets the same key again with a fresh 400 days, so a working device never loses it.
    device, key = pair(manager_a, side_a)
    client = holding(key)

    first = client.get(ME)
    seen_long_ago(device)
    later = client.get(ME)

    for answer in (first, later):
        cookie = answer.cookies[KEY_COOKIE]
        assert cookie.value == key
        assert int(cookie["max-age"]) == COOKIE_DAYS * 24 * 60 * 60
        assert cookie["httponly"] and cookie["samesite"] == "Strict" and cookie["path"] == "/api/"


def test_cookie_not_sent_again_while_fresh(manager_a: StaffMember, side_a: Side) -> None:
    # Within 5 minutes of the last time, the device's call writes nothing, and its answer sets no cookie: the key
    # travels in an answer as seldom as it can.
    _, key = pair(manager_a, side_a)
    client = holding(key)
    client.get(ME)

    again = client.get(ME)

    assert again.status_code == 200
    assert KEY_COOKIE not in again.cookies


def test_blocked_device_keeps_its_cookie(manager_a: StaffMember, side_a: Side) -> None:
    # A blocked device is refused, and its key is still kept alive: unblocking brings back the same key, so the
    # records it holds can still arrive (Jack, AUTH-1), even after a long block.
    device, key = pair(manager_a, side_a)
    with shop_context(manager_a.shop_id):
        block(device, by=manager_a, reason="Imeibiwa kaunta")

    refused = holding(key).get(ME)

    assert refused.status_code == 401
    assert refused.cookies[KEY_COOKIE].value == key


def test_paired_device_learns_its_shop_and_code(manager_a: StaffMember, side_a: Side, shop_a: Shop) -> None:
    # 03 §5.9, step 3: the device learns its shop, and its code for receipt numbers (D7). It shows the shop's name, so
    # a code claimed by the wrong shop's manager is seen at once.
    device, key = pair(manager_a, side_a)

    answer = holding(key).get(ME)

    assert answer.status_code == 200
    assert answer.json() == {
        "device": {"id": str(device.pk), "name": "Laptop ya Dawa", "code": 1, "status": "active"},
        "home_side": {"id": str(side_a.pk), "code": "D", "name": "Dawa"},
        "shop": {"id": str(shop_a.pk), "name": "Duka la Mfano", "code": "MFANO"},
    }
    # Never the key's hash: it stays on the server (03 §5.9).
    assert device.key_hash.encode() not in answer.content


def test_me_hands_out_the_csrf_cookie() -> None:
    # The app asks `me` first, paired or not, and gets the CSRF token's cookie with the answer: it needs the token
    # for its first change, the start of a pairing (ADR-0017).
    answer = APIClient().get(ME)

    assert answer.status_code == 401
    assert "csrftoken" in answer.cookies
