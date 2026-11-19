"""apps/people/tests/test_ending_roles.py — a role or an extra key taken away (02 §5, PPL-7).

Taking one away is an edit of its row, never a delete (rule 7): the row stays, marked ended, with who, when and why.
An ended row counts nowhere (test_permissions.py), and the same role or key can be given again later, as a new row.

These tests check what the database holds to: the rows that end. Who may end one, and the service that does it, come
with end_role and end_permission; until then a test ends a row by writing its three columns itself, as the service
will.
"""

from collections.abc import Callable

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import PermissionGrant, Role, RoleAssignment, StaffMember
from apps.people.services import assign_role, copy_role_templates, grant_permission
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db


@pytest.fixture
def seller(shop_a: Shop) -> Role:
    # Shop A's own Seller role, copied from its template: shop_a is a bare Shop row with no roles.
    with shop_context(shop_a):
        return copy_role_templates(shop_a)[RoleTemplate.SELLER]


def given(staff: StaffMember, seller: Role, side: Side) -> tuple[RoleAssignment, PermissionGrant]:
    # One row of each table, given by the system, on the same side: what each test then ends or deletes.
    with shop_context(staff.shop_id):
        role = assign_role(staff, seller, side=side, by=None)
        key = grant_permission(staff, Permission.STOCK_COUNT, side=side, by=None)
    return role, key


def end(row: RoleAssignment | PermissionGrant) -> None:
    # The row ended by the superuser (no one named), as the service will write it: when, and why.
    with shop_context(row.shop_id):
        type(row).objects.filter(pk=row.pk).update(ended_at=timezone.now(), end_reason="Amehamia Vyakula")


def refused(row: RoleAssignment | PermissionGrant, **change: object) -> None:
    # The change, refused by the database. In a savepoint of its own, so the test's transaction goes on after it.
    with shop_context(row.shop_id), pytest.raises(IntegrityError), transaction.atomic():
        type(row).objects.filter(pk=row.pk).update(**change)


def code_of(give: Callable[[], object]) -> str:
    # The code of the one rule a give broke, as full_clean names it: a once rule names no field.
    with pytest.raises(ValidationError) as broken:
        give()
    [error] = broken.value.error_dict["__all__"]
    return str(error.code)


def test_a_role_or_a_key_is_never_deleted(shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role) -> None:
    # Rule 7: nothing links to these rows, so PROTECT never stops a delete, and the edit history's trigger ignores one.
    # The no-delete trigger refuses it, however it is sent: a bulk delete() here, or SQL typed by hand.
    for row in given(staff_a, seller, side_a):
        with shop_context(shop_a), pytest.raises(IntegrityError), transaction.atomic():
            type(row).objects.filter(pk=row.pk).delete()
        with shop_context(shop_a):
            assert type(row).objects.filter(pk=row.pk).exists()


def test_an_end_is_whole_or_not_at_all(shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role) -> None:
    # An end says when and why, so a row is either open, with all three empty, or ended, with a time and a reason. Who
    # ended it may be empty: the superuser, who is nobody's staff. Half an end would leave a row that counts nowhere
    # with no reason anyone could read, or a reason on a row that still counts.
    now = timezone.now()
    for row in given(staff_a, seller, side_a):
        refused(row, ended_at=now)
        refused(row, ended_at=now, end_reason="   ")
        refused(row, end_reason="Amehamia Vyakula")
        refused(row, ended_by=staff_a)
        # Ended by a person, with all three: allowed, as the service will write it.
        with shop_context(shop_a):
            type(row).objects.filter(pk=row.pk).update(ended_at=now, ended_by=staff_a, end_reason="Amehamia Vyakula")


def test_an_ended_role_is_given_again_as_a_new_row(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role
) -> None:
    # The once rules count only rows not ended: Asha's Seller role on Dawa, taken away, can be given to her again, as a
    # new row, and the old one stays as history. Given twice while it counts is still refused.
    role, key = given(staff_a, seller, side_a)
    end(role)
    end(key)
    with shop_context(shop_a):
        again = assign_role(staff_a, seller, side=side_a, by=None)
        key_again = grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=None)
        assert again.pk != role.pk and key_again.pk != key.pk
        assert RoleAssignment.objects.filter(staff=staff_a).count() == 2
        assert PermissionGrant.objects.filter(staff=staff_a).count() == 2
        assert code_of(lambda: assign_role(staff_a, seller, side=side_a, by=None)) == "role.already_given"
        assert (
            code_of(lambda: grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=None))
            == "permission.already_given"
        )


def test_an_ended_role_on_every_side_is_given_again(shop_a: Shop, staff_a: StaffMember, seller: Role) -> None:
    # "Every side" is an empty side, and the once rules keep counting two empty sides as one (nulls_distinct=False):
    # ended, it is given again; open, a second is refused.
    with shop_context(shop_a):
        first = assign_role(staff_a, seller, side=None, by=None)
    end(first)
    with shop_context(shop_a):
        assign_role(staff_a, seller, side=None, by=None)
        assert code_of(lambda: assign_role(staff_a, seller, side=None, by=None)) == "role.already_given"
