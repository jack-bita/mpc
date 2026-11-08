"""apps/people/tests/test_me.py — "who is here?": the app asks who is logged in, where, and what they may do (AUTH-4; 03
§5.9, §5.10).

The app asks this after any login, and each time it opens: `GET /api/auth/me/`.

    the session                                   the answer
    a PIN's badge                                 200: person, job, shop, device, home side, permissions per side,
                                                  and the minutes it lasts unused
    a password, on a person's own phone           200: the same, with no device and no home side, and the shop's
                                                  minutes, for a shared laptop's screen
    on a temporary password, either way           200, saying so, though the office routes stay closed
    a suspended person, a blocked device,
    a copied badge                                403, each with its code
    a device alone, nobody, or the superuser      403 not_authenticated

It holds no phone, no email and no hash. The tenancy sweep finds this route by itself, and calls it as shop B's person
(backend/tests/test_tenancy_sweep.py). Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from datetime import date

import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.core.api.base import SEES_THE_SIDE
from apps.core.permissions import Permission, RoleTemplate
from apps.core.settings_registry import IDLE_MINUTES
from apps.core.tenancy import shop_context
from apps.people.api.views import MeViewSet
from apps.people.models import Device, StaffMember, User
from apps.people.permissions import effective_permissions
from apps.people.services import block, confirm_pairing, grant_permission, set_pin, start_pairing, suspend
from apps.shops.models import Setting, Shop, Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes and the cookies' names, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
ME = "/api/auth/me/"
SIDES = "/api/v1/shops/sides/"
PIN_LOGIN = "/api/auth/pin-login/"
SESSION = "/_allauth/browser/v1/auth/session"
PASSWORD_LOGIN = "/_allauth/browser/v1/auth/login"
KEY_COOKIE = "device_key"
SESSION_COOKIE = "sessionid"

PIN = "4829"
PHONE = "+255712345678"
PASSWORD = "a-long-test-password"


def logged_in(staff: StaffMember, key: str) -> APIClient:
    # A browser that holds this device's key, after this person typed their PIN there.
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    assert client.post(PIN_LOGIN, {"staff": str(staff.pk), "pin": PIN}, format="json").status_code == 204
    return client


def on_a_phone(staff: StaffMember) -> APIClient:
    # A person's own phone, logged in with a password through allauth's route: it holds no device's key.
    user = User.objects.get(pk=staff.user_id)
    user.phone = PHONE
    user.set_password(PASSWORD)
    user.save()
    phone = APIClient()
    phone.get(SESSION)
    login = phone.post(
        PASSWORD_LOGIN,
        {"phone": PHONE, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=phone.cookies["csrftoken"].value,
    )
    assert login.status_code == 200
    return phone


@pytest.fixture
def manager(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def paired(manager: StaffMember, side_a: Side) -> tuple[Device, str]:
    # A device paired the way the app pairs one: it asks and keeps its key, and a manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        device = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side_a, by=manager)
    return device, asked.key


@pytest.fixture
def laptop(paired: tuple[Device, str]) -> Device:
    return paired[0]


@pytest.fixture
def laptop_key(paired: tuple[Device, str]) -> str:
    return paired[1]


@pytest.fixture
def asha(staff_a: StaffMember) -> StaffMember:
    with shop_context(staff_a.shop_id):
        return set_pin(staff_a, PIN, by=None)


@pytest.fixture
def vyakula(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


@pytest.fixture
def pembejeo(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="P", name="Pembejeo", by=None)


def test_me_lists_permissions_per_side(
    asha: StaffMember, laptop_key: str, side_a: Side, vyakula: Side, pembejeo: Side, give_role: GiveRole
) -> None:
    # Seller on Dawa, Cashier on Vyakula, nothing of its own on Pembejeo, and one key on every side.
    give_role(asha, RoleTemplate.SELLER, side_a)
    give_role(asha, RoleTemplate.CASHIER, vyakula)
    with shop_context(asha.shop_id):
        grant_permission(asha, Permission.STOCK_COUNT, side=None, by=None)

    permissions = logged_in(asha, laptop_key).get(ME).data["permissions"]

    with shop_context(asha.shop_id):
        # The same answers the rest of the system gets (apps/people/permissions.py), not a second copy of the rule.
        assert permissions["whole_shop"] == sorted(effective_permissions(asha, None))
        assert {side["code"]: side["permissions"] for side in permissions["sides"]} == {
            "D": sorted(effective_permissions(asha, side_a)),
            "F": sorted(effective_permissions(asha, vyakula)),
            "P": sorted(effective_permissions(asha, pembejeo)),
        }
    # Not looking at nothing: her one every-side key is in each list, and Dawa holds a seller's keys besides.
    assert permissions["whole_shop"] == [Permission.STOCK_COUNT]
    assert {side["code"]: side["permissions"] for side in permissions["sides"]}["P"] == [Permission.STOCK_COUNT]
    assert len(permissions["sides"][0]["permissions"]) > 1


def test_me_leaves_out_a_side_she_holds_nothing_on(
    asha: StaffMember, laptop_key: str, side_a: Side, vyakula: Side, give_role: GiveRole
) -> None:
    # She doesn't see Vyakula on any route (X1), so `me` doesn't name it either.
    give_role(asha, RoleTemplate.SELLER, side_a)

    permissions = logged_in(asha, laptop_key).get(ME).data["permissions"]

    assert [side["code"] for side in permissions["sides"]] == ["D"]
    # A key on Dawa alone opens nothing of the whole shop's (02 §5).
    assert permissions["whole_shop"] == []


def test_me_lists_every_side_for_a_key_on_every_side(
    asha: StaffMember, laptop_key: str, side_a: Side, vyakula: Side, give_role: GiveRole
) -> None:
    # The Owner role, given on every side: each side is listed, a side added later included.
    give_role(asha, RoleTemplate.OWNER, None)
    client = logged_in(asha, laptop_key)
    assert [side["code"] for side in client.get(ME).data["permissions"]["sides"]] == ["D", "F"]

    with shop_context(asha.shop_id):
        add_side(shop=asha.shop, code="P", name="Pembejeo", by=None)
    assert [side["code"] for side in client.get(ME).data["permissions"]["sides"]] == ["D", "F", "P"]


def test_me_names_who_and_where(asha: StaffMember, laptop: Device, laptop_key: str, side_a: Side) -> None:
    answer = logged_in(asha, laptop_key).get(ME)

    assert answer.status_code == 200
    data = answer.data
    assert set(data) == {
        "user",
        "staff",
        "shop",
        "device",
        "home_side",
        "must_change_password",
        "idle_minutes",
        "permissions",
    }
    # Her language and font too: the app applies both at every login, so they follow her to any device (UI-9).
    assert data["user"] == {
        "id": str(asha.user_id),
        "full_name": asha.user.full_name,
        "language": asha.user.language,
        "font": asha.user.font,
    }
    assert data["staff"] == {"id": str(asha.pk), "display_name": asha.display_name, "job_title": asha.job_title}
    assert data["shop"] == {"id": str(asha.shop_id), "name": asha.shop.name, "code": asha.shop.code}
    assert data["device"] == {"id": str(laptop.pk), "name": laptop.name, "code": laptop.code, "status": "active"}
    assert data["home_side"] == {"id": str(side_a.pk), "code": side_a.code, "name": side_a.name}
    assert data["must_change_password"] is False


def test_me_holds_no_secret(asha: StaffMember, laptop: Device, laptop_key: str) -> None:
    # 03 §5.9: PIN hashes and keys never leave the server; and a screen on a shared laptop doesn't need a phone.
    User.objects.filter(pk=asha.user_id).update(phone=PHONE, email="asha@example.com")
    body = logged_in(asha, laptop_key).get(ME).content.decode()
    with shop_context(asha.shop_id):
        asha.refresh_from_db()
        laptop.refresh_from_db()
    for secret in (PHONE, "asha@example.com", asha.pin_hash, laptop.key_hash, laptop_key):
        assert secret not in body


def test_me_on_a_phone_has_no_device(asha: StaffMember, laptop: Device) -> None:
    # A password on a person's own phone: no device (ADR-0038), so no home side either.
    answer = on_a_phone(asha).get(ME)

    assert answer.status_code == 200
    assert answer.data["staff"]["id"] == str(asha.pk)
    assert answer.data["device"] is None
    assert answer.data["home_side"] is None


def test_me_says_a_pin_sessions_idle_minutes(asha: StaffMember, laptop_key: str, shop_a: Shop) -> None:
    # The laptop's screen keeps an idle timer of its own (UI-4): selling uses the device's key, not the session, so the
    # server's clock alone would never lock the screen. `me` tells it how long, as the shop's setting gave the badge at
    # its login.
    with shop_context(shop_a):
        Setting.objects.create(shop=shop_a, key=IDLE_MINUTES.key, value="5", effective_from=date(2020, 1, 1))

    assert logged_in(asha, laptop_key).get(ME).data["idle_minutes"] == 5


def test_me_keeps_the_idle_minutes_its_session_began_with(asha: StaffMember, laptop_key: str, shop_a: Shop) -> None:
    # The owner changes the setting while Asha is logged in. Her badge keeps the minutes it began with, and the server
    # ends it then, so the screen's timer must say the same: the badge's own, not the setting's new value. From her
    # next login, the new value.
    client = logged_in(asha, laptop_key)
    with shop_context(shop_a):
        Setting.objects.create(shop=shop_a, key=IDLE_MINUTES.key, value="5", effective_from=date(2020, 1, 1))

    assert client.get(ME).data["idle_minutes"] == IDLE_MINUTES.default
    assert logged_in(asha, laptop_key).get(ME).data["idle_minutes"] == 5


def test_me_gives_a_password_the_shops_idle_minutes(asha: StaffMember, shop_a: Shop) -> None:
    # A password names no device (ADR-0038), so the server can't tell a manager's own phone from the shop's shared
    # laptop. The laptop locks its screen after the shop's minutes, whoever logged in there and however; a phone that
    # is only the person's own never shows that screen. The session itself lasts as Django's do (UI-4's review).
    with shop_context(shop_a):
        Setting.objects.create(shop=shop_a, key=IDLE_MINUTES.key, value="5", effective_from=date(2020, 1, 1))

    assert on_a_phone(asha).get(ME).data["idle_minutes"] == 5


def test_me_tells_about_the_temporary_password(asha: StaffMember, laptop_key: str, give_role: GiveRole) -> None:
    # Neema: her PIN works (Jack, 4 Nov 2026), and the app must be able to tell her why the office pages are closed, so
    # `me` alone stays open, and says so. It shows only who she is and what she may do once she has chosen.
    give_role(asha, RoleTemplate.OWNER, None)
    User.objects.filter(pk=asha.user_id).update(must_change_password=True)

    client = logged_in(asha, laptop_key)
    answer = client.get(ME)
    assert answer.status_code == 200
    assert answer.data["must_change_password"] is True
    refused = client.get(SIDES)
    assert (refused.status_code, refused.data["code"]) == (403, "password.must_change")

    # The same on her phone, where she logged in with the temporary password itself.
    phone = on_a_phone(asha)
    User.objects.filter(pk=asha.user_id).update(must_change_password=True)
    assert phone.get(ME).data["must_change_password"] is True
    refused = phone.get(SIDES)
    assert (refused.status_code, refused.data["code"]) == (403, "password.must_change")


def test_me_refuses_a_suspended_person(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    with shop_context(asha.shop_id):
        suspend(asha, by=None, reason="Amekosa kazi siku tatu")

    answer = client.get(ME)
    assert (answer.status_code, answer.data["code"]) == (403, "staff.suspended")


def test_me_refuses_a_blocked_device(asha: StaffMember, laptop: Device, laptop_key: str, manager: StaffMember) -> None:
    client = logged_in(asha, laptop_key)
    with shop_context(asha.shop_id):
        block(laptop, by=manager, reason="Imeibiwa")

    answer = client.get(ME)
    assert (answer.status_code, answer.data["code"]) == (403, "device.blocked")


def test_me_refuses_a_copied_badge(asha: StaffMember, laptop_key: str) -> None:
    thief = APIClient()
    thief.cookies[SESSION_COOKIE] = logged_in(asha, laptop_key).cookies[SESSION_COOKIE].value

    answer = thief.get(ME)
    assert (answer.status_code, answer.data["code"]) == (403, "session.wrong_device")


def test_me_needs_a_person(laptop_key: str, superuser_client: Client) -> None:
    # Nobody at all; a device alone, which is a shop's machine, not someone; and the superuser, who is nobody's staff.
    device_alone = APIClient()
    device_alone.cookies[KEY_COOKIE] = laptop_key
    for client in (APIClient(), device_alone):
        answer = client.get(ME)
        assert (answer.status_code, answer.data["code"]) == (403, "not_authenticated")
    assert superuser_client.get(ME).status_code == 403


def test_me_only_answers_reads(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    assert client.post(ME).status_code == 405
    assert client.patch(ME).status_code == 405


def test_me_names_its_permissions() -> None:
    # Whoever is logged in may ask who they are; it needs no key of its own. Written out in full, so a change to what
    # the route asks for is a change to this test too (backend rules).
    assert MeViewSet.action_permissions == {"me": SEES_THE_SIDE}
