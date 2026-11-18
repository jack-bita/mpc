"""apps/people/tests/test_staff_routes.py — the office routes of a shop's workers, which the workers' page (PPL-6)
calls (PPL-4; 03 §5.10). What may and may not be done is the services'; these test the doors:

    GET   /api/v1/people/staff/        every worker the shop has had, those who left included
    GET   /api/v1/people/staff/{id}/   one worker
    POST  /api/v1/people/staff/        a new worker: the person and their job in one step, with the app's own id;
                                       or, with `hire_again`, a new job for a worker who left (PPL-11)
    PATCH /api/v1/people/staff/{id}/   fix their details, from the version the page read, with a reason (PPL-10)
    POST  /api/v1/people/staff/{id}/suspend/     stop a worker for a while, with a reason
    POST  /api/v1/people/staff/{id}/unsuspend/   bring them back, with a reason
    POST  /api/v1/people/staff/{id}/leave/       record their last day, with a reason

Each worker comes with their full name, phone, nickname, job title, first day, status and leaving day, each role and
extra key they were given, with its side (none: every side), the version a fix sends back, and, for a job that ended,
the job the person came back as, once they are hired again (PPL-11). Only for whoever
holds staff.manage on the whole shop (PPL-4's card): the page shows roles, and later pay (WAGE-2).

    shop     side          who          what they were given
    MFANO    Dawa (D)      Baba         Owner, every side
             Vyakula (F)   Asha         Seller on Dawa, stock.count on Vyakula
                           Juma         left

Fake data only: the repo is public (03 §10).
"""

import uuid
from collections.abc import Callable
from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.control.models import AuditAction, AuditEvent, EditEvent
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api.views import StaffViewSet
from apps.people.models import Role, StaffMember, User
from apps.people.services import add_staff, add_worker, grant_permission, mark_left, set_pin, suspend
from apps.people.services import hire_again as services_hire_again
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.shops.services import add_side
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

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
        "create": Permission.STAFF_MANAGE,
        "partial_update": Permission.STAFF_MANAGE,
        "suspend": Permission.STAFF_MANAGE,
        "unsuspend": Permission.STAFF_MANAGE,
        "leave": Permission.STAFF_MANAGE,
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
        # No phone yet: it is added on her page (PPL-10).
        "phone": None,
        "display_name": "Asha",
        "job_title": "Muuzaji wa dawa",
        "started_on": "2026-03-02",
        "status": "active",
        "left_on": None,
        "switched_off": False,
        # The job's version, which a fix sends back: nobody has fixed her yet.
        "version": 1,
        # Only a job that ended can have been come back from.
        "hired_again_as": None,
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
    # Never a PIN's hash, nor when it was set, nor the person's email or password (03 §5.9). The phone is shown, to
    # whoever manages the workers, as they type it and a temporary password needs it (PPL-10); never to a laptop
    # (apps/sync/tests/test_bootstrap_secrets.py).
    with shop_context(asha.shop_id):
        set_pin(asha, "4829", by=None)
    User.objects.filter(pk=asha.user_id).update(phone="+255712345678", email="asha@example.com")
    for answer in (client_for(baba).get(STAFF).json()["results"][0], client_for(baba).get(one(asha)).json()):
        assert not {"pin_hash", "pin_changed_at", "email", "password", "user"} & set(answer)
    assert client_for(baba).get(one(asha)).json()["phone"] == "+255712345678"


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


# --- Adding a worker


def new_worker(**changes: object) -> dict[str, object]:
    # Juma, as the workers' page sends him: with the id the app made itself (ADR-0007).
    return {
        "id": str(uuid.uuid7()),
        "full_name": "Juma Hamisi Mfano",
        "display_name": "Juma",
        "job_title": "Mpima pumba",
        "started_on": "2026-11-16",
        **changes,
    }


def jobs_named(shop: Shop, nickname: str) -> list[StaffMember]:
    with shop_context(shop):
        return list(StaffMember.objects.filter(display_name=nickname).select_related("user"))


def test_the_owner_adds_a_worker_in_one_step(shop_a: Shop, baba: StaffMember) -> None:
    sent = new_worker()

    answer = client_for(baba).post(STAFF, sent)

    assert answer.status_code == 201
    body = answer.json()
    assert {key: body[key] for key in ("id", "full_name", "display_name", "job_title", "started_on", "status")} == {
        "id": sent["id"],
        "full_name": "Juma Hamisi Mfano",
        "display_name": "Juma",
        "job_title": "Mpima pumba",
        "started_on": "2026-11-16",
        "status": "active",
    }
    # No role and no key yet (PPL-7), nor a PIN (PPL-8): he can't log in until those.
    assert (body["roles"], body["keys"]) == ([], [])
    [juma] = jobs_named(shop_a, "Juma")
    assert str(juma.pk) == sent["id"]
    # The person and the job, made together: a worker logs in with a PIN, so the person has no password at all.
    assert juma.user.full_name == "Juma Hamisi Mfano"
    assert not juma.user.has_usable_password()
    assert juma.created_by_id == baba.pk


def test_the_first_day_is_today_if_none_is_sent(shop_a: Shop, baba: StaffMember) -> None:
    sent = new_worker()
    del sent["started_on"]
    del sent["job_title"]

    body = client_for(baba).post(STAFF, sent).json()

    assert body["started_on"] == shop_today(shop_a).isoformat()
    assert body["job_title"] == ""


def test_a_worker_sent_twice_is_one_worker(shop_a: Shop, baba: StaffMember) -> None:
    # The phone's answer was lost on a slow network, and it sends again: the same id, so the same Juma, not two.
    sent = new_worker()
    owner = client_for(baba)

    first = owner.post(STAFF, sent)
    again = owner.post(STAFF, sent)

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert len(jobs_named(shop_a, "Juma")) == 1
    assert User.objects.filter(full_name="Juma Hamisi Mfano").count() == 1


def test_an_id_another_shop_holds_is_refused_and_makes_no_person(baba: StaffMember, staff_b: StaffMember) -> None:
    # PPL-4's review: the id names the new job, and another shop's job has it. Refused with the code that tells
    # nothing of that job (CreateOnceMixin), and the person made first is undone with the refused job.
    refused = client_for(baba).post(STAFF, new_worker(id=str(staff_b.pk)))

    assert refused.status_code == 400
    assert refused.json()["fields"] == {"id": ["id.taken"]}
    assert not User.objects.filter(full_name="Juma Hamisi Mfano").exists()


@pytest.mark.django_db(transaction=True)
def test_one_worker_sent_twice_at_once_is_one_worker(shop_a: Shop, sides: dict[str, Side], baba: StaffMember) -> None:
    # PPL-4's review: the first send has made Juma and not yet committed when the second arrives, so the second can't
    # see him: it makes a person too, and its job waits on the first's id in the database. Once the first commits, the
    # second's job is refused, its person undone with it, and the stored Juma is the answer (CreateOnceMixin's twin).
    sent = new_worker()

    def the_second_send() -> object:
        return client_for(baba).post(STAFF, sent)

    with shop_context(shop_a), transaction.atomic():
        add_worker(
            shop=shop_a,
            full_name="Juma Hamisi Mfano",
            display_name="Juma",
            staff_id=uuid.UUID(str(sent["id"])),
            by=baba,
        )
        second, ended = in_another_transaction(the_second_send)
        wait_until_someone_waits_for_me()
    second.join(timeout=5)

    assert not second.is_alive(), "The second send still waits after the first committed."
    answer = ended[0]
    assert (answer.status_code, answer.json()["id"]) == (201, sent["id"])  # type: ignore[attr-defined]
    assert len(jobs_named(shop_a, "Juma")) == 1
    assert User.objects.filter(full_name="Juma Hamisi Mfano").count() == 1


def test_a_nickname_another_current_worker_has_is_refused(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Nicknames name people on the PIN tiles and receipts, so two current workers never share one, whatever the
    # letter case (02 §5). Refused whole: no person is left behind without a job.
    refused = client_for(baba).post(STAFF, new_worker(full_name="Asha Juma Mfano", display_name="asha"))

    assert refused.status_code == 400
    assert refused.json()["code"] == "staff.display_name_taken"
    assert not User.objects.filter(full_name="Asha Juma Mfano").exists()


def test_a_nickname_of_someone_who_left_may_be_used_again(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # The Juma who left keeps his row (rule 7), and a new Juma may be called Juma.
    assert client_for(baba).post(STAFF, new_worker()).status_code == 201
    assert sorted(job.status for job in jobs_named(shop_a, "Juma")) == ["active", "left"]


def test_blank_names_are_refused_beside_their_boxes(baba: StaffMember) -> None:
    # Spaces alone are no name: each box gets its own code, so the page says it beside the box (UI-2).
    refused = client_for(baba).post(STAFF, new_worker(full_name="   ", display_name=""))

    assert refused.status_code == 400
    assert refused.json()["fields"] == {"full_name": ["blank"], "display_name": ["blank"]}


def test_adding_a_worker_needs_staff_manage_on_the_whole_shop(
    shop_a: Shop, sides: dict[str, Side], give_role: GiveRole
) -> None:
    manager = job(shop_a, "Meneja Mfano", "Meneja")
    give_role(manager, RoleTemplate.MANAGER, None)

    refused = client_for(manager).post(STAFF, new_worker())

    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    assert jobs_named(shop_a, "Juma") == []


def test_the_service_asks_the_key_again(shop_a: Shop, sides: dict[str, Side], give_role: GiveRole) -> None:
    # Whatever calls it, not the route alone (PPL-5): a manager the owner handed no staff.manage adds nobody.
    manager = job(shop_a, "Meneja Mfano", "Meneja")
    give_role(manager, RoleTemplate.MANAGER, None)

    with shop_context(shop_a), pytest.raises(PermissionDenied):
        add_worker(shop=shop_a, full_name="Juma Hamisi Mfano", display_name="Juma", by=manager)

    assert not User.objects.filter(full_name="Juma Hamisi Mfano").exists()


# --- A phone on Ongeza, and a worker who comes back (PPL-11)


def test_the_owner_adds_a_worker_with_a_phone(baba: StaffMember) -> None:
    body = client_for(baba).post(STAFF, new_worker(phone="0754 000 111")).json()

    assert body["phone"] == "+255754000111"


def test_the_phone_of_a_worker_who_left_names_him(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # Baba types Juma's phone on Ongeza, forgetting he worked here: nobody is made, and the answer names Juma's old job,
    # his full name and his last day, so the page offers Mwajiri tena. Never the phone.
    User.objects.filter(pk=juma.user_id).update(phone="+255754000111")

    refused = client_for(baba).post(STAFF, new_worker(phone="0754 000 111"))

    assert refused.status_code == 400
    body = refused.json()
    assert (body["code"], body["params"]) == (
        "staff.left_here",
        {"staff": str(juma.pk), "full_name": "Juma Mfano", "left_on": "2026-09-30"},
    )
    assert "+255754000111" not in refused.content.decode()
    assert [job.pk for job in jobs_named(shop_a, "Juma")] == [juma.pk]


def test_a_phone_in_use_says_only_that(baba: StaffMember, staff_b: StaffMember) -> None:
    # Shop B's worker's phone: in use, and nothing of whose, or where.
    User.objects.filter(pk=staff_b.user_id).update(phone="+255754000111")

    refused = client_for(baba).post(STAFF, new_worker(phone="0754 000 111"))

    assert refused.status_code == 400
    assert (refused.json()["fields"], refused.json()["params"]) == ({"phone": ["unique"]}, {})
    assert "Staff Demo B" not in refused.content.decode()


def test_another_shops_leavers_phone_is_only_in_use(baba: StaffMember, staff_b: StaffMember) -> None:
    # The worker who left shop B, and works nowhere now, is shop B's to name. Typed at shop A, his phone is only in use:
    # no name, no last day, no job's id.
    with shop_context(staff_b.shop_id):
        mark_left(staff_b, left_on=shop_today(staff_b.shop), by=None, reason="Amehamia Moshi")
    User.objects.filter(pk=staff_b.user_id).update(phone="+255754000111")

    refused = client_for(baba).post(STAFF, new_worker(phone="0754 000 111"))

    assert refused.status_code == 400
    assert (refused.json()["code"], refused.json()["fields"], refused.json()["params"]) == (
        "invalid",
        {"phone": ["unique"]},
        {},
    )
    assert "Staff Demo B" not in refused.content.decode()
    assert str(staff_b.pk) not in refused.content.decode()


def hire_again(old: StaffMember, **changes: object) -> dict[str, object]:
    # Mwajiri tena, as the page sends it: the old job's id, and the new job's own id, nickname, title and first day.
    return {
        "id": str(uuid.uuid7()),
        "hire_again": str(old.pk),
        "display_name": "Juma",
        "job_title": "Mpima pumba",
        "started_on": "2026-11-16",
        **changes,
    }


def test_the_owner_hires_a_worker_again(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    sent = hire_again(juma)

    answer = client_for(baba).post(STAFF, sent)

    assert answer.status_code == 201
    body = answer.json()
    assert {key: body[key] for key in ("id", "full_name", "display_name", "started_on", "status", "left_on")} == {
        "id": sent["id"],
        "full_name": "Juma Mfano",
        "display_name": "Juma",
        "started_on": "2026-11-16",
        "status": "active",
        "left_on": None,
    }
    # The same person, with two jobs: the old one as it was.
    old, new = sorted(jobs_named(shop_a, "Juma"), key=lambda job: job.started_on)
    assert (old.pk, old.status, str(new.pk), new.user_id) == (juma.pk, "left", sent["id"], juma.user_id)
    assert new.created_by_id == baba.pk


def test_a_hire_again_sent_twice_is_one_job(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # The answer was lost and the page sends again: the same id, so the same job, not "works here already".
    sent = hire_again(juma)
    owner = client_for(baba)

    first = owner.post(STAFF, sent)
    again = owner.post(STAFF, sent)

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()
    assert len(jobs_named(shop_a, "Juma")) == 2


@pytest.mark.django_db(transaction=True)
def test_one_hire_again_sent_twice_at_once_is_one_job(
    shop_a: Shop, sides: dict[str, Side], baba: StaffMember, juma: StaffMember
) -> None:
    # The review: the first send holds Juma's person locked, his new job made and not yet committed, when its own copy
    # arrives. The copy waits on the lock, then finds him back already (staff.already_member); its id names the first's
    # job, so the route answers with that job (CreateOnceMixin's twin), not a refusal, and there is one job, not two.
    sent = hire_again(juma)

    def the_second_send() -> object:
        return client_for(baba).post(STAFF, sent)

    with shop_context(shop_a), transaction.atomic():
        services_hire_again(
            juma,
            display_name="Juma",
            job_title="Mpima pumba",
            started_on=date(2026, 11, 16),
            staff_id=uuid.UUID(str(sent["id"])),
            by=baba,
        )
        second, ended = in_another_transaction(the_second_send)
        wait_until_someone_waits_for_me()
    second.join(timeout=5)

    assert not second.is_alive(), "The second send still waits after the first committed."
    answer = ended[0]
    assert (answer.status_code, answer.json()["id"]) == (201, sent["id"])  # type: ignore[attr-defined]
    assert len(jobs_named(shop_a, "Juma")) == 2


def test_another_shops_job_is_not_found_for_a_hire_again(baba: StaffMember, staff_b: StaffMember) -> None:
    refused = client_for(baba).post(STAFF, hire_again(staff_b))

    assert refused.status_code == 400
    assert refused.json()["fields"] == {"hire_again": ["does_not_exist"]}


def test_a_hire_agains_refusals_reach_the_page(baba: StaffMember, asha: StaffMember, juma: StaffMember) -> None:
    owner = client_for(baba)

    assert owner.post(STAFF, hire_again(asha, display_name="Asha")).json()["code"] == "staff.not_left"
    before = owner.post(STAFF, hire_again(juma, started_on="2026-09-29"))
    assert before.json()["fields"] == {"started_on": ["staff.back_before_left"]}


def test_one_working_at_another_shop_is_refused_naming_no_shop(
    shop_a: Shop, shop_b: Shop, baba: StaffMember, juma: StaffMember
) -> None:
    # Juma works at shop B by now: refused until AUTH-7 (ADR-0045), and the answer says only that, never which shop,
    # its name, its code or its id, nor his job there.
    with shop_context(shop_b):
        at_b = add_staff(shop=shop_b, user=User.objects.get(pk=juma.user_id), display_name="Juma", by=None)

    refused = client_for(baba).post(STAFF, hire_again(juma))

    assert refused.status_code == 400
    assert (refused.json()["code"], refused.json()["fields"], refused.json()["params"]) == (
        "staff.works_elsewhere",
        {},
        {},
    )
    body = refused.content.decode()
    for secret in ("Duka Jingine", "JINGINE", str(shop_b.pk), str(at_b.pk)):
        assert secret not in body
    assert len(jobs_named(shop_a, "Juma")) == 1


def test_a_full_name_is_needed_only_for_a_new_person(baba: StaffMember) -> None:
    # A worker hired again keeps his own (Badilisha fixes it); a new one needs one.
    sent = new_worker()
    del sent["full_name"]

    refused = client_for(baba).post(STAFF, sent)

    assert refused.status_code == 400
    assert refused.json()["fields"] == {"full_name": ["required"]}


def test_hiring_again_needs_staff_manage(shop_a: Shop, asha: StaffMember, juma: StaffMember) -> None:
    refused = client_for(asha).post(STAFF, hire_again(juma))

    assert refused.status_code == 403
    assert len(jobs_named(shop_a, "Juma")) == 1


def test_the_old_job_says_who_he_came_back_as(baba: StaffMember, juma: StaffMember) -> None:
    # Once he is back, his old job's page links to the new one, in place of Mwajiri tena (Jack: A, the old job stays
    # under Walioondoka).
    owner = client_for(baba)
    assert owner.get(one(juma)).json()["hired_again_as"] is None

    new = owner.post(STAFF, hire_again(juma)).json()

    assert owner.get(one(juma)).json()["hired_again_as"] == new["id"]
    rows = {row["id"]: row for row in owner.get(STAFF).json()["results"]}
    assert (rows[str(juma.pk)]["hired_again_as"], rows[new["id"]]["hired_again_as"]) == (new["id"], None)


def test_the_list_reads_who_came_back_in_the_same_few_queries(
    shop_a: Shop, baba: StaffMember, juma: StaffMember
) -> None:
    # Who came back is read for the whole page at once, as the roles are: thirty workers who left ask as often as one.
    owner = client_for(baba)
    with CaptureQueriesContext(connection) as one_left:
        owner.get(STAFF)
    for number in range(3):
        worker = job(shop_a, f"Mfanyakazi {number} Mfano", f"Mfanyakazi {number}")
        with shop_context(shop_a):
            mark_left(worker, left_on=date(2026, 9, 30), by=None, reason="Amehamia Moshi")
    with CaptureQueriesContext(connection) as four_left:
        answer = owner.get(STAFF)

    assert len(answer.json()["results"]) == 5
    assert len(four_left.captured_queries) == len(one_left.captured_queries)


# --- Suspending, bringing back, marking left


def change(staff: StaffMember, action: str) -> str:
    return f"{one(staff)}{action}/"


def status_of(staff: StaffMember) -> str:
    with shop_context(staff.shop_id):
        return StaffMember.objects.get(pk=staff.pk).status


def test_the_owner_suspends_brings_back_and_marks_a_worker_left(baba: StaffMember, asha: StaffMember) -> None:
    owner = client_for(baba)

    suspended = owner.post(change(asha, "suspend"), {"reason": "Hakuja kazini siku 3"})
    assert suspended.status_code == 200
    # The answer is the worker as she is now, as the list shows her, so the page needs no second read.
    assert (suspended.json()["id"], suspended.json()["status"]) == (str(asha.pk), "suspended")

    back = owner.post(change(asha, "unsuspend"), {"reason": "Amerudi kazini"})
    assert (back.status_code, back.json()["status"]) == (200, "active")

    left = owner.post(change(asha, "leave"), {"reason": "Amehamia Moshi", "left_on": "2026-11-14"})
    assert left.status_code == 200
    assert (left.json()["status"], left.json()["left_on"]) == ("left", "2026-11-14")


def test_a_suspension_from_the_route_writes_both_books(baba: StaffMember, asha: StaffMember) -> None:
    # CTRL-2's review: through the route, as the page will do it, both books name the worker and the owner who acted:
    # the audit trail with the reason, the edit history with what changed (02 §13).
    client_for(baba).post(change(asha, "suspend"), {"reason": "Hakuja kazini siku 3"})

    with shop_context(asha.shop_id):
        [line] = AuditEvent.objects.filter(subject_type="staff", subject_id=asha.pk)
        [edit] = EditEvent.objects.filter(subject_type="staff", subject_id=asha.pk)
    assert (line.action, line.created_by_id, line.reason) == (
        AuditAction.STAFF_SUSPEND,
        baba.pk,
        "Hakuja kazini siku 3",
    )
    assert edit.created_by_id == baba.pk
    assert (edit.before, edit.after) == ({"status": "active"}, {"status": "suspended"})


@pytest.mark.parametrize("action", ["suspend", "unsuspend", "leave"])
def test_each_change_of_status_needs_a_reason(action: str, baba: StaffMember, asha: StaffMember) -> None:
    if action == "unsuspend":
        with shop_context(asha.shop_id):
            suspend(asha, by=None, reason="Uchunguzi")
    before = status_of(asha)

    refused = client_for(baba).post(change(asha, action), {"reason": "   ", "left_on": "2026-11-14"})

    assert refused.status_code == 400
    assert refused.json()["code"] == "staff.reason_required"
    assert status_of(asha) == before


def test_a_leaving_day_ahead_is_refused(shop_a: Shop, baba: StaffMember, asha: StaffMember) -> None:
    # Leaving takes effect at once: "leaves on Friday" typed on Monday would stop her PIN four days early (02 §5).
    tomorrow = shop_today(shop_a) + timedelta(days=1)

    refused = client_for(baba).post(
        change(asha, "leave"), {"reason": "Atahamia Moshi", "left_on": tomorrow.isoformat()}
    )

    assert refused.status_code == 400
    assert refused.json()["code"] == "staff.left_in_future"
    assert status_of(asha) == "active"


def test_a_leaving_day_must_be_sent(baba: StaffMember, asha: StaffMember) -> None:
    refused = client_for(baba).post(change(asha, "leave"), {"reason": "Amehamia Moshi"})

    assert refused.status_code == 400
    assert refused.json()["fields"] == {"left_on": ["required"]}


@pytest.mark.parametrize("action", ["suspend", "unsuspend", "leave"])
def test_changes_of_status_need_staff_manage(
    action: str, shop_a: Shop, sides: dict[str, Side], asha: StaffMember, give_role: GiveRole
) -> None:
    manager = job(shop_a, "Meneja Mfano", "Meneja")
    give_role(manager, RoleTemplate.MANAGER, None)
    before = status_of(asha)

    refused = client_for(manager).post(change(asha, action), {"reason": "Hakuja kazini", "left_on": "2026-11-14"})

    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    assert status_of(asha) == before


def test_who_may_reaches_the_route(shop_a: Shop, baba: StaffMember, give_role: GiveRole) -> None:
    # The service's rule answers through the route with its own code, for the page to say: a manager with the key
    # still can't suspend the owner (02 §5).
    meneja = job(shop_a, "Meneja Mfano", "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(meneja, Permission.STAFF_MANAGE, side=None, by=None)

    refused = client_for(meneja).post(change(baba, "suspend"), {"reason": "Hakuja kazini"})

    assert refused.status_code == 400
    assert refused.json()["code"] == "staff.superuser_only"
    assert status_of(baba) == "active"


def test_another_shops_worker_is_not_found(baba: StaffMember, staff_b: StaffMember) -> None:
    hidden = client_for(baba).post(change(staff_b, "suspend"), {"reason": "Hakuja kazini"})

    assert hidden.status_code == 404
    assert status_of(staff_b) == "active"


WHY = "Niliandika vibaya"


def test_the_owner_fixes_a_workers_details(baba: StaffMember, asha: StaffMember) -> None:
    # Only the boxes the page changed, the version it read, and why. The answer is Asha as she is now, with her new
    # version, so the page needs no second read; her phone as it is stored.
    fixed = client_for(baba).patch(
        one(asha),
        {"version": 1, "reason": WHY, "full_name": "Asha Mfano Mpya", "phone": "0712 345 678", "job_title": "Muuzaji"},
        format="json",
    )

    assert fixed.status_code == 200
    body = fixed.json()
    assert (body["full_name"], body["phone"], body["job_title"], body["display_name"], body["version"]) == (
        "Asha Mfano Mpya",
        "+255712345678",
        "Muuzaji",
        "Asha",
        2,
    )
    with shop_context(asha.shop_id):
        [line] = AuditEvent.objects.filter(subject_type="staff", subject_id=asha.pk)
    assert (line.action, line.created_by_id, line.reason) == (AuditAction.STAFF_DETAILS_CHANGED, baba.pk, WHY)


def test_a_fix_from_an_old_copy_is_a_conflict(baba: StaffMember, asha: StaffMember) -> None:
    # Meneja fixed Asha after Baba read her page: Baba's fix, from version 1, would undo Meneja's.
    owner = client_for(baba)
    owner.patch(one(asha), {"version": 1, "reason": WHY, "job_title": "Muuzaji"}, format="json")

    refused = owner.patch(one(asha), {"version": 1, "reason": WHY, "job_title": "Fundi"}, format="json")

    assert refused.status_code == 409
    assert refused.json()["code"] == "version_conflict"
    assert owner.get(one(asha)).json()["job_title"] == "Muuzaji"


def test_a_fix_needs_the_version_and_a_reason(baba: StaffMember, asha: StaffMember) -> None:
    owner = client_for(baba)

    unread = owner.patch(one(asha), {"reason": WHY, "job_title": "Muuzaji"}, format="json")
    assert (unread.status_code, unread.json()["fields"]) == (400, {"version": ["required"]})

    no_reason = owner.patch(one(asha), {"version": 1, "reason": "   ", "job_title": "Muuzaji"}, format="json")
    assert (no_reason.status_code, no_reason.json()["code"]) == (400, "staff.reason_required")

    assert owner.get(one(asha)).json()["job_title"] == "Muuzaji wa dawa"


def test_a_fixs_refusals_come_beside_their_boxes(baba: StaffMember, asha: StaffMember) -> None:
    # Spaces alone are no name, refused by the route's own check, as on Ongeza; a wrong phone by the service, under its
    # box too, so the page says each beside its own box.
    owner = client_for(baba)

    blank = owner.patch(one(asha), {"version": 1, "reason": WHY, "full_name": "   "}, format="json")
    assert (blank.status_code, blank.json()["fields"]) == (400, {"full_name": ["blank"]})

    wrong = owner.patch(one(asha), {"version": 1, "reason": WHY, "phone": "12345"}, format="json")
    assert (wrong.status_code, wrong.json()["fields"]) == (400, {"phone": ["phone.invalid"]})


def test_fixing_a_worker_needs_staff_manage(
    shop_a: Shop, sides: dict[str, Side], asha: StaffMember, give_role: GiveRole
) -> None:
    # A manager the owner handed no staff.manage: today he could put his own phone on Asha's job.
    manager = job(shop_a, "Meneja Mfano", "Meneja")
    give_role(manager, RoleTemplate.MANAGER, None)

    refused = client_for(manager).patch(
        one(asha), {"version": 1, "reason": WHY, "phone": "0712 345 678"}, format="json"
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    assert User.objects.get(pk=asha.user_id).phone is None


def test_who_may_fix_reaches_the_route(shop_a: Shop, baba: StaffMember, give_role: GiveRole) -> None:
    # A manager with the key still can't fix the owner, nor himself (02 §5): each said by its own code.
    meneja = job(shop_a, "Meneja Mfano", "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(meneja, Permission.STAFF_MANAGE, side=None, by=None)

    for person, code in ((baba, "staff.superuser_only"), (meneja, "staff.own")):
        refused = client_for(meneja).patch(one(person), {"version": 1, "reason": WHY, "job_title": "X"}, format="json")
        assert (refused.status_code, refused.json()["code"]) == (400, code)


def test_another_shops_worker_is_not_found_for_a_fix(baba: StaffMember, staff_b: StaffMember) -> None:
    hidden = client_for(baba).patch(one(staff_b), {"version": 1, "reason": WHY, "job_title": "X"}, format="json")

    assert hidden.status_code == 404
    with shop_context(staff_b.shop_id):
        assert StaffMember.objects.get(pk=staff_b.pk).version == 1


def test_a_create_sent_again_shows_no_worker_to_whoever_lacks_the_key(
    shop_a: Shop, sides: dict[str, Side], baba: StaffMember, asha: StaffMember
) -> None:
    # PPL-4's review: every laptop knows each worker's id (the PIN tiles). Sent as a new worker's id by Asha, who holds
    # no staff.manage, it found Baba and answered with his row, his Owner role among it. Now refused, as the list is.
    dawa_only = job(shop_a, "Neema Mfano", "Neema")
    with shop_context(shop_a):
        grant_permission(dawa_only, Permission.STAFF_MANAGE, side=sides["D"], by=None)

    for person in (asha, dawa_only):
        refused = client_for(person).post(STAFF, new_worker(id=str(baba.pk)))
        assert refused.status_code == 403, person.display_name
        assert refused.json()["code"] == "permission_denied"
        assert "Baba Mfano" not in refused.content.decode()


def test_a_person_the_superuser_switched_off_is_shown_so(baba: StaffMember, asha: StaffMember) -> None:
    # PPL-4's review: the superuser switched Asha's person off in the admin. Her job still says "active", but she logs
    # in nowhere, and no laptop shows her (staff_rows, SYNC-15): the list says so, or Baba would wonder why.
    User.objects.filter(pk=asha.user_id).update(is_active=False)

    rows = {row["display_name"]: row for row in client_for(baba).get(STAFF).json()["results"]}

    assert (rows["Asha"]["status"], rows["Asha"]["switched_off"]) == ("active", True)
    assert rows["Baba"]["switched_off"] is False
    assert client_for(baba).get(one(asha)).json()["switched_off"] is True
