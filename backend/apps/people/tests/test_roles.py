"""apps/people/tests/test_roles.py — the rules the three role tables keep themselves (02 §5): a role or a grant holds
only known codes, a shop has one role per template, and a person holds a role, or an extra permission, once per side.

Each rule sits in the database (03 §5.6) and in full_clean, which reads it from Meta: a person gets a code
(ADR-0032), and code that skips full_clean still can't store a broken row. The rows are made by hand here, to test
the tables alone; the services that make them come next (test_permissions.py).
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import PermissionGrant, Role, RoleAssignment, StaffMember
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db


def test_role_permissions_must_be_known(shop_a: Shop) -> None:
    # "sale.bargin" is a typo nobody would notice: a role holding it gives nobody anything. full_clean refuses it
    # with a code, and the database refuses it even when full_clean is skipped.
    role = Role(shop=shop_a, name="Msaidizi", permissions=[Permission.SALE_WRITE, "sale.bargin"])
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        role.full_clean()
    assert [error.code for error in refused.value.error_dict["__all__"]] == ["permission.unknown"]
    with pytest.raises(IntegrityError, match="people_role_permissions_known"), transaction.atomic():
        role.save()


def test_one_role_per_template_per_shop(shop_a: Shop, shop_b: Shop) -> None:
    # Two Managers in one shop would split its managers across two bundles, and a change to one would miss the
    # others. Each shop has its own, so shop B's Manager is no clash.
    with shop_context(shop_a):
        Role(shop=shop_a, template=RoleTemplate.MANAGER, permissions=[Permission.SALE_WRITE]).save()
        second = Role(shop=shop_a, template=RoleTemplate.MANAGER, permissions=[Permission.SALE_WRITE])
        with pytest.raises(ValidationError) as refused:
            second.full_clean()
    assert [error.code for error in refused.value.error_dict["__all__"]] == ["role.template_taken"]
    with shop_context(shop_b):
        Role(shop=shop_b, template=RoleTemplate.MANAGER, permissions=[Permission.SALE_WRITE]).full_clean()


def test_role_given_once_per_side(shop_a: Shop, side_a: Side, staff_a: StaffMember) -> None:
    # A second row would change nothing, and taking the role away later would have to find both. "All sides" (no
    # side) counts too: PostgreSQL never sees two empty values as the same, unless the rule says so.
    with shop_context(shop_a):
        role = Role(shop=shop_a, template=RoleTemplate.WORKER, permissions=[Permission.SALE_HAND_OVER])
        role.save()
        for side in (side_a, None):
            RoleAssignment(shop=shop_a, staff=staff_a, role=role, side=side).save()
            again = RoleAssignment(shop=shop_a, staff=staff_a, role=role, side=side)
            with pytest.raises(ValidationError) as refused:
                again.full_clean()
            assert [error.code for error in refused.value.error_dict["__all__"]] == ["role.already_given"]
            with pytest.raises(IntegrityError, match="people_roleassignment_once"), transaction.atomic():
                again.save()


def test_extra_permission_known_and_given_once(shop_a: Shop, side_a: Side, staff_a: StaffMember) -> None:
    # The same two rules on a grant: a code from the list only, and once per side, "all sides" included.
    with shop_context(shop_a):
        typo = PermissionGrant(shop=shop_a, staff=staff_a, permission="stock.cont", side=side_a)
        with pytest.raises(ValidationError) as refused:
            typo.full_clean()
        assert [error.code for error in refused.value.error_dict["__all__"]] == ["permission.unknown"]
        for side in (side_a, None):
            PermissionGrant(shop=shop_a, staff=staff_a, permission=Permission.STOCK_COUNT, side=side).save()
            again = PermissionGrant(shop=shop_a, staff=staff_a, permission=Permission.STOCK_COUNT, side=side)
            with pytest.raises(ValidationError) as refused:
                again.full_clean()
            assert [error.code for error in refused.value.error_dict["__all__"]] == ["permission.already_given"]
