"""apps/demo/tests/test_demo_device.py — the one-tap demo: Jaribu demo makes a visitor's browser a device of the demo
shop, and hands it the sellers' PINs and the manager's login, only where the demo shop is the only shop (OPS-3, OPS-13,
BP15, ADR-0029).

    GET  /api/devices/v1/demo/open/   true only where the demo is open
    POST /api/devices/v1/demo/        one tap: a working device's key in the cookie, the PINs to show, and the
                                      manager's login for his tile to fill in

Shut in three cases, each proven here: a shop that isn't a demo (the real server's, or one beside the demo shop), no
demo sign (the real server never sets it), and no demo shop yet. Open, the tap makes a device through the two steps of
every pairing, refuses a browser whose key already works, gives yesterday's browser a new device, and counts against
the start of a pairing's limit.

The PINs and the manager's login are written here as the visitors read them, never imported from the seed, as in
test_seed_demo.py: a changed PIN or password must turn a test red. Fake data only: the repo is public (03 §10).
"""

from collections.abc import Iterator
from typing import Any

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.tenancy import shop_context
from apps.demo import services
from apps.demo.services import SHOP_CODE, DemoDevice, register_demo_device, seed_demo
from apps.people.device_keys import DEVICE_KEY_COOKIE, hash_device_key
from apps.people.models import Device, PairingRequest, StaffMember, User
from apps.people.services import add_staff, mark_left
from apps.shops.models import Shop, ShopKind
from apps.shops.selectors import shop_today
from apps.shops.services import NewSide, create_shop

pytestmark = pytest.mark.django_db

# Written out, not imported: a promise to the app (as in apps/people/tests/test_pairing_routes.py).
DEMO = "/api/devices/v1/demo/"
DEMO_OPEN = "/api/devices/v1/demo/open/"
PAIRING = "/api/devices/v1/pairing/"
ME = "/api/devices/v1/me/"
PIN_LOGIN = "/api/auth/pin-login/"
SESSION = "/_allauth/browser/v1/auth/session"
PASSWORD_LOGIN = "/_allauth/browser/v1/auth/login"
# The demo's public PINs, as visitors read them (README, docs/runbooks/demo.md).
PINS = {"Asha": "2580", "Baraka": "1470"}
# The manager's public login, as visitors read it there too.
MANAGER_LOGIN = "meneja@example.com"
MANAGER_PASSWORD = "jaribu-demo"
# The start of a pairing's limit, an hour, which the tap shares (config/settings/base.py).
LIMIT = 10


@pytest.fixture(autouse=True)
def demo_sign(settings: Settings) -> None:
    # Every test here runs where the sign is set, as on the demo; the one that proves the refusal takes it away.
    settings.DEMO_SEED = True


@pytest.fixture(autouse=True)
def fresh_content_types() -> Iterator[None]:
    # The seed's flush makes Django's content types again with new ids, and the test's rollback takes those back, so
    # the next test must not find them in memory (as in test_seed_demo.py).
    yield
    ContentType.objects.clear_cache()


@pytest.fixture
def demo_shop() -> Shop:
    seed_demo(fresh=True)
    return Shop.objects.get(kind=ShopKind.DEMO, code=SHOP_CODE)


def live_shop() -> Shop:
    return create_shop(name="Duka Halisi", code="HALISI", sides=[NewSide("D", "Dawa")])


def is_open() -> bool:
    answer = APIClient().get(DEMO_OPEN)
    assert answer.status_code == 200
    return bool(answer.json()["open"])


def devices_made() -> int:
    # Every shop's devices, read straight from PostgreSQL, past the tenancy guard: a refusal must make none anywhere.
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*) FROM {connection.ops.quote_name(Device._meta.db_table)}")
        return int(cursor.fetchone()[0])


def assert_refused_as_closed(answer: Any) -> None:
    # The refusal's code, and nothing made: no device, no waiting code, no key. Any: the test client adds json() to
    # its answers as it hands them back, which no type names.
    assert answer.status_code == 400
    assert answer.json()["code"] == "demo.closed"
    assert DEVICE_KEY_COOKIE not in answer.cookies
    assert PairingRequest.objects.count() == 0
    assert devices_made() == 0


def staff_ids(shop: Shop) -> dict[str, str]:
    with shop_context(shop):
        return {member.display_name: str(member.pk) for member in StaffMember.objects.all()}


# --- shut --------------------------------------------------------------------------------------------------------


def test_one_tap_demo_refused_with_live_shop(demo_shop: Shop) -> None:
    # ADR-0029's promise: a stranger's browser never joins a real shop. A live shop beside the demo shop, the likelier
    # accident, shuts the tap for the demo shop too, and the refusal says nothing of the live shop. Also the leak test
    # the tenancy sweep names for this route (DEVICE_ROUTES_WITHOUT_A_LOOK, backend/tests/sweep_lists.py).
    live = live_shop()

    answer = APIClient().post(DEMO)

    assert_refused_as_closed(answer)
    assert set(answer.json()) == {"code", "message", "fields", "params"}
    assert live.code.encode() not in answer.content
    assert str(live.pk).encode() not in answer.content
    assert not is_open()


def test_one_tap_demo_refused_with_only_a_live_shop() -> None:
    # The real server's own case, were the sign ever set there by mistake: a live shop and no demo shop.
    live_shop()

    assert_refused_as_closed(APIClient().post(DEMO))
    assert not is_open()


def test_one_tap_demo_refused_without_the_sign(demo_shop: Shop, settings: Settings) -> None:
    # The real server never sets DEMO_SEED: shut there even if its database somehow held only a demo shop.
    settings.DEMO_SEED = False

    assert_refused_as_closed(APIClient().post(DEMO))
    assert not is_open()


def test_one_tap_demo_refused_before_the_seed() -> None:
    # A demo database the seed hasn't filled yet: no shop to join.
    assert_refused_as_closed(APIClient().post(DEMO))
    assert not is_open()


def test_demo_open_answer_holds_nothing_of_a_shop(demo_shop: Shop) -> None:
    # Why the sweep may leave the open check out (NOT_SHOP_ROUTES): its answer is one true or false, on every server.
    answer = APIClient().get(DEMO_OPEN)

    assert answer.json() == {"open": True}


# --- open --------------------------------------------------------------------------------------------------------


def test_one_tap_demo_makes_a_working_device(demo_shop: Shop) -> None:
    # One tap, and the browser is a device of the demo shop: its key works at once, with no code and no manager's yes.
    browser = APIClient()

    answer = browser.post(DEMO)

    assert answer.status_code == 201
    key = answer.cookies[DEVICE_KEY_COOKIE].value
    # The key goes in the cookie only, never in the answer's body, which page scripts can read.
    assert key.encode() not in answer.content
    me = browser.get(ME)
    assert me.status_code == 200
    assert me.json()["shop"]["code"] == SHOP_CODE
    assert me.json()["home_side"]["code"] == "D"
    with shop_context(demo_shop):
        device = Device.objects.get()
        # Through the two steps of every pairing: its waiting request was confirmed, by the demo's manager.
        assert device.key_hash == hash_device_key(key)
        assert device.created_by == StaffMember.objects.get(display_name="Meneja")
        request = PairingRequest.objects.get()
        assert request.device == device
        assert device.name == f"Demo {request.code[:4]}-{request.code[4:]}"


def test_one_tap_demo_answers_the_seeds_pins(demo_shop: Shop) -> None:
    # The PIN screen shows each seller's PIN under their tile, found by their staff id. Meneja logs in with a password,
    # so has no PIN to show: his tile gets his login instead (the next test).
    ids = staff_ids(demo_shop)

    answer = APIClient().post(DEMO)

    assert answer.json()["pins"] == [{"staff_id": ids[name], "pin": pin} for name, pin in PINS.items()]


def test_one_tap_hands_over_the_managers_login(demo_shop: Shop) -> None:
    # OPS-13: Meneja has no PIN, so his tile opens the password login, filled with what the tap hands over. Only he:
    # Asha and Baraka log in with the PIN under their tiles, and get no login here. The answer holds these two lists
    # and nothing else, so nothing more of the shop's can slip into a stranger's browser.
    ids = staff_ids(demo_shop)

    answer = APIClient().post(DEMO)

    assert answer.json() == {
        "pins": [{"staff_id": ids[name], "pin": pin} for name, pin in PINS.items()],
        "logins": [{"staff_id": ids["Meneja"], "login": MANAGER_LOGIN, "password": MANAGER_PASSWORD}],
    }


def test_one_tap_demo_managers_login_logs_in(demo_shop: Shop) -> None:
    # What the login page fills in works: the visitor's browser, a device now, logs Meneja in with it, as Ingia sends
    # it. The email goes as `email`, as the app's login box sends an email (login-name.ts).
    browser = APIClient()
    login = browser.post(DEMO).json()["logins"][0]
    browser.get(SESSION)

    answer = browser.post(
        PASSWORD_LOGIN,
        {"email": login["login"], "password": login["password"]},
        format="json",
        HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value,
    )

    assert answer.status_code == 200


def test_one_tap_demo_pins_name_the_seeds_own_people(demo_shop: Shop) -> None:
    # Visitors share Meneja's password, so one may mark Asha as left and give a new person her nickname (unique among
    # current staff only). The PIN still names the seed's Asha, whose PIN it is: the tap neither fails for everyone
    # (two rows by one nickname) nor puts 2580 under someone it doesn't open.
    seeds_asha = staff_ids(demo_shop)["Asha"]
    with shop_context(demo_shop):
        asha = StaffMember.objects.get(pk=seeds_asha)
        mark_left(asha, left_on=shop_today(demo_shop), by=None, reason="Ameacha kazi")
        add_staff(shop=demo_shop, user=User.objects.create_user(full_name="Asha Mpya"), display_name="Asha", by=None)

    answer = APIClient().post(DEMO)

    assert answer.status_code == 201
    assert {"staff_id": seeds_asha, "pin": PINS["Asha"]} in answer.json()["pins"]


def test_one_tap_demo_leaves_out_someone_not_found(demo_shop: Shop) -> None:
    # A seller the tap can't find by the seed's nickname, renamed by a visitor, say: no PIN for her, and still a
    # device for this visitor, never a refusal for everyone until the next reset.
    ids = staff_ids(demo_shop)
    with shop_context(demo_shop):
        StaffMember.objects.filter(pk=ids["Baraka"]).update(display_name="Bakari")

    answer = APIClient().post(DEMO)

    assert answer.status_code == 201
    assert answer.json()["pins"] == [{"staff_id": ids["Asha"], "pin": PINS["Asha"]}]


def test_one_tap_demo_pins_log_in(demo_shop: Shop) -> None:
    # What the screen shows works: the new device logs Asha in with the PIN it was handed.
    browser = APIClient()
    pins = browser.post(DEMO).json()["pins"]

    answer = browser.post(PIN_LOGIN, {"staff": pins[0]["staff_id"], "pin": pins[0]["pin"]}, format="json")

    assert answer.status_code == 204


def test_one_tap_demo_refuses_a_working_device(demo_shop: Shop) -> None:
    # A second tap on a browser that already is a device must not swap its key: the first device would be lost.
    browser = APIClient()
    browser.post(DEMO)
    key = browser.cookies[DEVICE_KEY_COOKIE].value

    answer = browser.post(DEMO)

    assert answer.status_code == 400
    assert answer.json()["code"] == "pairing.already_paired"
    assert browser.cookies[DEVICE_KEY_COOKIE].value == key
    assert devices_made() == 1


def test_one_tap_demo_after_a_new_day(demo_shop: Shop) -> None:
    # Tomorrow's seed makes the shop again, and yesterday's device with it is gone: the browser's old key opens
    # nothing, so a tap gives it a new device, of the new shop (04 OPS-3).
    browser = APIClient()
    browser.post(DEMO)
    seed_demo(fresh=True)
    assert browser.get(ME).status_code == 401

    answer = browser.post(DEMO)

    assert answer.status_code == 201
    new_shop = Shop.objects.get(kind=ShopKind.DEMO)
    assert new_shop != demo_shop
    assert browser.get(ME).json()["shop"]["id"] == str(new_shop.pk)


def test_one_tap_demo_refused_confirm_leaves_nothing(demo_shop: Shop, monkeypatch: pytest.MonkeyPatch) -> None:
    # The promise of register_demo_device's one transaction: a confirm refused after the start takes the start back
    # too. No code is left waiting for a manager who will never type it, no device, no new key; and the code this
    # browser was already waiting with, from Sajili kifaa hiki, is not retired, so its manager can still confirm it.
    browser = APIClient()
    browser.post(PAIRING)
    waiting_key = browser.cookies[DEVICE_KEY_COOKIE].value
    waiting = PairingRequest.objects.get()

    def refused(*args: object, **kwargs: object) -> None:
        raise ValidationError("A device of this shop already has this name.", code="device.name_taken")

    monkeypatch.setattr(services, "confirm_pairing", refused)

    answer = browser.post(DEMO)

    assert answer.status_code == 400
    assert answer.json()["code"] == "device.name_taken"
    assert list(PairingRequest.objects.all()) == [waiting]
    waiting.refresh_from_db()
    assert waiting.expires_at > timezone.now()
    assert devices_made() == 0
    assert browser.cookies[DEVICE_KEY_COOKIE].value == waiting_key


def test_one_tap_demo_throttled_with_pairing(demo_shop: Shop) -> None:
    # Each tap makes a waiting request and a device, as a start of a pairing does, so both count against the one limit
    # per caller's network: a flood of taps can't fill the demo's device list. The address is one set aside for
    # documentation (RFC 5737).
    for _ in range(LIMIT // 2):
        assert APIClient(REMOTE_ADDR="203.0.113.10").post(DEMO).status_code == 201
        assert APIClient(REMOTE_ADDR="203.0.113.10").post(PAIRING).status_code == 201

    answer = APIClient(REMOTE_ADDR="203.0.113.10").post(DEMO)

    assert answer.status_code == 429
    assert answer.json()["code"] == "throttled"


def test_one_tap_demo_needs_the_csrf_token(demo_shop: Shop) -> None:
    # A page on another website must not make a visitor's browser join: the tap is a change, so CSRF-checked
    # (DeviceView). A real browser sends the token `me` handed out; this one sends none.
    answer = APIClient(enforce_csrf_checks=True).post(DEMO)

    assert answer.status_code == 403
    assert devices_made() == 0


def test_demo_device_never_prints_its_key(demo_shop: Shop) -> None:
    # A test's failure message, a log line or an error page that printed the result would otherwise show the key.
    made = register_demo_device()

    assert isinstance(made, DemoDevice)
    assert made.key not in repr(made)
