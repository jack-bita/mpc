"""apps/people/tests/test_password_change.py — a logged-in person chooses their own password, which is how a temporary
one ends (AUTH-6; 03 §5.9; ADR-0038).

    POST account/password/change   the current password and a new one   200: the mark is off, and the office routes open

Through the real login and the real route, with CSRF checked, as a browser's visit is. The mark is put on by hand here:
who may put it on, and how, is in test_temporary_password.py. Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes, written out here rather than imported: they are a promise to the app, and a test that read them from the
# code would follow the code wherever it went.
LOGIN = "/_allauth/browser/v1/auth/login"
SESSION = "/_allauth/browser/v1/auth/session"
CHANGE = "/_allauth/browser/v1/account/password/change"
SIDES = "/api/v1/shops/sides/"

PHONE = "+255712345678"
TEMPORARY = "mbegu-za-mahindi-2026"
OWN = "mbolea-ya-kupandia-2027"


@pytest.fixture
def asha(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    # A seller the owner has just given a temporary password: the mark is on.
    user = User.objects.create_user(full_name="Asha Mfano", phone=PHONE, password=TEMPORARY)
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=user, display_name="Asha", by=None)
    give_role(staff, RoleTemplate.SELLER, None)
    User.objects.filter(pk=user.pk).update(must_change_password=True)
    return staff


def csrf_token(client: APIClient) -> str:
    # The CSRF token, as the app gets it: from the `csrftoken` cookie. Read again before each change: a login gives the
    # browser a new one.
    client.get(SESSION)
    return client.cookies["csrftoken"].value


def log_in(password: str = TEMPORARY) -> tuple[APIClient, int]:
    client = APIClient(enforce_csrf_checks=True)
    answer = client.post(LOGIN, {"phone": PHONE, "password": password}, HTTP_X_CSRFTOKEN=csrf_token(client))
    return client, answer.status_code


@pytest.fixture
def phone(asha: StaffMember) -> APIClient:
    client, status = log_in()
    assert status == 200
    return client


def change(client: APIClient, **sent: str) -> tuple[int, list[str]]:
    # A change as the app sends it. Its status, and allauth's error codes, in its own shape: UI-5's form reads them.
    answer = client.post(CHANGE, sent, HTTP_X_CSRFTOKEN=csrf_token(client))
    return answer.status_code, [error["code"] for error in answer.json().get("errors", [])]


def office_code(client: APIClient) -> tuple[int, str]:
    answer = client.get(SIDES)
    return answer.status_code, answer.json().get("code", "")


def mark_of(staff: StaffMember) -> bool:
    return User.objects.get(pk=staff.user_id).must_change_password


def test_change_clears_the_mark(asha: StaffMember, phone: APIClient) -> None:
    assert office_code(phone) == (403, "password.must_change")

    assert change(phone, current_password=TEMPORARY, new_password=OWN) == (200, [])

    # The mark is off, and this very session opens the office routes: no second login after choosing.
    assert mark_of(asha) is False
    assert phone.get(SIDES).status_code == 200
    # The owner's password opens nothing now; hers does.
    assert log_in(TEMPORARY)[1] == 400
    assert log_in(OWN)[1] == 200


def test_new_password_cannot_be_the_temporary_one(asha: StaffMember, phone: APIClient) -> None:
    # The whole point of the change: the owner typed that one, so choosing it again would leave them knowing it for
    # good, and the mark would say all is well.
    assert change(phone, current_password=TEMPORARY, new_password=TEMPORARY) == (400, ["password.same_as_temporary"])
    assert mark_of(asha) is True
    assert office_code(phone) == (403, "password.must_change")


def test_new_password_must_pass_the_checks(asha: StaffMember, phone: APIClient) -> None:
    # The same checks as any other password, the person's own name and phone included (AUTH_PASSWORD_VALIDATORS).
    assert change(phone, current_password=TEMPORARY, new_password="ashamfano") == (400, ["password_too_similar"])
    assert mark_of(asha) is True


def test_change_needs_the_current_password(asha: StaffMember, phone: APIClient) -> None:
    # Whoever picks up a phone that is logged in can't take the person's password with it.
    assert change(phone, new_password=OWN) == (400, ["required"])
    assert change(phone, current_password="not-the-password", new_password=OWN) == (400, ["enter_current_password"])
    assert User.objects.get(pk=asha.user_id).check_password(TEMPORARY)


def test_a_person_with_no_password_cannot_set_one_alone() -> None:
    # allauth's own form skips the current password for someone who has none. AUTH-4's PIN sessions would reach it: at
    # a shared laptop left open, anyone could give a PIN-only worker a password, and log in as them from anywhere for
    # good. A first password is the owner's to set, face to face (ADR-0038).
    worker = User.objects.create_user(full_name="Juma Mfano", phone="+255712345679")
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(worker)

    assert change(client, new_password=OWN) == (400, ["required"])
    assert change(client, current_password="anything", new_password=OWN) == (400, ["enter_current_password"])
    worker.refresh_from_db()
    assert not worker.has_usable_password()


def test_change_ends_other_sessions(asha: StaffMember, phone: APIClient) -> None:
    # A phone lost while logged in is logged out by choosing a new password. Django's session check does it, as a
    # session holds a fingerprint of the password it started with; the session that made the change gets a new one, and
    # stays.
    lost_phone, status = log_in()
    assert status == 200

    assert change(phone, current_password=TEMPORARY, new_password=OWN) == (200, [])

    assert lost_phone.get(SESSION).status_code == 401
    assert phone.get(SESSION).status_code == 200


def test_change_needs_csrf(asha: StaffMember, phone: APIClient) -> None:
    # Another website can't change a person's password in their name.
    answer = phone.post(CHANGE, {"current_password": TEMPORARY, "new_password": OWN})
    assert answer.status_code == 403
    assert User.objects.get(pk=asha.user_id).check_password(TEMPORARY)


def test_change_needs_a_login() -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert change(client, current_password=TEMPORARY, new_password=OWN)[0] == 401


def test_change_is_slowed_down(asha: StaffMember, phone: APIClient) -> None:
    # A stranger holding a logged-in phone can't try passwords here without end. allauth's own limit, 5 a minute per
    # person; our subclass of its route must keep it, so this pins it.
    for _ in range(5):
        assert change(phone, current_password="not-the-password", new_password=OWN)[0] == 400
    assert change(phone, current_password=TEMPORARY, new_password=OWN)[0] == 429
    assert mark_of(asha) is True


def test_a_change_with_no_mark_is_an_ordinary_change(asha: StaffMember, phone: APIClient) -> None:
    # The route is for everyone with a password, not only those who must: a person may change theirs at any time.
    User.objects.filter(pk=asha.user_id).update(must_change_password=False)
    assert change(phone, current_password=TEMPORARY, new_password=OWN) == (200, [])
    assert mark_of(asha) is False
    assert phone.get(SIDES).status_code == 200
