"""apps/people/tests/test_giving_roles.py — how a shop gets its roles, and how a person is given one, or one extra
permission (02 §5).

Each shop holds its own copy of the six templates, made once. A role or a permission is given only inside its own
shop (T1), never to someone who has left, and the row keeps who gave it. Only someone with staff.manage there may
give, and only what they hold there themselves (Jack, 29 Oct 2026). Fake data only: the repo is public (03 §10).
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.core.permissions import ROLE_TEMPLATES, Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import PermissionGrant, Role, RoleAssignment, StaffMember
from apps.people.services import assign_role, copy_role_templates, grant_permission, mark_left, suspend
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db


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
    # holds the owner's own approvals, to himself or to anyone; not one of those approvals as an extra key; and,
    # holding staff.manage on Dawa alone, nothing for every side.
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        assign_role(staff_a2, roles[RoleTemplate.MANAGER], side=None, by=None)
        grant_permission(staff_a2, Permission.STAFF_MANAGE, side=side_a, by=None)
        for receiver in (staff_a2, staff_a):
            with pytest.raises(PermissionDenied):
                assign_role(receiver, roles[RoleTemplate.OWNER], side=side_a, by=staff_a2)
        with pytest.raises(PermissionDenied):
            grant_permission(staff_a, Permission.DRAWER_APPROVE, side=side_a, by=staff_a2)
        with pytest.raises(PermissionDenied):
            assign_role(staff_a, roles[RoleTemplate.WORKER], side=None, by=staff_a2)
        # What he holds on Dawa, he may give on Dawa.
        assign_role(staff_a, roles[RoleTemplate.WORKER], side=side_a, by=staff_a2)


def test_giver_check_reads_the_role_as_stored(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # The role handed in may be a copy whose codes were changed in memory and never saved: here the Owner role, made to
    # say "sale.write" only. The check reads the role as stored, so a Manager given staff.manage still can't hand out
    # the real Owner role, with the owner's own approvals (Jack's rule).
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
        assign_role(staff_a2, roles[RoleTemplate.MANAGER], side=None, by=None)
        grant_permission(staff_a2, Permission.STAFF_MANAGE, side=None, by=None)
        owner = roles[RoleTemplate.OWNER]
        owner.permissions = [Permission.SALE_WRITE]
        with pytest.raises(PermissionDenied):
            assign_role(staff_a, owner, side=None, by=staff_a2)
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
