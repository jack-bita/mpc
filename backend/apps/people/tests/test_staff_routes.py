"""apps/people/tests/test_staff_routes.py — the office routes of a shop's workers, which the workers' page (PPL-6)
calls (PPL-4; 03 §5.10). What may and may not be done is the services'; these test the doors:

    GET   /api/v1/people/staff/        every worker the shop has had, those who left included
    GET   /api/v1/people/staff/{id}/   one worker

Each worker comes with their full name, nickname, job title, first day, status and leaving day, and each role and
extra key they were given, with its side (none: every side). Only for whoever holds staff.manage on the whole shop
(PPL-4's card): the page shows roles, and later pay (WAGE-2).

    shop     side          who          what they were given
    MFANO    Dawa (D)      Baba         Owner, every side
             Vyakula (F)   Asha         Seller on Dawa, stock.count on Vyakula
                           Juma         left

Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api.views import StaffViewSet
from apps.people.models import Role, StaffMember, User
from apps.people.services import add_staff, grant_permission, mark_left, set_pin
from apps.shops.models import Shop, Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db

# The routes, written out here rather than imported: they are a promise to the app.
STAFF = "/api/v1/people/staff/"

START = date(2026, 3, 2)

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


def one(staff: StaffMember) -> str:
    return f"{STAFF}{staff.pk}/"


def client_for(staff: StaffMember) -> APIClient:
    # The way the office screens call: logged in as this person, at their shop. force_authenticate puts the person
    # straight into `request.auth`, as the real logins do (backend/conftest.py); the real login and its CSRF check are
    # the temporary password's route tests' (test_temporary_password_route.py).
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def job(shop: Shop, full_name: str, nickname: str, *, job_title: str = "") -> StaffMember:
    user = User.objects.create_user(full_name=full_name)
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=nickname, job_title=job_title, started_on=START, by=None)


@pytest.fixture
def sides(shop_a: Shop) -> dict[str, Side]:
    with shop_context(shop_a):
        return {
            "D": add_side(shop=shop_a, code="D", name="Dawa", by=None),
            "F": add_side(shop=shop_a, code="F", name="Vyakula", by=None),
        }


@pytest.fixture
def baba(shop_a: Shop, sides: dict[str, Side], give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Baba Mfano", "Baba", job_title="Mmiliki")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def asha(shop_a: Shop, sides: dict[str, Side], give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Asha Mfano", "Asha", job_title="Muuzaji wa dawa")
    give_role(staff, RoleTemplate.SELLER, sides["D"])
    with shop_context(shop_a):
        grant_permission(staff, Permission.STOCK_COUNT, side=sides["F"], by=None)
    return staff


@pytest.fixture
def juma(shop_a: Shop, sides: dict[str, Side]) -> StaffMember:
    staff = job(shop_a, "Juma Mfano", "Juma")
    with shop_context(shop_a):
        return mark_left(staff, left_on=date(2026, 9, 30), by=None, reason="Amehamia Moshi")


def test_staff_routes_name_their_permissions() -> None:
    # Pinned here, as the test clients hold every key and can't catch a route that asks for the wrong one.
    assert StaffViewSet.action_permissions == {
        "list": Permission.STAFF_MANAGE,
        "retrieve": Permission.STAFF_MANAGE,
        "temporary_password": Permission.STAFF_MANAGE,
    }


def test_the_owner_lists_every_worker_the_shop_has_had(
    baba: StaffMember, asha: StaffMember, juma: StaffMember, sides: dict[str, Side]
) -> None:
    answer = client_for(baba).get(STAFF)

    assert answer.status_code == 200
    rows = {row["display_name"]: row for row in answer.json()["results"]}
    # Juma left, and is still there: the page shows him apart, never as gone without a trace (rule 7).
    assert set(rows) == {"Baba", "Asha", "Juma"}
    with shop_context(asha.shop_id):
        seller = Role.objects.get(template=RoleTemplate.SELLER)
    [given_role] = rows["Asha"]["roles"]
    [given_key] = rows["Asha"]["keys"]
    assert rows["Asha"] == {
        "id": str(asha.pk),
        "full_name": "Asha Mfano",
        "display_name": "Asha",
        "job_title": "Muuzaji wa dawa",
        "started_on": "2026-03-02",
        "status": "active",
        "left_on": None,
        # A copied role's name is empty: the page shows its template's, translated (02 §5).
        "roles": [
            {
                "id": given_role["id"],
                "role": str(seller.pk),
                "template": "seller",
                "name": "",
                "side": str(sides["D"].pk),
            }
        ],
        "keys": [{"id": given_key["id"], "permission": "stock.count", "side": str(sides["F"].pk)}],
    }
    # A role on every side has no side.
    assert [(role["template"], role["side"]) for role in rows["Baba"]["roles"]] == [("owner", None)]
    assert (rows["Juma"]["status"], rows["Juma"]["left_on"], rows["Juma"]["roles"]) == ("left", "2026-09-30", [])


def test_the_owner_reads_one_worker(baba: StaffMember, asha: StaffMember) -> None:
    answer = client_for(baba).get(one(asha))

    assert answer.status_code == 200
    body = answer.json()
    assert (body["id"], body["full_name"]) == (str(asha.pk), "Asha Mfano")
    assert [role["template"] for role in body["roles"]] == ["seller"]
    assert [key["permission"] for key in body["keys"]] == ["stock.count"]


def test_no_secret_of_a_worker_is_shown(baba: StaffMember, asha: StaffMember) -> None:
    # Never a PIN's hash, nor when it was set, nor the person's phone or email, which PPL-10 decides on (03 §5.9).
    with shop_context(asha.shop_id):
        set_pin(asha, "4829", by=None)
    for answer in (client_for(baba).get(STAFF).json()["results"][0], client_for(baba).get(one(asha)).json()):
        assert not {"pin_hash", "pin_changed_at", "phone", "email", "password", "user"} & set(answer)


def test_another_shops_workers_never_show(baba: StaffMember, asha: StaffMember, staff_b: StaffMember) -> None:
    owner = client_for(baba)

    assert str(staff_b.pk) not in {row["id"] for row in owner.get(STAFF).json()["results"]}
    hidden = owner.get(one(staff_b))
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "not_found"


def test_the_workers_need_staff_manage_on_the_whole_shop(
    shop_a: Shop, sides: dict[str, Side], asha: StaffMember, give_role: GiveRole
) -> None:
    # A seller, a manager the owner handed no staff.manage, and one who holds it on Dawa alone: none sees the workers,
    # as a person's job belongs to the whole shop (PPL-5).
    manager = job(shop_a, "Meneja Mfano", "Meneja")
    give_role(manager, RoleTemplate.MANAGER, None)
    dawa_only = job(shop_a, "Neema Mfano", "Neema")
    give_role(dawa_only, RoleTemplate.SELLER, sides["D"])
    with shop_context(shop_a):
        grant_permission(dawa_only, Permission.STAFF_MANAGE, side=sides["D"], by=None)

    for person in (asha, manager, dawa_only):
        for address in (STAFF, one(asha)):
            refused = client_for(person).get(address)
            assert refused.status_code == 403, (person.display_name, address)
            assert refused.json()["code"] == "permission_denied"


def test_the_list_reads_the_roles_in_the_same_few_queries_however_many_workers(
    shop_a: Shop, sides: dict[str, Side], baba: StaffMember, asha: StaffMember, give_role: GiveRole
) -> None:
    # Each worker's roles and keys are read for the whole page at once, not one worker at a time: a shop of thirty
    # workers asks as often as a shop of two.
    owner = client_for(baba)
    with CaptureQueriesContext(connection) as two:
        owner.get(STAFF)
    for number in range(3):
        worker = job(shop_a, f"Mfanyakazi {number} Mfano", f"Mfanyakazi {number}")
        give_role(worker, RoleTemplate.WORKER, sides["F"])
    with CaptureQueriesContext(connection) as five:
        answer = owner.get(STAFF)

    assert len(answer.json()["results"]) == 5
    assert len(five.captured_queries) == len(two.captured_queries)
