"""apps/people/tests/test_giving_roles.py — how a shop gets its roles, and how a person is given one, or one extra
permission (02 §5).

Each shop holds its own copy of the six templates, made once. A role or a permission is given only inside its own
shop (T1), never to someone who has left, and the row keeps who gave it. Only someone with staff.manage there may
give, and only what they hold there themselves (Jack, 29 Oct 2026); the Owner role, only the superuser (Jack, PPL-7:
A). A give the app sends twice, by its id, is one row (ADR-0007). Fake data only: the repo is public (03 §10).
"""

import uuid
from collections.abc import Callable

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.core.permissions import ROLE_TEMPLATES, Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import PermissionGrant, Role, RoleAssignment, StaffMember
from apps.people.services import (
    add_worker,
    assign_role,
    copy_role_templates,
    end_role,
    grant_permission,
    mark_left,
    suspend,
)
from apps.shops.models import Shop, Side
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.mark.django_db(transaction=True)
def test_two_owners_giving_each_other_one_role_take_turns(
    staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Each gives the other the Manager role at once. Both lock that role, so they take turns, and the second checks the
    # role as the first left it. With no lock, the second would never wait, and could check a role an owner was changing
    # at that moment. Neither ends in a deadlock, though each locks a different person and each line links to the other.
    give_role(staff_a, RoleTemplate.OWNER, None)
    give_role(staff_a2, RoleTemplate.OWNER, None)
    with shop_context(staff_a.shop_id):
        role = Role.objects.get(template=RoleTemplate.MANAGER)

    def second() -> RoleAssignment:
        with shop_context(staff_a.shop_id):
            return assign_role(staff_a2, role, side=None, by=staff_a)

    with shop_context(staff_a.shop_id), transaction.atomic():
        assign_role(staff_a, role, side=None, by=staff_a2)
        thread, ended = in_another_transaction(second)
        wait_until_someone_waits_for_me()
    thread.join(timeout=5)
    assert isinstance(ended[0], RoleAssignment)


def test_shop_gets_its_own_copy_of_each_template(shop_a: Shop) -> None:
    # Six roles, each holding its template's codes, made by the system (no `created_by`): the shop's own rows, which
    # its owner can change later without touching the templates or any other shop.
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        stored = {role.template: role for role in Role.objects.all()}
    assert set(roles) == set(stored) == set(RoleTemplate)
    for template, role in stored.items():
        assert set(role.permissions) == ROLE_TEMPLATES[RoleTemplate(template)]
        assert role.created_by_id is None


def test_templates_copied_once_per_shop(shop_a: Shop) -> None:
    # A second copy would give the shop two Managers.
    with shop_context(shop_a):
        copy_role_templates(shop_a)
        with pytest.raises(ValidationError) as refused:
            copy_role_templates(shop_a)
    assert [error.code for error in refused.value.error_dict["__all__"]] == ["role.template_taken"]


def test_role_assignment_stays_in_one_shop(
    shop_a: Shop, shop_b: Shop, side_a: Side, side_b: Side, staff_a: StaffMember, staff_b: StaffMember
) -> None:
    # T1: the role, the side and whoever gives them all belong to the person's own shop. Shop B's Owner role, or its
    # side, given at shop A would sit in A's rows, pointing at rows A's guard never shows.
    with shop_context(shop_b):
        owner_b = copy_role_templates(shop_b)[RoleTemplate.OWNER]
    with shop_context(shop_a):
        owner_a = copy_role_templates(shop_a)[RoleTemplate.OWNER]
        for role, side, by in ((owner_b, side_a, None), (owner_a, side_b, None), (owner_a, side_a, staff_b)):
            with pytest.raises(ValidationError) as refused:
                assign_role(staff_a, role, side=side, by=by)
            assert refused.value.code == "staff.other_shop"
        for side, by in ((side_b, None), (side_a, staff_b)):
            with pytest.raises(ValidationError) as refused:
                grant_permission(staff_a, Permission.STOCK_COUNT, side=side, by=by)
            assert refused.value.code == "staff.other_shop"
        assert not RoleAssignment.objects.exists()
        assert not PermissionGrant.objects.exists()


def test_left_staff_gets_no_role(shop_a: Shop, side_a: Side, staff_a: StaffMember) -> None:
    # A person who has left is gone for good: a role or a permission given now would come back with nobody, since a
    # returning worker gets a new job (02 §5).
    with shop_context(shop_a):
        worker = copy_role_templates(shop_a)[RoleTemplate.WORKER]
        mark_left(staff_a, left_on=staff_a.started_on, by=None, reason="Moved to another town")
        with pytest.raises(ValidationError) as giving_role:
            assign_role(staff_a, worker, side=side_a, by=None)
        with pytest.raises(ValidationError) as granting:
            grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=None)
    assert giving_role.value.code == granting.value.code == "staff.left"


def test_role_given_keeps_who_gave_it(shop_a: Shop, side_a: Side, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # Who gave a role, and when, are the row's own `created_by` and `created_at` (02 §1): Staff A2, the owner, gives
    # Staff A the Worker role, and an extra key of a known code only.
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        worker = roles[RoleTemplate.WORKER]
        assign_role(staff_a2, roles[RoleTemplate.OWNER], side=None, by=None)
        given = assign_role(staff_a, worker, side=side_a, by=staff_a2)
        granted = grant_permission(staff_a, Permission.STOCK_COUNT, side=None, by=staff_a2)
        with pytest.raises(ValidationError) as typo:
            grant_permission(staff_a, "stock.cont", side=None, by=staff_a2)
    assert given.created_by_id == granted.created_by_id == staff_a2.pk
    assert [error.code for error in typo.value.error_dict["__all__"]] == ["permission.unknown"]


def test_giving_a_role_needs_staff_manage(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # A Manager runs the shop, but adding workers and giving them roles is the owner's (staff.manage, Jack): with
    # every Manager code on every side, Staff A2 still can't give the Worker role, until the owner grants staff.manage.
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        assign_role(staff_a2, roles[RoleTemplate.MANAGER], side=None, by=None)
        with pytest.raises(PermissionDenied):
            assign_role(staff_a, roles[RoleTemplate.WORKER], side=side_a, by=staff_a2)
        grant_permission(staff_a2, Permission.STAFF_MANAGE, side=None, by=None)
        assign_role(staff_a, roles[RoleTemplate.WORKER], side=side_a, by=staff_a2)


def test_manager_cannot_make_himself_owner(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Given staff.manage to add a loader, a Manager may give only what he holds himself: not the Owner role, which
    # holds the owner's own approvals, to himself or to anyone (the superuser's alone, PPL-7); not one of those
    # approvals as an extra key; and, holding staff.manage on Dawa alone, nothing for every side.
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        assign_role(staff_a2, roles[RoleTemplate.MANAGER], side=None, by=None)
        grant_permission(staff_a2, Permission.STAFF_MANAGE, side=side_a, by=None)
        for receiver in (staff_a2, staff_a):
            with pytest.raises(ValidationError) as refused:
                assign_role(receiver, roles[RoleTemplate.OWNER], side=side_a, by=staff_a2)
            assert refused.value.code == "role.superuser_only"
        with pytest.raises(PermissionDenied):
            grant_permission(staff_a, Permission.DRAWER_APPROVE, side=side_a, by=staff_a2)
        with pytest.raises(PermissionDenied):
            assign_role(staff_a, roles[RoleTemplate.WORKER], side=None, by=staff_a2)
        # What he holds on Dawa, he may give on Dawa.
        assign_role(staff_a, roles[RoleTemplate.WORKER], side=side_a, by=staff_a2)


def test_giver_check_reads_the_role_as_stored(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # The role handed in may be a copy whose codes were changed in memory and never saved: here the Manager role, made
    # to say "sale.write" only. The check reads the role as stored, so a Seller given staff.manage still can't hand out
    # the real Manager role, with keys he lacks (Jack's rule). And the Owner role made to look like a Seller's, its
    # template changed in memory, is still the Owner role, the superuser's alone to give (PPL-7).
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        assign_role(staff_a2, roles[RoleTemplate.SELLER], side=None, by=None)
        grant_permission(staff_a2, Permission.STAFF_MANAGE, side=None, by=None)
        manager = roles[RoleTemplate.MANAGER]
        manager.permissions = [Permission.SALE_WRITE]
        with pytest.raises(PermissionDenied):
            assign_role(staff_a, manager, side=None, by=staff_a2)
        owner = roles[RoleTemplate.OWNER]
        owner.template, owner.permissions = RoleTemplate.SELLER, [Permission.SALE_WRITE]
        with pytest.raises(ValidationError) as refused:
            assign_role(staff_a, owner, side=None, by=staff_a2)
        assert refused.value.code == "role.superuser_only"
        assert not RoleAssignment.objects.filter(staff=staff_a).exists()


def test_suspended_or_departed_giver_gives_nothing(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # A giver's roles count only while they work. Staff A2, an owner, is suspended, then leaves; staff_a2 is still the
    # copy loaded before, which says "active", so the check must read the giver from the database (X2).
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        assign_role(staff_a2, roles[RoleTemplate.OWNER], side=None, by=None)

        def gives_nothing() -> None:
            with pytest.raises(PermissionDenied):
                assign_role(staff_a, roles[RoleTemplate.WORKER], side=side_a, by=staff_a2)
            with pytest.raises(PermissionDenied):
                grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=staff_a2)

        suspend(staff_a2, by=None, reason="Missed three days of work")
        gives_nothing()
        mark_left(staff_a2, left_on=staff_a2.started_on, by=None, reason="Moved to another town")
        gives_nothing()
        assert not RoleAssignment.objects.filter(staff=staff_a).exists()
        assert not PermissionGrant.objects.filter(staff=staff_a).exists()


# PPL-7: the Owner role is the superuser's alone; a give sent twice, by its id, is one row; the demo's people keep
# theirs.


def test_only_the_superuser_gives_the_owner_role(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Whoever holds the Owner role can be suspended or changed only by the superuser: a manager who held every key and
    # gave himself the Owner role could no longer be stopped by the owner. So even an owner, who holds every key it
    # gives, hears "ask the superuser" (Jack, PPL-7: A). The superuser (`by` None) gives it, as to a shop's first owner.
    give_role(staff_a2, RoleTemplate.OWNER, None)
    with shop_context(shop_a):
        owner = Role.objects.get(template=RoleTemplate.OWNER)
        with pytest.raises(ValidationError) as refused:
            assign_role(staff_a, owner, side=None, by=staff_a2)
        assert refused.value.code == "role.superuser_only"
        assert not RoleAssignment.objects.filter(staff=staff_a).exists()
        assign_role(staff_a, owner, side=None, by=None)


@pytest.fixture
def roles_a(shop_a: Shop) -> dict[str, Role]:
    with shop_context(shop_a):
        return copy_role_templates(shop_a)


def test_a_give_sent_twice_is_one_row(
    shop_a: Shop,
    side_a: Side,
    staff_a: StaffMember,
    staff_a2: StaffMember,
    roles_a: dict[str, Role],
    give_role: GiveRole,
) -> None:
    # The page sends Baba's give of the Seller role, and the answer is lost on a bad network: it sends the same give,
    # with the same id, again (ADR-0007). The second finds the row the first made, and answers with it: one row, and no
    # role.already_given. The same for a key.
    give_role(staff_a2, RoleTemplate.OWNER, None)
    role_id, key_id = uuid.uuid7(), uuid.uuid7()
    with shop_context(shop_a):
        for _ in range(2):
            given = assign_role(staff_a, roles_a[RoleTemplate.SELLER], side=side_a, by=staff_a2, given_id=role_id)
            granted = grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=staff_a2, granted_id=key_id)
            assert (given.pk, granted.pk) == (role_id, key_id)
        assert list(RoleAssignment.objects.filter(staff=staff_a).values_list("pk", flat=True)) == [role_id]
        assert list(PermissionGrant.objects.filter(staff=staff_a).values_list("pk", flat=True)) == [key_id]


def test_a_give_sent_again_after_it_ended_answers_as_now(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, roles_a: dict[str, Role]
) -> None:
    # The first send's answer was lost, and Baba took the role away before the page sent it again: the repeat finds
    # the row as it is now, ended, and gives nothing new. A new give is a new id.
    role_id = uuid.uuid7()
    with shop_context(shop_a):
        given = assign_role(staff_a, roles_a[RoleTemplate.SELLER], side=side_a, by=None, given_id=role_id)
        end_role(given, reason="Amehamia Vyakula", by=None)
        again = assign_role(staff_a, roles_a[RoleTemplate.SELLER], side=side_a, by=None, given_id=role_id)
        assert again.ended_at is not None
        assert RoleAssignment.objects.filter(staff=staff_a).count() == 1


def test_an_id_another_worker_holds_is_taken(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, staff_a2: StaffMember, roles_a: dict[str, Role]
) -> None:
    # The id names one give, to one person: sent for someone else, it is taken, and nothing is given.
    role_id = uuid.uuid7()
    with shop_context(shop_a):
        assign_role(staff_a, roles_a[RoleTemplate.SELLER], side=side_a, by=None, given_id=role_id)
        with pytest.raises(ValidationError) as refused:
            assign_role(staff_a2, roles_a[RoleTemplate.SELLER], side=side_a, by=None, given_id=role_id)
        assert [error.code for error in refused.value.error_dict["id"]] == ["id.taken"]
        assert not RoleAssignment.objects.filter(staff=staff_a2).exists()


@pytest.mark.django_db(transaction=True)
def test_two_copies_of_one_give_at_once_make_one_row(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, roles_a: dict[str, Role]
) -> None:
    # Two copies of one give reach the server in the same second. The first locks Asha's job; the second waits for it,
    # then finds the first's row by its id, and answers with it, never role.already_given.
    role_id = uuid.uuid7()
    seller = roles_a[RoleTemplate.SELLER]

    def second() -> object:
        with shop_context(shop_a):
            return assign_role(staff_a, seller, side=side_a, by=None, given_id=role_id)

    with shop_context(shop_a), transaction.atomic():
        assign_role(staff_a, seller, side=side_a, by=None, given_id=role_id)
        thread, ended = in_another_transaction(second)
        wait_until_someone_waits_for_me()
    thread.join(timeout=5)
    [answer] = ended
    assert isinstance(answer, RoleAssignment) and answer.pk == role_id
    with shop_context(shop_a):
        assert RoleAssignment.objects.filter(staff=staff_a).count() == 1


def test_demo_people_keep_their_roles_when_given(
    shop_a: Shop,
    side_a: Side,
    staff_a: StaffMember,
    staff_a2: StaffMember,
    roles_a: dict[str, Role],
    give_role: GiveRole,
    settings: Settings,
) -> None:
    # On the demo every visitor is Meneja (OPS-3): one who gave Asha a role would change her for every other visitor
    # until the next morning's seed. A worker the visitor added may be given one.
    give_role(staff_a2, RoleTemplate.OWNER, None)
    settings.DEMO_SEED = True
    with shop_context(shop_a):
        for give in (
            lambda: assign_role(staff_a, roles_a[RoleTemplate.SELLER], side=side_a, by=staff_a2),
            lambda: grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=staff_a2),
        ):
            with pytest.raises(ValidationError) as refused:
                give()
            assert refused.value.code == "demo.people_fixed"
        juma = add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", by=staff_a2)
        assign_role(juma, roles_a[RoleTemplate.SELLER], side=side_a, by=staff_a2)
        grant_permission(juma, Permission.STOCK_COUNT, side=side_a, by=staff_a2)
