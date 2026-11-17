"""apps/people/tests/test_temporary_password_route.py — the office route that sets a temporary password (AUTH-6; 03
§5.10; ADR-0038). What may and may not be done is the service's, in test_temporary_password.py; these test the door.

    POST /api/v1/people/staff/{id}/temporary-password/   {"password": ..., "reason": ...}   204, nothing in the answer

Through the real login, with CSRF checked, as a browser's visit is. Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from typing import Any
from unittest import mock

import pytest
from django.views.debug import ExceptionReporter
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.control.models import AuditAction, AuditEvent
from apps.core.api.base import ShopViewSet
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api.views import StaffViewSet
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, grant_permission
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

# The routes, written out here rather than imported: they are a promise to the app, and a test that read them from the
# code would follow the code wherever it went.
LOGIN = "/_allauth/browser/v1/auth/login"
SESSION = "/_allauth/browser/v1/auth/session"
CHANGE = "/_allauth/browser/v1/account/password/change"
SIDES = "/api/v1/shops/sides/"

BABA_PHONE = "+255712345670"
ASHA_PHONE = "+255712345678"
OLD = "mbegu-za-mahindi-2026"
TEMPORARY = "mbolea-ya-kupandia-2027"
HER_OWN = "mahindi-ya-njano-2028"

TEST_CLIENT_FILES = ("django/test/client.py", "rest_framework/test.py", "test_temporary_password_route.py")

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


def route(staff: StaffMember) -> str:
    return f"/api/v1/people/staff/{staff.pk}/temporary-password/"


def job(shop: Shop, name: str, phone: str) -> StaffMember:
    user = User.objects.create_user(full_name=f"{name} Mfano", phone=phone, password=OLD)
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, by=None)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Baba", BABA_PHONE)
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def asha(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Asha", ASHA_PHONE)
    give_role(staff, RoleTemplate.SELLER, side_a)
    return staff


def csrf_token(client: APIClient) -> str:
    # From the `csrftoken` cookie, as the app gets it. Read again before each change: a login gives the browser a new
    # one.
    client.get(SESSION)
    return client.cookies["csrftoken"].value


def logged_in(phone: str, password: str = OLD) -> APIClient:
    client = APIClient(enforce_csrf_checks=True)
    answer = client.post(LOGIN, {"phone": phone, "password": password}, HTTP_X_CSRFTOKEN=csrf_token(client))
    assert answer.status_code == 200
    return client


def send(client: APIClient, staff: StaffMember, **sent: str) -> Any:
    return client.post(route(staff), sent, HTTP_X_CSRFTOKEN=csrf_token(client))


def assert_unchanged(staff: StaffMember) -> None:
    user = User.objects.get(pk=staff.user_id)
    assert user.check_password(OLD)
    assert user.must_change_password is False


def test_the_whole_story(baba: StaffMember, asha: StaffMember) -> None:
    # The card's first Done when, start to end, through every door a person uses.
    baba_phone = logged_in(BABA_PHONE)
    assert send(baba_phone, asha, password=TEMPORARY, reason="Amesahau").status_code == 204

    # Asha logs in with what Baba told her. Every office route stops her, and tells her why.
    asha_phone = logged_in(ASHA_PHONE, TEMPORARY)
    answer = asha_phone.get(SIDES)
    assert (answer.status_code, answer.json()["code"]) == (403, "password.must_change")

    # She chooses her own, in the same session, and the office opens.
    sent = {"current_password": TEMPORARY, "new_password": HER_OWN}
    assert asha_phone.post(CHANGE, sent, HTTP_X_CSRFTOKEN=csrf_token(asha_phone)).status_code == 200
    assert asha_phone.get(SIDES).status_code == 200

    # What Baba knows opens nothing now. The trail names who, for whom and why.
    assert APIClient().post(LOGIN, {"phone": ASHA_PHONE, "password": TEMPORARY}).status_code == 400
    with shop_context(asha.shop_id):
        line = AuditEvent.objects.get(action=AuditAction.STAFF_TEMPORARY_PASSWORD)
    assert (line.created_by_id, line.subject_id, line.reason) == (baba.pk, asha.pk, "Amesahau")


def test_route_answers_nothing_back(baba: StaffMember, asha: StaffMember) -> None:
    # ADR-0038: once sent, it is never shown again. An empty answer has nothing to show.
    answer = send(logged_in(BABA_PHONE), asha, password=TEMPORARY, reason="Amesahau")
    assert answer.status_code == 204
    assert answer.content == b""


@pytest.mark.parametrize(
    ("password", "code"),
    [("ashamfano", "password_too_similar"), ("x" * 129, "max_length"), ("", "blank")],
)
def test_refused_password_is_not_in_the_answer(baba: StaffMember, asha: StaffMember, password: str, code: str) -> None:
    # Beside the box the owner typed in, and with no copy of what was typed: the answer's words go to logs and error
    # trackers. Refused before it is hashed: 129 characters is a limit of ours, so a huge password can't be sent to the
    # slow hash.
    answer = send(logged_in(BABA_PHONE), asha, password=password, reason="Amesahau")
    assert answer.status_code == 400
    assert code in answer.json()["fields"]["password"]
    if password:
        assert password not in answer.content.decode()
    assert_unchanged(asha)


@pytest.mark.parametrize("typed", [f"{TEMPORARY} ", f" {TEMPORARY}", f"{TEMPORARY}\n"])
def test_spaces_around_a_password_still_log_in(baba: StaffMember, asha: StaffMember, typed: str) -> None:
    # A phone's keyboard adds a space after a word. allauth's login takes the spaces off what is typed, so a password
    # stored with one could never match, whatever Asha typed: she would use up her five tries. Tried through the real
    # login, as a look at the stored hash alone once passed with exactly this bug.
    assert send(logged_in(BABA_PHONE), asha, password=typed, reason="Amesahau").status_code == 204
    # As she was told it, and as Baba's keyboard wrote it.
    logged_in(ASHA_PHONE, TEMPORARY)
    logged_in(ASHA_PHONE, typed)


def test_spaces_inside_a_password_are_kept(baba: StaffMember, asha: StaffMember) -> None:
    # A phrase is a good password, and allauth's login leaves its inner spaces alone too.
    phrase = "mbolea ya kupandia 2027"
    assert send(logged_in(BABA_PHONE), asha, password=phrase, reason="Amesahau").status_code == 204
    logged_in(ASHA_PHONE, phrase)


def test_a_password_of_only_spaces_is_refused(baba: StaffMember, asha: StaffMember) -> None:
    # Twelve spaces would pass a length check and leave nothing at the login.
    answer = send(logged_in(BABA_PHONE), asha, password=" " * 12, reason="Amesahau")
    assert answer.status_code == 400
    assert answer.json()["fields"]["password"] == ["blank"]
    assert_unchanged(asha)


def test_a_reason_is_needed(baba: StaffMember, asha: StaffMember) -> None:
    client = logged_in(BABA_PHONE)
    answer = send(client, asha, password=TEMPORARY, reason="   ")
    assert (answer.status_code, answer.json()["code"]) == (400, "staff.reason_required")
    answer = send(client, asha, password=TEMPORARY)
    assert answer.json()["fields"]["reason"] == ["required"]
    assert_unchanged(asha)


def test_staff_routes_name_their_permissions() -> None:
    # The test clients hold every key, so they can't catch a route that asks for the wrong one (backend rules).
    assert StaffViewSet.action_permissions == {"temporary_password": Permission.STAFF_MANAGE}
    # A person's password opens them on every side: the row is the whole shop's, so the key is asked on the whole shop.
    assert StaffViewSet.side_field is None
    assert issubclass(StaffViewSet, ShopViewSet)


def test_route_refuses_without_the_key(shop_a: Shop, give_role: GiveRole, asha: StaffMember) -> None:
    meneja = job(shop_a, "Meneja", "+255712345671")
    give_role(meneja, RoleTemplate.MANAGER, None)
    answer = send(logged_in("+255712345671"), asha, password=TEMPORARY, reason="Amesahau")
    assert (answer.status_code, answer.json()["code"]) == (403, "permission_denied")
    assert_unchanged(asha)


def test_route_opens_for_a_manager_handed_the_key(shop_a: Shop, give_role: GiveRole, asha: StaffMember) -> None:
    meneja = job(shop_a, "Meneja", "+255712345671")
    give_role(meneja, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(meneja, Permission.STAFF_MANAGE, side=None, by=None)
    assert send(logged_in("+255712345671"), asha, password=TEMPORARY, reason="Amesahau").status_code == 204


def test_route_says_why_it_refuses(baba: StaffMember, shop_a: Shop, give_role: GiveRole) -> None:
    # The service's refusals reach the app as codes it translates (ADR-0032): here, "ask the superuser".
    meneja = job(shop_a, "Meneja", "+255712345671")
    give_role(meneja, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(meneja, Permission.STAFF_MANAGE, side=None, by=None)
    answer = send(logged_in("+255712345671"), baba, password=TEMPORARY, reason="Amesahau")
    assert (answer.status_code, answer.json()["code"]) == (400, "password.superuser_only")
    assert_unchanged(baba)


def test_someone_who_must_change_sets_nothing(baba: StaffMember, asha: StaffMember) -> None:
    # A manager on a temporary password, which someone else knows, isn't yet the only person who could be asking.
    client = logged_in(BABA_PHONE)
    User.objects.filter(pk=baba.user_id).update(must_change_password=True)
    answer = send(client, asha, password=TEMPORARY, reason="Amesahau")
    assert (answer.status_code, answer.json()["code"]) == (403, "password.must_change")
    assert_unchanged(asha)


def test_route_needs_csrf(baba: StaffMember, asha: StaffMember) -> None:
    # Another website can't set a person's password in the owner's name: it would then know it.
    client = logged_in(BABA_PHONE)
    assert client.post(route(asha), {"password": TEMPORARY, "reason": "Amesahau"}).status_code == 403
    assert_unchanged(asha)


def test_route_needs_a_login(asha: StaffMember) -> None:
    answer = APIClient().post(route(asha), {"password": TEMPORARY, "reason": "Amesahau"})
    assert (answer.status_code, answer.json()["code"]) == (403, "not_authenticated")
    assert_unchanged(asha)


def test_another_shops_person_is_not_found(shop_b: Shop, give_role: GiveRole, asha: StaffMember) -> None:
    # The sweep sends this empty (backend/tests/test_tenancy_sweep.py). Sent in full, by an owner: as if she weren't
    # there.
    other_owner = job(shop_b, "Mmiliki", "+255712345672")
    give_role(other_owner, RoleTemplate.OWNER, None)
    answer = send(logged_in("+255712345672"), asha, password=TEMPORARY, reason="Amesahau")
    assert (answer.status_code, answer.json()["code"]) == (404, "not_found")
    assert_unchanged(asha)


def test_route_shows_nothing_to_a_read(baba: StaffMember, asha: StaffMember) -> None:
    # Only a POST: nothing about the person to read here, and PPL-4 adds the rest of the staff routes.
    assert logged_in(BABA_PHONE).get(route(asha)).status_code == 405


def test_password_stays_out_when_the_hash_itself_fails(baba: StaffMember, asha: StaffMember) -> None:
    # Hiding a variable by its name isn't enough here: the library underneath gives the password its own name, `secret`,
    # and running out of memory in the hash is the likeliest crash on the demo's 512 MB. So every variable is hidden, in
    # the route and the service, and in everything they call.
    client = logged_in(BABA_PHONE)
    token = csrf_token(client)
    crashing = mock.patch("apps.people.services.make_password", side_effect=MemoryError("out of memory"))
    with crashing, pytest.raises(MemoryError) as crash:
        client.post(route(asha), {"password": TEMPORARY, "reason": "Amesahau"}, HTTP_X_CSRFTOKEN=token)
    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    on_the_server = [frame for frame in frames if not frame["filename"].endswith(TEST_CLIENT_FILES)]
    shown = [
        (frame["function"], name) for frame in on_the_server for name, value in frame["vars"] if TEMPORARY in str(value)
    ]
    assert shown == []


def test_password_stays_out_of_error_reports(baba: StaffMember, asha: StaffMember) -> None:
    # A crash in the visit lists every function's variables in Django's error report, which a server with DEBUG off logs
    # and sends. The route holds what was sent while it calls the service, so a crash inside the service, after the
    # password is hashed, must not print the password in any frame.
    client = logged_in(BABA_PHONE)
    crashing = mock.patch("apps.people.services.audit", side_effect=RuntimeError("no database"))
    with crashing, pytest.raises(RuntimeError) as crash:
        send(client, asha, password=TEMPORARY, reason="Amesahau")
    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    # Only the server's frames. The test client's own hold what this test sent, and a server has no such frames: there,
    # a visit starts at Django's handler.
    on_the_server = [frame for frame in frames if not frame["filename"].endswith(TEST_CLIENT_FILES)]
    shown = [(frame["function"], name, str(value)) for frame in on_the_server for name, value in frame["vars"]]
    assert [(function, name) for function, name, value in shown if TEMPORARY in value] == []
    # And it looked in the right places: the crash passed through the route and the service, each hiding its copy.
    [sent] = [value for function, name, value in shown if (function, name) == ("temporary_password", "sent")]
    assert set(sent) == {"*"}
    [password] = [
        value for function, name, value in shown if (function, name) == ("set_temporary_password", "password")
    ]
    assert set(password) == {"*"}


def test_no_temporary_password_on_the_demo(baba: StaffMember, asha: StaffMember, settings: Settings) -> None:
    # On the demo, a visitor with the owner's keys could hand any person a password of their own and lock the next
    # visitors out of that login (Jack, 8 Nov 2026). Refused before anything is checked or written.
    settings.DEMO_SEED = True

    answer = send(logged_in(BABA_PHONE), asha, password=TEMPORARY, reason="Amesahau")

    assert (answer.status_code, answer.json()["code"]) == (400, "demo.logins_fixed")
    assert_unchanged(asha)
