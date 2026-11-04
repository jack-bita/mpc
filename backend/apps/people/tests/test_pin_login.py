"""apps/people/tests/test_pin_login.py — a worker logs in by PIN on a shop's device (AUTH-4; 03 §5.9; X2).

A device's key says which machine this is; a PIN says who stands at it. The route takes both, and starts a session: a
badge, kept by the server, that names this person on this device.

    the request                                   POST /api/auth/pin-login/
    no key, a made-up key                         401 not_authenticated
    a blocked device                              401 device.blocked
    a suspended shop's device                     401 shop.suspended
    a suspended person                            403 staff.suspended, with no PIN check
    someone who left, or who is switched off      400 pin.wrong, after one full check, as for a wrong PIN
    another shop's person, or a made-up one       400 pin.wrong, the same
    a wrong PIN                                   400 pin.wrong; the fifth, 400 pin.locked with the wait
    the right PIN                                 204, a session, the old one torn up

What each visit then does with its badge is test_pin_session.py's subject; the lock's own rules, test_pin_lock.py's.

Fake data only: the repo is public (03 §10).
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any
from unittest import mock

import pytest
from django.contrib.auth.hashers import Argon2PasswordHasher
from django.contrib.sessions.models import Session
from django.views.debug import ExceptionReporter
from rest_framework.test import APIClient

from apps.control.models import EditEvent
from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import IDLE_MINUTES
from apps.core.tenancy import shop_context
from apps.people.models import Device, PinLock, StaffMember, User
from apps.people.pins import _hasher, _peppered, pin_matches
from apps.people.services import (
    _move_pin_to_todays_cost,
    add_staff,
    block,
    confirm_pairing,
    mark_left,
    set_pin,
    start_pairing,
    suspend,
    unblock,
    unsuspend,
)
from apps.shops.models import Setting, Shop, ShopStatus, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The route and the cookies' names, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
PIN_LOGIN = "/api/auth/pin-login/"
DEVICE_ME = "/api/devices/v1/me/"
KEY_COOKIE = "device_key"
SESSION_COOKIE = "sessionid"

PIN = "4829"
WRONG = "4830"
# How a hash made today names its cost: 19 MiB, 2 passes, 1 lane (apps/people/hashers.py).
TODAYS_COST = "$m=19456,t=2,p=1$"
# Files whose frames hold what the test itself sent: not the server's, so not for it to hide.
TEST_CLIENT_FILES = ("django/test/client.py", "rest_framework/test.py", "test_pin_login.py")


def pair(manager: StaffMember, side: Side, name: str) -> tuple[Device, str]:
    # A device paired the way the app pairs one: it asks and keeps its key, and a manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        return confirm_pairing(asked.request.code, name=name, home_side=side, by=manager), asked.key


def a_browser(key: str, *, csrf: bool = False) -> APIClient:
    # A browser that holds this device's key in its cookie. `csrf`: check CSRF as a real browser's visit is checked; the
    # test client skips that check unless asked.
    client = APIClient(enforce_csrf_checks=csrf)
    client.cookies[KEY_COOKIE] = key
    return client


def try_pin(client: APIClient, staff_id: uuid.UUID, pin: str = PIN) -> Any:
    return client.post(PIN_LOGIN, {"staff": str(staff_id), "pin": pin}, format="json")


def session_row(client: APIClient) -> Session:
    return Session.objects.get(session_key=client.cookies[SESSION_COOKIE].value)


@contextmanager
def counting_checks() -> Iterator[list[str]]:
    # Each full PIN check this block costs, counted rather than timed: a clock would fail on a busy machine.
    checks: list[str] = []
    real_check = _hasher.verify

    def counted(password: str, encoded: str) -> bool:
        checks.append(encoded)
        return real_check(password, encoded)

    with mock.patch.object(_hasher, "verify", counted):
        yield checks


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
def asha(staff_a: StaffMember) -> StaffMember:
    with shop_context(staff_a.shop_id):
        return set_pin(staff_a, PIN, by=None)


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    user = User.objects.create_user(full_name="Juma Demo")
    with shop_context(shop_a):
        return set_pin(add_staff(shop=shop_a, user=user, display_name="Juma", by=None), PIN, by=None)


def test_right_pin_starts_a_session_on_the_device(asha: StaffMember, laptop: Device, laptop_key: str) -> None:
    client = a_browser(laptop_key)

    answer = try_pin(client, asha.pk)

    # Nothing in the answer: the app asks `me` next (03 §5.9).
    assert answer.status_code == 204
    assert not answer.content
    session = session_row(client).get_decoded()
    assert session["_auth_user_id"] == str(asha.user_id)
    # The badge names its person, shop and device, so each visit checks all three (test_pin_session.py). It names the
    # job, not only the person: someone with jobs at two shops is at this device's shop here.
    assert session["pin_session"] == {"shop": str(asha.shop_id), "staff": str(asha.pk), "device": str(laptop.pk)}


def test_session_lasts_the_shops_idle_minutes(asha: StaffMember, laptop_key: str, shop_a: Shop) -> None:
    # 15 minutes by default (session.idle_minutes, apps/core/settings_registry.py), both in the browser's cookie and on
    # the server's own row, as a copied cookie must not outlive it.
    client = a_browser(laptop_key)
    try_pin(client, asha.pk)
    assert client.cookies[SESSION_COOKIE]["max-age"] == 15 * 60
    assert session_row(client).get_decoded()["_session_expiry"] == 15 * 60

    # A shop's own value, from the next login.
    with shop_context(shop_a):
        Setting.objects.create(shop=shop_a, key=IDLE_MINUTES.key, value="5", effective_from=date(2020, 1, 1))
    try_pin(client, asha.pk)
    assert client.cookies[SESSION_COOKIE]["max-age"] == 5 * 60


def test_pin_login_only_on_active_device(
    asha: StaffMember, laptop_key: str, laptop: Device, manager: StaffMember, shop_a: Shop
) -> None:
    # X2: a PIN is useless off the shop's devices. Each refusal is the device's, before any PIN is read.
    assert try_pin(APIClient(), asha.pk).data["code"] == "not_authenticated"
    assert try_pin(a_browser("made-up-key"), asha.pk).data["code"] == "not_authenticated"

    with shop_context(shop_a):
        block(laptop, by=manager, reason="Imeibiwa")
    blocked = a_browser(laptop_key)
    answer = try_pin(blocked, asha.pk)
    assert (answer.status_code, answer.data["code"]) == (401, "device.blocked")
    assert SESSION_COOKIE not in blocked.cookies
    with shop_context(shop_a):
        unblock(laptop, by=manager, reason="Imepatikana")

    Shop.objects.filter(pk=shop_a.pk).update(status=ShopStatus.SUSPENDED)
    closed = a_browser(laptop_key)
    answer = try_pin(closed, asha.pk)
    assert (answer.status_code, answer.data["code"]) == (401, "shop.suspended")
    assert SESSION_COOKIE not in closed.cookies


def test_waiting_device_cannot_log_anyone_in(asha: StaffMember) -> None:
    # A key still waiting for a manager's yes opens nothing (AUTH-2).
    answer = try_pin(a_browser(start_pairing().key), asha.pk)
    assert (answer.status_code, answer.data["code"]) == (401, "not_authenticated")


def test_suspended_staff_cannot_log_in(asha: StaffMember, laptop_key: str) -> None:
    client = a_browser(laptop_key)
    with shop_context(asha.shop_id):
        suspend(asha, by=None, reason="Amekosa kazi siku tatu")

    # Told why, as her status is no secret at the counter: a device holds its shop's staff status for itself (03 §6).
    # No check: this visit costs the server no memory, whatever PIN is sent.
    with counting_checks() as checks:
        answer = try_pin(client, asha.pk)
    assert (answer.status_code, answer.data["code"]) == (403, "staff.suspended")
    assert checks == []
    assert SESSION_COOKIE not in client.cookies

    # Brought back, her PIN works again: nothing about her PIN changed.
    with shop_context(asha.shop_id):
        unsuspend(asha, by=None, reason="Amerudi kazini")
    assert try_pin(client, asha.pk).status_code == 204


def test_left_staff_cannot_log_in(asha: StaffMember, laptop_key: str) -> None:
    # Someone who has left isn't anyone at this shop now: the answer is the one for a wrong PIN, not a refusal that says
    # who they were (apps/people/selectors.py).
    client = a_browser(laptop_key)
    with shop_context(asha.shop_id):
        mark_left(asha, left_on=asha.started_on, by=None, reason="Amehamia mji mwingine")

    with counting_checks() as checks:
        answer = try_pin(client, asha.pk)
    assert (answer.status_code, answer.data["code"]) == (400, "pin.wrong")
    assert len(checks) == 1
    assert SESSION_COOKIE not in client.cookies


def test_switched_off_person_cannot_log_in(asha: StaffMember, laptop_key: str) -> None:
    # A person switched off (User.is_active) must never log in again, whatever their job's status says (PPL-1).
    client = a_browser(laptop_key)
    User.objects.filter(pk=asha.user_id).update(is_active=False)

    answer = try_pin(client, asha.pk)
    assert (answer.status_code, answer.data["code"]) == (400, "pin.wrong")
    assert SESSION_COOKIE not in client.cookies


def test_another_shops_staff_cannot_log_in(staff_b: StaffMember, laptop_key: str, shop_b: Shop) -> None:
    # X2: only on a device of the same shop. Shop B's person, with their own right PIN, on shop A's laptop: to this
    # visit they don't exist, as the guard hides them, so the answer can't say they exist elsewhere (T1).
    with shop_context(shop_b):
        set_pin(staff_b, PIN, by=None)
    client = a_browser(laptop_key)

    with counting_checks() as checks:
        answer = try_pin(client, staff_b.pk)

    assert (answer.status_code, answer.data["code"]) == (400, "pin.wrong")
    # The same work as a wrong PIN, so the time says nothing.
    assert len(checks) == 1
    assert SESSION_COOKIE not in client.cookies
    with shop_context(shop_b):
        assert not PinLock.objects.exists()


def test_made_up_person_costs_a_full_check(laptop_key: str) -> None:
    with counting_checks() as checks:
        answer = try_pin(a_browser(laptop_key), uuid.uuid7())
    assert (answer.status_code, answer.data["code"]) == (400, "pin.wrong")
    assert len(checks) == 1


def test_wrong_pins_answer_wrong_then_locked(asha: StaffMember, laptop_key: str) -> None:
    client = a_browser(laptop_key)
    for _ in range(4):
        answer = try_pin(client, asha.pk, WRONG)
        assert (answer.status_code, answer.data["code"]) == (400, "pin.wrong")

    answer = try_pin(client, asha.pk, WRONG)
    assert (answer.status_code, answer.data["code"]) == (400, "pin.locked")
    # The seconds to wait, for the app's "try again in a minute" (ADR-0032).
    assert answer.data["params"] == {"wait": 60}
    assert SESSION_COOKIE not in client.cookies


def test_second_pin_replaces_the_first_session(asha: StaffMember, juma: StaffMember, laptop_key: str) -> None:
    # One badge per device: Juma's PIN tears up Asha's badge, on the server too, so a copy of it opens nothing.
    client = a_browser(laptop_key)
    try_pin(client, asha.pk)
    ashas_badge = client.cookies[SESSION_COOKIE].value

    assert try_pin(client, juma.pk).status_code == 204

    assert not Session.objects.filter(session_key=ashas_badge).exists()
    assert session_row(client).get_decoded()["_auth_user_id"] == str(juma.user_id)


def test_same_person_gets_a_new_session(asha: StaffMember, laptop_key: str) -> None:
    # Her own old badge too: a badge never outlives a new login, so one copied earlier opens nothing.
    client = a_browser(laptop_key)
    try_pin(client, asha.pk)
    old_badge = client.cookies[SESSION_COOKIE].value

    try_pin(client, asha.pk)

    assert client.cookies[SESSION_COOKIE].value != old_badge
    assert not Session.objects.filter(session_key=old_badge).exists()


def test_old_pin_hash_moves_to_the_new_cost(asha: StaffMember, laptop_key: str) -> None:
    # A PIN hashed before AUTH-4, at Django's default cost of 100 MiB. At her next login, it moves to today's.
    django_default = Argon2PasswordHasher()
    old = django_default.encode(_peppered(PIN), django_default.salt())
    with shop_context(asha.shop_id):
        StaffMember.objects.filter(pk=asha.pk).update(pin_hash=old)
        asha.refresh_from_db()
        changed_at = asha.pin_changed_at
        edits_before = EditEvent.objects.filter(subject_id=asha.pk).count()

    assert try_pin(a_browser(laptop_key), asha.pk).status_code == 204

    with shop_context(asha.shop_id):
        asha.refresh_from_db()
        assert TODAYS_COST in asha.pin_hash
        assert pin_matches(PIN, asha.pin_hash)
        # Her PIN didn't change, so devices keep their offline check of it (03 §5.9), and the trail says nothing.
        assert asha.pin_changed_at == changed_at
        assert EditEvent.objects.filter(subject_id=asha.pk).count() == edits_before


def test_new_pin_set_meanwhile_is_kept(asha: StaffMember) -> None:
    # A manager gives her a new PIN while her login is hashing the old one: the login's copy is out of date, and writing
    # it would quietly bring the old PIN back.
    with shop_context(asha.shop_id):
        renewed = set_pin(StaffMember.objects.get(pk=asha.pk), "5930", by=None)
        _move_pin_to_todays_cost(asha, PIN)
        renewed.refresh_from_db()
    assert pin_matches("5930", renewed.pin_hash)
    assert not pin_matches(PIN, renewed.pin_hash)


def test_pin_login_is_limited_per_device(manager: StaffMember, side_a: Side, laptop_key: str) -> None:
    # A flood of tries, each a new made-up person so that no lock stops it, costs a full check each: 19 MiB. So each
    # device has a limit of its own *(default)*. Another device doesn't feel it.
    client = a_browser(laptop_key)
    for _ in range(30):
        assert try_pin(client, uuid.uuid7()).status_code == 400

    answer = try_pin(client, uuid.uuid7())
    assert (answer.status_code, answer.data["code"]) == (429, "throttled")
    assert answer.data["params"]["wait"] > 0

    _, other_key = pair(manager, side_a, "Laptop ya Vyakula")
    assert try_pin(a_browser(other_key), uuid.uuid7()).status_code == 400


def test_pin_login_needs_csrf(asha: StaffMember, laptop_key: str) -> None:
    # The device's cookie goes with every request to our address, even one another website makes the laptop send:
    # without the token, that website could use up Asha's five tries, and lock her out (ADR-0038).
    client = a_browser(laptop_key, csrf=True)

    answer = try_pin(client, asha.pk, WRONG)
    assert (answer.status_code, answer.data["code"]) == (403, "permission_denied")
    with shop_context(asha.shop_id):
        assert not PinLock.objects.exists()

    # With the token, as the app sends it: from the cookie `me` hands out.
    client.get(DEVICE_ME)
    answer = client.post(
        PIN_LOGIN,
        {"staff": str(asha.pk), "pin": PIN},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert answer.status_code == 204


@pytest.mark.parametrize(
    ("sent", "field", "code"),
    [
        ({"staff": "not-an-id", "pin": PIN}, "staff", "invalid"),
        ({"pin": PIN}, "staff", "required"),
        ({"staff": "0192f6a4-0000-7000-8000-000000000000"}, "pin", "required"),
        # A huge "PIN" never reaches the slow hash: nothing that long can be one.
        ({"staff": "0192f6a4-0000-7000-8000-000000000000", "pin": "1" * 17}, "pin", "max_length"),
    ],
)
def test_badly_shaped_try_is_refused_before_any_check(
    laptop_key: str, sent: dict[str, str], field: str, code: str
) -> None:
    with counting_checks() as checks:
        answer = a_browser(laptop_key).post(PIN_LOGIN, sent, format="json")
    assert answer.status_code == 400
    assert answer.data["fields"] == {field: [code]}
    assert checks == []


def test_pin_stays_out_of_error_reports(asha: StaffMember, laptop_key: str) -> None:
    # Django's error report lists each function's variables when something fails, and running out of memory in the hash
    # is the likeliest crash on the demo's 512 MB. Nowhere on the server's side does the PIN show. A text of its own,
    # not four digits, which a random id in some frame could hold by chance.
    secret = "secret-pin-value"
    crashing = mock.patch.object(_hasher, "verify", side_effect=MemoryError("out of memory"))
    with crashing, pytest.raises(MemoryError) as crash:
        try_pin(a_browser(laptop_key), asha.pk, secret)
    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    on_the_server = [frame for frame in frames if not frame["filename"].endswith(TEST_CLIENT_FILES)]
    assert on_the_server
    shown = [
        (frame["function"], name) for frame in on_the_server for name, value in frame["vars"] if secret in str(value)
    ]
    assert shown == []


def test_pin_login_answers_hold_nothing_of_any_shop(
    asha: StaffMember, laptop_key: str, staff_b: StaffMember, side_b: Side, give_role: GiveRole
) -> None:
    # The tenancy sweep sends this route only empty POSTs, so it looks here for what a real try answers: never a name,
    # a phone or a shop, on its own device or on another shop's (DEVICE_ROUTES_WITHOUT_A_LOOK).
    give_role(staff_b, RoleTemplate.MANAGER, None)
    _, key_b = pair(staff_b, side_b, "Simu ya Jingine")

    assert not try_pin(a_browser(laptop_key), asha.pk).content
    for key in (laptop_key, key_b):
        answer = try_pin(a_browser(key), asha.pk, WRONG)
        assert answer.status_code == 400
        assert set(answer.data) == {"code", "message", "fields", "params"}
        for shown in (asha.display_name, asha.user.full_name, asha.shop.name, asha.shop.code, str(asha.shop_id)):
            assert shown not in str(answer.data)
