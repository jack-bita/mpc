"""apps/people/permissions.py — what a person may do, and on which side (02 §5, rule X1).

The two questions every later card asks: effective_permissions(staff, side), every code a person holds there,
and require(staff, permission, side), which refuses unless they hold that one. Both read held_permissions(staff),
everything the person holds, side by side, which is also what a person hands the office routes for a whole visit
(StaffMember.held_permissions(), PPL-5).

On a side, a person holds the codes of every role and grant given on that side, plus those given on every side
(no side). Asked about the whole shop (side=None), as for an action on a row that belongs to no side, such as a
product, only those given on every side count: a key for Vyakula alone opens nothing of the whole shop's. That rule
is written once, in core's HeldPermissions (apps/core/permissions.py). A person who is suspended, or who has left,
holds nothing at all, whatever they were given; brought back, they hold it all again.

Read through the guarded `objects` (CORE-2): the person's shop must be open, and only its rows count.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from apps.core.permissions import HeldPermissions, Permission
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import PermissionGrant, RoleAssignment, StaffMember, StaffStatus
from apps.shops.models import Side


class UnknownPermission(Exception):
    # A bug, not a person's mistake: the calling code asked about a code that isn't on the list
    # (apps/core/permissions.py), a typo such as "sale.take_paymnt". Nobody holds it, so every person would be
    # refused, quietly. It becomes a server error and a log line instead, with no error code (ADR-0032).
    pass


def held_permissions(staff: StaffMember) -> HeldPermissions:
    """Every permission code `staff` holds, on every side and side by side, in two queries: one for the extra
    permissions, one for the roles, however many sides the shop has. Nothing for a person who is suspended or has
    left."""
    open_shop = current_shop()
    if open_shop is not ALL_SHOPS and open_shop != staff.shop_id:
        # T1: the guard reads only the open shop's rows, so a person of another shop would quietly hold nothing, and the
        # bug in the calling code would hide behind a plain "no". A server error instead, as for another shop's side.
        raise ShopMismatch("The person belongs to another shop than the one open.")
    # The status is read from the database in the same query, not from the copy handed in: a visit may hold a copy
    # loaded before the person was suspended, which still says "active" (X2).
    held = Q(staff=staff, staff__status=StaffStatus.ACTIVE)
    grants = PermissionGrant.objects.filter(held).values_list("side_id", "permission")
    roles = RoleAssignment.objects.filter(held).values_list("side_id", "role__permissions")
    every_side: set[str] = set()
    on_side: defaultdict[uuid.UUID, set[str]] = defaultdict(set)

    def add(side_id: uuid.UUID | None, codes: Iterable[str]) -> None:
        # No side means every side (02 §5): a side added later included.
        (every_side if side_id is None else on_side[side_id]).update(codes)

    for side_id, code in grants:
        add(side_id, [code])
    for side_id, codes in roles:
        add(side_id, codes)
    return HeldPermissions(
        every_side=frozenset(every_side), on_side={side_id: frozenset(codes) for side_id, codes in on_side.items()}
    )


def effective_permissions(staff: StaffMember, side: Side | None) -> frozenset[str]:
    """Every permission code `staff` holds on `side`, or on the whole shop when `side` is None. Empty for a person
    who is suspended or has left."""
    if side is not None and side.shop_id != staff.shop_id:
        # T1: shop B's side matches none of shop A's rows, so the answer would hold A's every-side codes alone, as if
        # B's side were A's. A bug in the calling code, so a server error (apps/core/tenancy.py).
        raise ShopMismatch("The side belongs to another shop than the person.")
    return held_permissions(staff).on(None if side is None else side.pk)


def require(staff: StaffMember, permission: str, side: Side | None) -> None:
    """Refuse with PermissionDenied unless `staff` holds `permission` on `side`, or on the whole shop when `side` is
    None. CORE-6's error handler answers the refusal as 403 permission_denied (apps/core/api/errors.py)."""
    if permission not in Permission.values:
        raise UnknownPermission(f"{permission!r} is not a permission code (apps/core/permissions.py).")
    if permission not in effective_permissions(staff, side):
        # English for the logs; the screens translate the code (ADR-0032).
        raise PermissionDenied(f"This person may not {permission} here.")
