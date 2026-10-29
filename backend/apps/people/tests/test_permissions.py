"""apps/people/tests/test_permissions.py — who may do what, on which side (02 §5, rule X1).

A permission is one action, by its code (`sale.bargain`). A role is a named bundle of them; each shop holds its
own copy of six templates (Owner, Manager, Seller, Order writer, Cashier, Worker). A person gets a role on one
side or on all sides, and maybe one extra permission of their own (a grant). What they may do on a side is
everything those give them there:

    person   holds                               Dawa (D)    Vyakula (F)
    Baba     Owner, all sides                    every one   every one
    Asha     Cashier on F                        none        the Cashier's
    Juma     Worker on F, + stock.count on F     none        the Worker's + stock.count

A person who is suspended, or who has left, may do nothing at all, whatever they hold.

Every test works inside shop_context(shop), as a visit will: the services and the reads go through the guarded
`objects` (CORE-2). `by=None`: the system or the superuser acts.
"""

import pytest
from django.core.exceptions import PermissionDenied

from apps.core.permissions import ROLE_TEMPLATES, Permission, RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Role, StaffMember
from apps.people.permissions import UnknownPermission, effective_permissions, require
from apps.people.services import assign_role, copy_role_templates, grant_permission, mark_left, suspend, unsuspend
from apps.shops.models import Shop, Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db


@pytest.fixture
def vyakula(shop_a: Shop) -> Side:
    # Shop A's second side, beside side_a (Dawa, D), made the way the app makes one (SHOP-2).
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


@pytest.fixture
def roles_a(shop_a: Shop) -> dict[str, Role]:
    # Shop A's own six roles, copied from the templates, by their template's code: roles_a["worker"]. shop_a
    # (backend/conftest.py) is a bare Shop row with no roles, so the copy is made here.
    with shop_context(shop_a):
        return copy_role_templates(shop_a)


def test_worker_cannot_bargain(shop_a: Shop, side_a: Side, staff_a: StaffMember, roles_a: dict[str, Role]) -> None:
    # A loader hands goods over against paid slips, and never lowers a price (spec §6).
    with shop_context(shop_a):
        assign_role(staff_a, roles_a[RoleTemplate.WORKER], side=side_a, by=None)
        may = effective_permissions(staff_a, side_a)
    assert Permission.SALE_BARGAIN not in may
    # Not nothing either: a check that gave nobody anything would pass the line above.
    assert may == ROLE_TEMPLATES[RoleTemplate.WORKER]


def test_all_sides_role_covers_both_sides(
    shop_a: Shop, side_a: Side, vyakula: Side, staff_a: StaffMember, roles_a: dict[str, Role]
) -> None:
    # A manager runs the shop when the owner is away (spec §6). Given on all sides (side=None), the role works on
    # each one, and on a side the shop adds later too: "all sides" is not a list of the sides of that day.
    manager = roles_a[RoleTemplate.MANAGER]
    with shop_context(shop_a):
        assign_role(staff_a, manager, side=None, by=None)
        mashine = add_side(shop=shop_a, code="M", name="Mashine", by=None)
        for side in (side_a, vyakula, mashine):
            assert effective_permissions(staff_a, side) == set(manager.permissions)


def test_grant_limited_to_its_side(shop_a: Shop, side_a: Side, vyakula: Side, staff_a: StaffMember) -> None:
    # One extra key for one person: Juma may count the stock on Vyakula. Only there: not on Dawa, and not for an
    # action on the whole shop, which needs it on all sides.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.STOCK_COUNT, side=vyakula, by=None)
        assert effective_permissions(staff_a, vyakula) == {Permission.STOCK_COUNT}
        assert effective_permissions(staff_a, side_a) == set()
        assert effective_permissions(staff_a, None) == set()


def test_suspended_member_has_no_permissions(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, staff_a2: StaffMember, roles_a: dict[str, Role]
) -> None:
    # Suspended, or gone: no permission at all, from roles or from grants. Nobody has to take their roles away
    # first: the status alone is enough (02 §5).
    with shop_context(shop_a):
        for staff in (staff_a, staff_a2):
            assign_role(staff, roles_a[RoleTemplate.OWNER], side=None, by=None)
            grant_permission(staff, Permission.STOCK_COUNT, side=side_a, by=None)
            assert Permission.SALE_BARGAIN in effective_permissions(staff, side_a)  # before: everything
        suspend(staff_a, by=None, reason="Missed three days of work")
        mark_left(staff_a2, left_on=staff_a2.started_on, by=None, reason="Moved to another town")
        # staff_a and staff_a2 are copies loaded before, which still say "active". A visit may hold such a copy,
        # so the check must read the status from the database, not from the copy.
        for staff in (staff_a, staff_a2):
            assert effective_permissions(staff, side_a) == set()
            assert effective_permissions(staff, None) == set()


def test_require_refuses_with_permission_denied(
    shop_a: Shop, side_a: Side, vyakula: Side, staff_a: StaffMember, roles_a: dict[str, Role]
) -> None:
    # Asha is Cashier on Vyakula: she may take the money there, not at Dawa. The refusal is Django's
    # PermissionDenied, which the API answers as 403 permission_denied (CORE-6). A code that isn't on the list is a
    # bug in the calling code, which would refuse everyone quietly: it fails loudly instead.
    with shop_context(shop_a):
        assign_role(staff_a, roles_a[RoleTemplate.CASHIER], side=vyakula, by=None)
        require(staff_a, Permission.SALE_TAKE_PAYMENT, vyakula)
        with pytest.raises(PermissionDenied):
            require(staff_a, Permission.SALE_TAKE_PAYMENT, side_a)
        with pytest.raises(UnknownPermission):
            require(staff_a, "sale.take_paymnt", vyakula)


def test_whole_shop_needs_all_sides(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, staff_a2: StaffMember, roles_a: dict[str, Role]
) -> None:
    # An action on a row of the whole shop, such as adding a product, needs the permission on every side: a Manager
    # on Dawa alone may not, a Manager on all sides may.
    with shop_context(shop_a):
        assign_role(staff_a, roles_a[RoleTemplate.MANAGER], side=side_a, by=None)
        assign_role(staff_a2, roles_a[RoleTemplate.MANAGER], side=None, by=None)
        with pytest.raises(PermissionDenied):
            require(staff_a, Permission.PRODUCT_MANAGE, None)
        require(staff_a2, Permission.PRODUCT_MANAGE, None)


def test_member_brought_back_holds_their_roles_again(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, roles_a: dict[str, Role]
) -> None:
    # A suspension takes nothing away for good: brought back, the person holds what they held before, and nobody
    # has to give it again.
    with shop_context(shop_a):
        assign_role(staff_a, roles_a[RoleTemplate.WORKER], side=side_a, by=None)
        suspended = suspend(staff_a, by=None, reason="Missed three days of work")
        assert effective_permissions(suspended, side_a) == set()
        back = unsuspend(suspended, by=None, reason="Came back with a doctor's note")
        assert effective_permissions(back, side_a) == ROLE_TEMPLATES[RoleTemplate.WORKER]


def test_side_of_another_shop_refused(
    shop_a: Shop, side_b: Side, staff_a: StaffMember, roles_a: dict[str, Role]
) -> None:
    # T1: asked about shop B's side, the check would find none of A's rows for it, and answer with A's every-side
    # permissions alone, as if B's side were A's. A bug in the calling code, so a server error (ShopMismatch).
    with shop_context(shop_a):
        assign_role(staff_a, roles_a[RoleTemplate.OWNER], side=None, by=None)
        with pytest.raises(ShopMismatch):
            effective_permissions(staff_a, side_b)


def test_person_of_a_shop_not_open_refused(shop_a: Shop, staff_b: StaffMember) -> None:
    # T1: with shop A open, the guard reads only A's rows, so shop B's person would quietly hold nothing, and the bug in
    # the calling code would hide behind a plain "no". It fails loudly instead, as another shop's side does.
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        effective_permissions(staff_b, None)
