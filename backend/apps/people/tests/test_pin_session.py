"""apps/people/tests/test_pin_session.py — a PIN's badge is checked at every click (AUTH-4; 03 §5.9; X2).

A PIN login gives a browser a badge, a session that names a person, their shop and a device (test_pin_login.py). These
tests go through the real login, then an office route, /api/v1/shops/sides/, with the badge it gave:

    the badge's person, device and shop           an office route
    all as they were                              200, the device's shop's rows
    the number copied away from its device        403 session.wrong_device
    the shop suspended                            403 shop.suspended
    the device blocked                            403 device.blocked
    the person left, or switched off              403 not_authenticated
    the person given a new PIN                    403 not_authenticated
    no use for 15 minutes                         403 not_authenticated
    the person suspended                          403 staff.suspended; back again, 200, with no new login
    the person on a temporary password            403 password.must_change; once they choose their own, 200
    logged out                                    403 not_authenticated, at once

A badge never opens the Django admin, whoever's it is: the admin reads every shop's rows, and none of these checks runs
there. Logout must work whatever has happened to the person or the device: it asks only for the session and the CSRF
token.

Fake data only: the repo is public (03 §10).
"""

import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from unittest import mock

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone
from django.views.debug import ExceptionReporter
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import IDLE_MINUTES
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import (
    add_staff,
    block,
    confirm_pairing,
    mark_left,
    set_pin,
    set_temporary_password,
    start_pairing,
    suspend,
    unblock,
    unsuspend,
)
from apps.shops.models import Setting, Shop, ShopStatus, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes and the cookies' names, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
PIN_LOGIN = "/api/auth/pin-login/"
DEVICE_ME = "/api/devices/v1/me/"
SIDES = "/api/v1/shops/sides/"
ME = "/api/auth/me/"
LOGOUT = "/api/auth/logout/"
SESSION = "/_allauth/browser/v1/auth/session"
PASSWORD_LOGIN = "/_allauth/browser/v1/auth/login"
KEY_COOKIE = "device_key"
SESSION_COOKIE = "sessionid"

PIN = "4829"
PHONE = "+255712345678"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "a-long-test-password"
# Files whose frames hold what the test itself sent: not the server's, so not for it to hide.
TEST_CLIENT_FILES = ("django/test/client.py", "rest_framework/test.py", "test_pin_session.py")


def pair(manager: StaffMember, side: Side, name: str) -> tuple[Device, str]:
    # A device paired the way the app pairs one: it asks and keeps its key, and a manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        return confirm_pairing(asked.request.code, name=name, home_side=side, by=manager), asked.key


def logged_in(staff: StaffMember, key: str) -> APIClient:
    # A browser that holds this device's key, after this person typed their PIN there.
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    assert client.post(PIN_LOGIN, {"staff": str(staff.pk), "pin": PIN}, format="json").status_code == 204
    return client


def session_row(client: APIClient) -> Session:
    return Session.objects.get(session_key=client.cookies[SESSION_COOKIE].value)


def on_a_phone(staff: StaffMember) -> APIClient:
    # A person's own phone, logged in with a password through allauth's route: it holds no device's key.
    user = User.objects.get(pk=staff.user_id)
    user.phone = PHONE
    user.set_password(ADMIN_PASSWORD)
    user.save()
    phone = APIClient()
    phone.get(SESSION)
    login = phone.post(
        PASSWORD_LOGIN,
        {"phone": PHONE, "password": ADMIN_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=phone.cookies["csrftoken"].value,
    )
    assert login.status_code == 200
    return phone


def last_used(client: APIClient, *, seconds_ago: int, ends: datetime) -> None:
    # As if this badge was last used a while ago, and is that close to its end, with no waiting in the test.
    store = SessionStore(session_key=client.cookies[SESSION_COOKIE].value)
    store["pin_session_used"] = int(time.time()) - seconds_ago
    store.save()
    Session.objects.filter(session_key=store.session_key).update(expire_date=ends)


@pytest.fixture
def manager(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def paired(manager: StaffMember, side_a: Side) -> tuple[Device, str]:
    return pair(manager, side_a, "Laptop ya Dawa")


@pytest.fixture
def laptop(paired: tuple[Device, str]) -> Device:
    return paired[0]


@pytest.fixture
def laptop_key(paired: tuple[Device, str]) -> str:
    return paired[1]


@pytest.fixture
def asha(staff_a: StaffMember, give_role: GiveRole) -> StaffMember:
    # Every key on every side, so she sees the route's rows: what stops her in these tests is her badge alone.
    give_role(staff_a, RoleTemplate.OWNER, None)
    with shop_context(staff_a.shop_id):
        return set_pin(staff_a, PIN, by=None)


def test_pin_session_reaches_office_routes(asha: StaffMember, laptop_key: str) -> None:
    answer = logged_in(asha, laptop_key).get(SIDES)
    assert answer.status_code == 200
    assert [side["name"] for side in answer.data["results"]] == ["Dawa"]


def test_suspension_stops_the_next_click(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    with shop_context(asha.shop_id):
        suspend(asha, by=None, reason="Amekosa kazi siku tatu")

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "staff.suspended")

    # Brought back, she needs no new login (ADR-0038).
    with shop_context(asha.shop_id):
        unsuspend(asha, by=None, reason="Amerudi kazini")
    assert client.get(SIDES).status_code == 200


def test_blocked_device_stops_its_sessions(
    asha: StaffMember, laptop: Device, laptop_key: str, manager: StaffMember
) -> None:
    # A stolen laptop that someone left logged in: blocked from the owner's phone, it opens nothing (ADR-0018).
    client = logged_in(asha, laptop_key)
    with shop_context(asha.shop_id):
        block(laptop, by=manager, reason="Imeibiwa")

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "device.blocked")

    with shop_context(asha.shop_id):
        unblock(laptop, by=manager, reason="Imepatikana")
    assert client.get(SIDES).status_code == 200


def test_suspended_shop_stops_its_sessions(asha: StaffMember, laptop_key: str, shop_a: Shop) -> None:
    client = logged_in(asha, laptop_key)
    Shop.objects.filter(pk=shop_a.pk).update(status=ShopStatus.SUSPENDED)

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "shop.suspended")


def test_person_who_left_has_no_session(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    with shop_context(asha.shop_id):
        mark_left(asha, left_on=asha.started_on, by=None, reason="Amehamia mji mwingine")

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "not_authenticated")


def test_switched_off_person_has_no_session(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    User.objects.filter(pk=asha.user_id).update(is_active=False)

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "not_authenticated")


def test_session_copied_to_another_device_is_refused(
    asha: StaffMember, laptop_key: str, manager: StaffMember, side_a: Side
) -> None:
    # A badge works only beside its own device's key: someone who copies its number gets nothing from it.
    client = logged_in(asha, laptop_key)
    badge = client.cookies[SESSION_COOKIE].value
    _, other_key = pair(manager, side_a, "Laptop ya Vyakula")

    for key in (None, other_key):
        thief = APIClient()
        thief.cookies[SESSION_COOKIE] = badge
        if key:
            thief.cookies[KEY_COOKIE] = key
        answer = thief.get(SIDES)
        assert (answer.status_code, answer.data["code"]) == (403, "session.wrong_device")


def test_badge_beside_another_shops_key_is_refused(
    asha: StaffMember, laptop_key: str, staff_b: StaffMember, side_b: Side, give_role: GiveRole
) -> None:
    # Rule 1: the visit's shop comes through the device key's door, and must be the one the badge names. No row of
    # either shop is read for this answer, so a mismatch can't show anything of shop A's to shop B's device, or back.
    client = logged_in(asha, laptop_key)
    give_role(staff_b, RoleTemplate.MANAGER, None)
    _, key_b = pair(staff_b, side_b, "Simu ya Jingine")

    thief = APIClient()
    thief.cookies[SESSION_COOKIE] = client.cookies[SESSION_COOKIE].value
    thief.cookies[KEY_COOKIE] = key_b
    with (
        mock.patch("apps.people.selectors.Device") as device_table,
        mock.patch("apps.people.selectors.StaffMember") as job_table,
    ):
        answer = thief.get(SIDES)

    assert (answer.status_code, answer.data["code"]) == (403, "session.wrong_device")
    device_table.objects.select_related.assert_not_called()
    job_table.objects.select_related.assert_not_called()


def test_idle_session_ends(asha: StaffMember, laptop_key: str) -> None:
    # The end of the idle time, as the server's own row holds it: a copy of the cookie can't outlive it.
    client = logged_in(asha, laptop_key)
    Session.objects.filter(session_key=client.cookies[SESSION_COOKIE].value).update(
        expire_date=timezone.now() - timedelta(seconds=1)
    )

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "not_authenticated")


def test_use_keeps_the_session_alive(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    last_used(client, seconds_ago=61, ends=timezone.now() + timedelta(minutes=1))

    answer = client.get(SIDES)

    assert answer.status_code == 200
    # A whole idle time again, on the server's row and in the browser's cookie.
    assert session_row(client).expire_date > timezone.now() + timedelta(minutes=14)
    assert answer.cookies[SESSION_COOKIE]["max-age"] == 15 * 60


def test_short_idle_time_survives_use(asha: StaffMember, laptop_key: str, shop_a: Shop) -> None:
    # A shop may set 1 minute (IDLE_MINUTES). Pushed only once a minute, a badge in use would end before its first push:
    # someone clicking every few seconds would be logged out at the end of the first minute.
    with shop_context(shop_a):
        Setting.objects.create(shop=shop_a, key=IDLE_MINUTES.key, value="1", effective_from=date(2020, 1, 1))
    client = logged_in(asha, laptop_key)
    last_used(client, seconds_ago=31, ends=timezone.now() + timedelta(seconds=29))

    answer = client.get(SIDES)

    assert answer.status_code == 200
    assert session_row(client).expire_date > timezone.now() + timedelta(seconds=55)
    assert answer.cookies[SESSION_COOKIE]["max-age"] == 60


def test_session_is_saved_at_most_once_a_minute(asha: StaffMember, laptop_key: str) -> None:
    # A busy screen sends many requests, and one write each would be a table's worth of work for nothing.
    client = logged_in(asha, laptop_key)
    ends = timezone.now() + timedelta(minutes=14)
    last_used(client, seconds_ago=30, ends=ends)

    answer = client.get(SIDES)

    assert answer.status_code == 200
    assert session_row(client).expire_date == ends
    assert SESSION_COOKIE not in answer.cookies


def test_refused_click_does_not_keep_the_session_alive(asha: StaffMember, laptop_key: str) -> None:
    # A suspended person clicking away must not keep the badge going until someone brings them back.
    client = logged_in(asha, laptop_key)
    with shop_context(asha.shop_id):
        suspend(asha, by=None, reason="Amekosa kazi siku tatu")
    ends = timezone.now() + timedelta(minutes=1)
    last_used(client, seconds_ago=61, ends=ends)

    assert client.get(SIDES).status_code == 403
    assert session_row(client).expire_date == ends


def test_new_pin_ends_the_session(asha: StaffMember, laptop_key: str) -> None:
    # The owner suspects Juma knows Asha's PIN and gives her a new one: a login made with the old PIN ends with it, as a
    # new password ends a person's other sessions.
    client = logged_in(asha, laptop_key)
    with shop_context(asha.shop_id):
        set_pin(asha, "5930", by=None)

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "not_authenticated")


def test_pin_session_meets_the_password_mark(asha: StaffMember, laptop_key: str) -> None:
    # Neema forgot her password, and Baba typed her a temporary one. Her PIN still logs her in, so she can sell (Jack,
    # 4 Nov 2026); the office routes stay closed until she chooses her own.
    User.objects.filter(pk=asha.user_id).update(must_change_password=True)

    client = logged_in(asha, laptop_key)

    answer = client.get(SIDES)
    assert (answer.status_code, answer.data["code"]) == (403, "password.must_change")

    User.objects.filter(pk=asha.user_id).update(must_change_password=False)
    assert client.get(SIDES).status_code == 200


def test_temporary_password_ends_a_badge(
    asha: StaffMember, laptop_key: str, shop_a: Shop, side_a: Side, give_role: GiveRole
) -> None:
    # The real thing, not a mark set by hand. The owner types Juma a temporary password. A session holds a fingerprint
    # of the password it started with, even a PIN's, so his open badge ends, as his phone's would. His PIN still works,
    # and the next badge says he must choose his own.
    user = User.objects.create_user(full_name="Juma Demo", phone=PHONE)
    with shop_context(shop_a):
        juma = set_pin(add_staff(shop=shop_a, user=user, display_name="Juma", by=None), PIN, by=None)
    give_role(juma, RoleTemplate.SELLER, side_a)
    client = logged_in(juma, laptop_key)

    with shop_context(shop_a):
        set_temporary_password(juma, "a-long-temporary-password", by=asha, reason="Amesahau nenosiri")

    refused = client.get(SIDES)
    assert (refused.status_code, refused.data["code"]) == (403, "not_authenticated")

    again = logged_in(juma, laptop_key)
    assert again.get(ME).data["must_change_password"] is True
    refused = again.get(SIDES)
    assert (refused.status_code, refused.data["code"]) == (403, "password.must_change")


def test_password_login_over_a_badge_changes_nothing(asha: StaffMember, laptop_key: str) -> None:
    # allauth answers that someone is already logged in here, and the badge goes on as it was, with its checks: a
    # password typed at a shared laptop never turns a badge into something else.
    on_a_phone(asha)
    client = logged_in(asha, laptop_key)
    badge = client.cookies[SESSION_COOKIE].value

    answer = client.post(
        PASSWORD_LOGIN,
        {"phone": PHONE, "password": ADMIN_PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )

    assert answer.status_code == 409
    assert client.cookies[SESSION_COOKIE].value == badge
    assert "pin_session" in session_row(client).get_decoded()
    assert client.get(SIDES).status_code == 200


def test_pin_session_names_its_shop(asha: StaffMember, laptop_key: str, shop_b: Shop, side_b: Side) -> None:
    # Someone with jobs at two shops: a password can't tell which one a visit is for, and is refused until AUTH-7. A PIN
    # can: it was typed on this device, of this shop.
    with shop_context(shop_b):
        add_staff(shop=shop_b, user=asha.user, display_name="Asha", by=None)

    answer = logged_in(asha, laptop_key).get(SIDES)

    assert answer.status_code == 200
    assert [side["name"] for side in answer.data["results"]] == ["Dawa"]


def test_pin_session_changes_need_csrf(asha: StaffMember, laptop_key: str) -> None:
    # The badge's cookie goes with every request to our address, even one another website makes the laptop send.
    client = APIClient(enforce_csrf_checks=True)
    client.cookies[KEY_COOKIE] = laptop_key
    client.get(DEVICE_ME)
    login = client.post(
        PIN_LOGIN,
        {"staff": str(asha.pk), "pin": PIN},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert login.status_code == 204

    answer = client.post(SIDES, {"code": "F", "name": "Vyakula"}, format="json")
    assert (answer.status_code, answer.data["code"]) == (403, "permission_denied")


def test_device_key_stays_out_of_error_reports(asha: StaffMember, laptop_key: str) -> None:
    # Each visit of a PIN session holds the device's key for a moment, to compare it: a crash there must not print it.
    client = logged_in(asha, laptop_key)
    crashing = mock.patch("apps.people.selectors.hash_device_key", side_effect=MemoryError("out of memory"))
    with crashing, pytest.raises(MemoryError) as crash:
        client.get(SIDES)
    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    on_the_server = [frame for frame in frames if not frame["filename"].endswith(TEST_CLIENT_FILES)]
    assert on_the_server
    shown = [
        (frame["function"], name)
        for frame in on_the_server
        for name, value in frame["vars"]
        if laptop_key in str(value)
    ]
    assert shown == []


def test_logout_ends_the_session_at_once(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    badge = client.cookies[SESSION_COOKIE].value

    answer = client.post(LOGOUT)

    assert answer.status_code == 204
    assert not answer.content
    # Gone on the server, so a copy of its number opens nothing; and the browser is told to forget it.
    assert not Session.objects.filter(session_key=badge).exists()
    assert answer.cookies[SESSION_COOKIE]["max-age"] == 0
    refused = client.get(SIDES)
    assert (refused.status_code, refused.data["code"]) == (403, "not_authenticated")


def test_suspended_person_can_log_out(asha: StaffMember, laptop_key: str) -> None:
    # Every office route refuses her now, and that must not leave her badge lying on a shared laptop.
    client = logged_in(asha, laptop_key)
    badge = client.cookies[SESSION_COOKIE].value
    with shop_context(asha.shop_id):
        suspend(asha, by=None, reason="Amekosa kazi siku tatu")

    assert client.post(LOGOUT).status_code == 204
    assert not Session.objects.filter(session_key=badge).exists()


def test_logout_works_on_a_blocked_device(
    asha: StaffMember, laptop: Device, laptop_key: str, manager: StaffMember
) -> None:
    client = logged_in(asha, laptop_key)
    badge = client.cookies[SESSION_COOKIE].value
    with shop_context(asha.shop_id):
        block(laptop, by=manager, reason="Imeibiwa")

    assert client.post(LOGOUT).status_code == 204
    assert not Session.objects.filter(session_key=badge).exists()


def test_logout_needs_csrf(asha: StaffMember, laptop_key: str) -> None:
    # Without the token, another website could log the shop's laptop out, again and again, in the middle of a sale.
    client = APIClient(enforce_csrf_checks=True)
    client.cookies[KEY_COOKIE] = laptop_key
    client.get(DEVICE_ME)
    client.post(
        PIN_LOGIN,
        {"staff": str(asha.pk), "pin": PIN},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    badge = client.cookies[SESSION_COOKIE].value

    answer = client.post(LOGOUT)

    assert (answer.status_code, answer.data["code"]) == (403, "permission_denied")
    assert Session.objects.filter(session_key=badge).exists()


def test_logout_with_no_session_is_fine() -> None:
    # A second tap, or a badge that had already gone idle: the person wants to be out, and they are.
    assert APIClient().post(LOGOUT).status_code == 204


def test_logout_ends_a_password_session(asha: StaffMember) -> None:
    # The same route for a person on their own phone: a session is a session.
    phone = on_a_phone(asha)
    assert phone.get(SIDES).status_code == 200

    assert phone.post(LOGOUT).status_code == 204

    refused = phone.get(SIDES)
    assert (refused.status_code, refused.data["code"]) == (403, "not_authenticated")


@pytest.fixture
def admin_with_a_job(shop_a: Shop) -> StaffMember:
    # Someone who can open the admin, and also works at a shop. Nobody does today (the superuser is nobody's staff), and
    # nothing in the app stops it.
    user = User.objects.create_superuser(full_name="Admin Demo", email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
    with shop_context(shop_a):
        return set_pin(add_staff(shop=shop_a, user=user, display_name="Admin", by=None), PIN, by=None)


def test_pin_session_cannot_open_the_admin(admin_with_a_job: StaffMember, laptop_key: str) -> None:
    # 4 digits at a shared counter must not open a page that reads every shop's rows.
    client = logged_in(admin_with_a_job, laptop_key)
    for page in ("/admin/", "/admin/people/user/"):
        answer = client.get(page)
        assert answer.status_code == 302
        assert answer["Location"].startswith("/admin/login/")

    # The same person, logged in with their password: the refusal is the badge's, not theirs.
    by_password = Client()
    by_password.force_login(admin_with_a_job.user)
    assert by_password.get("/admin/").status_code == 200


def test_admin_login_over_a_badge_starts_clean(admin_with_a_job: StaffMember, laptop_key: str) -> None:
    # Their password, typed in the admin on a browser that holds their badge. Django keeps a session's data for the same
    # person, so the mark would stay, and the admin would send them back to its login page for good.
    badge = logged_in(admin_with_a_job, laptop_key).cookies[SESSION_COOKIE].value
    # Django's plain test client: the admin's login is a normal form, and a browser posts it as one.
    browser = Client()
    browser.cookies[SESSION_COOKIE] = badge

    answer = browser.post("/admin/login/", {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert answer.status_code == 302
    assert browser.get("/admin/").status_code == 200
    assert not Session.objects.filter(session_key=badge).exists()
    assert "pin_session" not in Session.objects.get(session_key=browser.cookies[SESSION_COOKIE].value).get_decoded()


def test_admin_login_page_shows_no_one_to_a_badge(asha: StaffMember, laptop_key: str) -> None:
    # Django's login page greets whoever `request.user` is: "You are authenticated as asha@example.com". A copied badge
    # must read nothing of hers there, as on allauth's routes. The email goes in first, so a leak would show. A plain
    # visit leaves the badge as it was: only a password actually typed here ends it.
    User.objects.filter(pk=asha.user_id).update(email="asha@example.com")
    badge = logged_in(asha, laptop_key).cookies[SESSION_COOKIE].value
    thief = Client()
    thief.cookies[SESSION_COOKIE] = badge

    answer = thief.get("/admin/login/")

    assert answer.status_code == 200
    body = answer.content.decode()
    assert "asha@example.com" not in body
    assert "You are authenticated" not in body
    assert Session.objects.filter(session_key=badge).exists()


def test_allauths_session_route_answers_no_badge(asha: StaffMember, laptop_key: str) -> None:
    # allauth's "am I logged in?" holds the person's name and email, and knows nothing of a badge's checks. A copied
    # badge, or the next person at an open laptop, gets what a stranger gets. The email goes in first, so a leak would
    # show.
    User.objects.filter(pk=asha.user_id).update(email="asha@example.com")
    client = logged_in(asha, laptop_key)
    thief = APIClient()
    thief.cookies[SESSION_COOKIE] = client.cookies[SESSION_COOKIE].value

    for browser in (client, thief):
        answer = browser.get(SESSION)
        assert answer.status_code == 401
        body = answer.content.decode()
        assert "asha@example.com" not in body
        assert asha.user.full_name not in body
        assert str(asha.user_id) not in body


def test_allauths_session_route_still_answers_a_password(asha: StaffMember) -> None:
    # On a person's own phone it is the app's way to ask who is logged in (UI-5).
    phone = on_a_phone(asha)
    answer = phone.get(SESSION)
    assert answer.status_code == 200
    assert answer.json()["data"]["user"]["display"] == asha.user.full_name


def test_allauths_logout_still_ends_a_badge(asha: StaffMember, laptop_key: str) -> None:
    client = logged_in(asha, laptop_key)
    badge = client.cookies[SESSION_COOKIE].value

    client.delete(SESSION)

    assert not Session.objects.filter(session_key=badge).exists()
