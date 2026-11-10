"""apps/people/tests/test_staff_session.py — a person logged in with a password acts as their staff member, on every
office route (AUTH-3; 03 §5.9; ADR-0038).

The other tests of office routes skip the login (`staff_client_a`, backend/conftest.py). These go through the real one:
a phone and a password through allauth's route, then an office route, /api/v1/shops/sides/, with the session it started.

    the person                         an office route
    active, one job                    200, their own shop's rows
    suspended                          403 staff.suspended, on the very next request; back again, 200
    must choose their own password     403 password.must_change, on the very next request; once chosen, 200
    their shop suspended               403 shop.suspended
    jobs at two shops                  403 staff.choose_shop, until AUTH-7
    left, or the superuser: no job     403 not_authenticated
    switched off, or logged out        403 not_authenticated

Fake data only: the repo is public (03 §10).
"""

import uuid
from collections.abc import Callable

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.login_doors import shops_of_person
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, mark_left, suspend, unsuspend
from apps.shops.models import Shop, ShopStatus, Side

pytestmark = pytest.mark.django_db

# The routes, written out here rather than imported: they are a promise to the app, and a test that read them from the
# code would follow the code wherever it went.
LOGIN = "/_allauth/browser/v1/auth/login"
SESSION = "/_allauth/browser/v1/auth/session"
SIDES = "/api/v1/shops/sides/"

PHONE = "+255712345678"
PASSWORD = "mbegu-za-mahindi-2026"

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def owner(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    # The owner of shop A, with a phone and a password, on every side: they may change a side, which shows who acts.
    user = User.objects.create_user(full_name="Baba Mfano", phone=PHONE, password=PASSWORD)
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=user, display_name="Baba", by=None)
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def csrf_token(client: APIClient) -> str:
    # The CSRF token, as the app gets it: from the `csrftoken` cookie, which every allauth route hands out. Read again
    # before each change: a login gives the browser a new one.
    client.get(SESSION)
    return client.cookies["csrftoken"].value


@pytest.fixture
def phone() -> APIClient:
    # A phone's browser, logged in the way the app logs in: CSRF checked, as a real browser's visit is.
    client = APIClient(enforce_csrf_checks=True)
    answer = client.post(LOGIN, {"phone": PHONE, "password": PASSWORD}, HTTP_X_CSRFTOKEN=csrf_token(client))
    assert answer.status_code == 200
    return client


def code_of(client: Client) -> tuple[int, str]:
    # What an office route answers this browser: its status, and the code the app translates (ADR-0032).
    answer = client.get(SIDES)
    return answer.status_code, answer.json().get("code", "")


def test_password_session_reaches_office_routes(owner: StaffMember, phone: APIClient, shop_a: Shop) -> None:
    answer = phone.get(SIDES)
    assert answer.status_code == 200
    assert [row["code"] for row in answer.json()["results"]] == ["D"]

    # The session acts as the staff member: a row it makes names them (`request.auth`, CORE-6).
    new = {"id": str(uuid.uuid7()), "code": "F", "name": "Vyakula"}
    assert phone.post(SIDES, new, HTTP_X_CSRFTOKEN=csrf_token(phone)).status_code == 201
    with shop_context(shop_a):
        assert Side.objects.get(pk=new["id"]).created_by_id == owner.pk


def test_email_session_reaches_office_routes(owner: StaffMember) -> None:
    # The same door by the other login name: a session is a person's, however they logged in.
    User.objects.filter(pk=owner.user_id).update(email="baba@example.com")
    client = APIClient(enforce_csrf_checks=True)
    answer = client.post(
        LOGIN, {"email": "baba@example.com", "password": PASSWORD}, HTTP_X_CSRFTOKEN=csrf_token(client)
    )
    assert answer.status_code == 200
    assert client.get(SIDES).status_code == 200


def test_password_session_changes_need_csrf(owner: StaffMember, phone: APIClient, shop_a: Shop) -> None:
    # The login is built on DRF's session login, whose CSRF check must stay: the cookie alone would let another website
    # change a side in the owner's name.
    new = {"id": str(uuid.uuid7()), "code": "F", "name": "Vyakula"}
    assert phone.post(SIDES, new).status_code == 403
    with shop_context(shop_a):
        assert not Side.objects.filter(pk=new["id"]).exists()


def test_password_session_shows_only_its_own_shop(owner: StaffMember, phone: APIClient, side_b: Side) -> None:
    # Shop B has a side too (side_b): the session's shop is the only one the visit can see (ADR-0037).
    answer = phone.get(SIDES)
    assert str(side_b.pk) not in {row["id"] for row in answer.json()["results"]}


def test_suspended_staff_stopped_at_next_request(owner: StaffMember, phone: APIClient, shop_a: Shop) -> None:
    assert phone.get(SIDES).status_code == 200

    # Baba's session is still there, in its cookie: only the check on this very visit stops it (ADR-0038).
    with shop_context(shop_a):
        suspend(owner, by=None, reason="Cash short for two weeks")
    assert code_of(phone) == (403, "staff.suspended")

    # Brought back, the same session works again: no new login.
    with shop_context(shop_a):
        unsuspend(owner, by=None, reason="Sorted out")
    assert phone.get(SIDES).status_code == 200


def test_must_change_blocks_office_routes(owner: StaffMember, phone: APIClient, shop_a: Shop) -> None:
    assert phone.get(SIDES).status_code == 200

    # The mark goes on: a read and a change are both stopped, on this very visit, whatever session the person holds.
    User.objects.filter(pk=owner.user_id).update(must_change_password=True)
    assert code_of(phone) == (403, "password.must_change")
    new = {"id": str(uuid.uuid7()), "code": "F", "name": "Vyakula"}
    answer = phone.post(SIDES, new, HTTP_X_CSRFTOKEN=csrf_token(phone))
    assert (answer.status_code, answer.json()["code"]) == (403, "password.must_change")
    with shop_context(shop_a):
        assert not Side.objects.filter(pk=new["id"]).exists()

    # Only the office routes close: the session is still theirs, as the way to choose a new password needs it.
    assert phone.get(SESSION).status_code == 200

    # The mark comes off: the same session works again, with no new login.
    User.objects.filter(pk=owner.user_id).update(must_change_password=False)
    assert phone.get(SIDES).status_code == 200


def test_must_change_leaves_the_admin_open(superuser: User, superuser_client: Client) -> None:
    # The mark closes a job's office routes, and the admin isn't one of those: the person who resets passwords can't be
    # locked out by a reset. So the mark protects nothing for someone who can open the admin: one who also has a job
    # could disable their own password there, and the mark would come off. Nothing is lost, as they hold the whole admin
    # anyway.
    User.objects.filter(pk=superuser.pk).update(must_change_password=True)
    assert superuser_client.get("/admin/").status_code == 200


def test_staff_who_left_is_refused(owner: StaffMember, phone: APIClient, shop_a: Shop) -> None:
    with shop_context(shop_a):
        mark_left(owner, left_on=owner.started_on, by=None, reason="Moved to another town")
    assert code_of(phone) == (403, "not_authenticated")


def test_switched_off_person_is_refused(owner: StaffMember, phone: APIClient) -> None:
    # `is_active`, the switch on the person, not on a job: at every shop at once (apps/people/models.py).
    User.objects.filter(pk=owner.user_id).update(is_active=False)
    assert code_of(phone) == (403, "not_authenticated")


def test_suspended_shop_stops_its_staff(owner: StaffMember, phone: APIClient, shop_a: Shop) -> None:
    Shop.objects.filter(pk=shop_a.pk).update(status=ShopStatus.SUSPENDED)
    assert code_of(phone) == (403, "shop.suspended")


def test_two_shops_must_choose(owner: StaffMember, phone: APIClient, shop_b: Shop) -> None:
    # One person, jobs at two shops (02 D12). Which shop's rows? Never a guess: refused until AUTH-7.
    with shop_context(shop_b):
        second = add_staff(shop=shop_b, user=owner.user, display_name="Baba", by=None)
    assert code_of(phone) == (403, "staff.choose_shop")

    # A job they have left is no job: only current ones count.
    with shop_context(shop_b):
        mark_left(second, left_on=second.started_on, by=None, reason="Moved to another town")
    assert phone.get(SIDES).status_code == 200


@pytest.mark.parametrize("route", ["/api/schema/", "/api/docs/"])
def test_api_docs_answer_the_same_for_a_suspended_session(
    owner: StaffMember, phone: APIClient, shop_a: Shop, settings: Settings, route: str
) -> None:
    # The docs hold no shop's data, and never read who is asking (DocsAccess). So a browser still holding a suspended
    # person's session gets what any visitor gets: the page on the demo, and "not found" on the real server, not a 403
    # that says the address is there.
    with shop_context(shop_a):
        suspend(owner, by=None, reason="Cash short for two weeks")

    settings.API_DOCS_PUBLIC = True
    assert phone.get(route).status_code == 200
    settings.API_DOCS_PUBLIC = False
    assert phone.get(route).status_code == 404


def test_superuser_session_stays_out_of_office(superuser_client: Client) -> None:
    # The superuser is nobody's staff (CORE-6): they keep to the admin, and read no shop through the office routes.
    assert code_of(superuser_client) == (403, "not_authenticated")


def test_logout_stops_office_routes(owner: StaffMember, phone: APIClient) -> None:
    assert phone.get(SIDES).status_code == 200
    assert phone.delete(SESSION, HTTP_X_CSRFTOKEN=csrf_token(phone)).status_code == 401
    assert code_of(phone) == (403, "not_authenticated")


def test_person_door_reads_only_a_shop_id(owner: StaffMember, shop_b: Shop) -> None:
    # The door reads past the guard, so it reads as little as its callers need: shops' ids, in one query, by the
    # person, every shop where they work, by id. The login counts them; a change to the person writes a line in each,
    # in that order (ADR-0042, SYNC-15). Everything else is read through the guard, once each shop is open.
    with CaptureQueriesContext(connection) as queries:
        found = shops_of_person(owner.user_id)

    assert found == [owner.shop_id]
    [query] = queries.captured_queries
    # The one column, under the name values_list() gives it; then the table, the person, and the order: by the first
    # column, the shop's id, which Django writes by its place in the list.
    assert query["sql"].startswith('SELECT "people_staffmember"."shop_id" AS "shop_id" FROM "people_staffmember" WHERE')
    assert '"people_staffmember"."user_id" =' in query["sql"]
    assert query["sql"].endswith("ORDER BY 1 ASC")
    # A job at a second shop: both shops, by id, whichever job came first.
    with shop_context(shop_b):
        add_staff(shop=shop_b, user=User.objects.get(pk=owner.user_id), display_name="Owner", by=None)
    assert shops_of_person(owner.user_id) == sorted([owner.shop_id, shop_b.pk])
    # Nobody's job leads to no shop.
    assert shops_of_person(uuid.uuid7()) == []
