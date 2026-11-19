"""apps/people/permissions.py — what a person may do, and on which side (02 §5, rule X1).

The two questions every later card asks: effective_permissions(staff, side), every code a person holds there,
and require(staff, permission, side), which refuses unless they hold that one. Both read held_permissions(staff),
everything the person holds, side by side, which is also what a person hands the office routes for a whole visit
(StaffMember.held_permissions(), PPL-5).

On a side, a person holds the codes of every role and grant given on that side, plus those given on every side
(no side). Asked about the whole shop (side=None), as for an action on a row that belongs to no side, such as a
product, only those given on every side count: a key for Vyakula alone opens nothing of the whole shop's. That rule
is written once, in core's HeldPermissions (apps/core/permissions.py). A person who is suspended, or who has left,
holds nothing at all, whatever they were given; brought back, they hold it all again. A role or a key taken away
(ended, PPL-7) counts nowhere, in either question below: its row stays only as history.

And one question about what they were given, whatever their status (given_permissions): what they would hold if brought
back, for a check of who holds more than whom (AUTH-6); or, at a moment past, what they held then, for a record made
offline and pushed later (SYNC-5, PPL-7).

Read through the guarded `objects` (CORE-2): the person's shop must be open, and only its rows count.
"""

import uuid
from collections import defaultdict
from datetime import datetime

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
    # The status is read from the database in the same query, not from the copy handed in: a visit may hold a copy
    # loaded before the person was suspended, which still says "active" (X2).
    return _read_permissions(staff, Q(staff=staff, staff__status=StaffStatus.ACTIVE))


def given_permissions(staff: StaffMember, *, at: datetime | None = None) -> HeldPermissions:
    """Every permission code `staff` was given, whatever their status: what they hold once they are brought back. Never
    for what a person may do now, which is held_permissions; this is for comparing two people (HeldPermissions.covers),
    where a suspended owner must not read as someone with no keys.

    `at`: a moment past, for a record made offline (SYNC-5): the keys not yet taken away by then, by the laptop's
    clock, as was_working_at reads a status (apps/people/selectors.py). Read from the rows' own end, not the audit
    trail, as an end writes no audit line (PPL-7). A key given after `at` still counts, unless it had been taken away
    by then (_held_at). A role's codes are read as they are now, for a moment past too: no card edits a role yet
    (parking lot item 26)."""
    return _read_permissions(staff, Q(staff=staff), at=at)


# One role or key a person was given, as read for _held_at: its side (None: every side), the codes it gives (a key's
# one, or a role's as they are now), when it was given, and when it was taken away (None: it still counts).
_Given = tuple[uuid.UUID | None, list[str], datetime, datetime | None]


def _read_permissions(staff: StaffMember, rows: Q, *, at: datetime | None = None) -> HeldPermissions:
    # The one reading behind both questions above: they differ only in which of the person's rows count. Never one that
    # ended (PPL-7): taken away, a role opens nothing, at once. With `at`, what the person held then (_held_at): every
    # row is read, ended ones included, as one taken away after `at` still counted, and one taken away before it tells
    # whether a key given back later may count. Two queries either way.
    open_shop = current_shop()
    if open_shop is not ALL_SHOPS and open_shop != staff.shop_id:
        # T1: the guard reads only the open shop's rows, so a person of another shop would quietly hold nothing, and the
        # bug in the calling code would hide behind a plain "no". A server error instead, as for another shop's side.
        raise ShopMismatch("The person belongs to another shop than the one open.")
    if at is None:
        rows &= Q(ended_at__isnull=True)
    grants = PermissionGrant.objects.filter(rows).values_list("side_id", "permission", "created_at", "ended_at")
    roles = RoleAssignment.objects.filter(rows).values_list("side_id", "role__permissions", "created_at", "ended_at")
    given: list[_Given] = [(side_id, [code], given_at, ended_at) for side_id, code, given_at, ended_at in grants]
    given += [(side_id, list(codes), given_at, ended_at) for side_id, codes, given_at, ended_at in roles]
    if at is not None:
        given = _held_at(given, at)
    every_side: set[str] = set()
    on_side: defaultdict[uuid.UUID, set[str]] = defaultdict(set)
    for side_id, codes, _given_at, _ended_at in given:
        # No side means every side (02 §5): a side added later included.
        (every_side if side_id is None else on_side[side_id]).update(codes)
    return HeldPermissions(
        every_side=frozenset(every_side), on_side={side_id: frozenset(codes) for side_id, codes in on_side.items()}
    )


def _held_at(given: list[_Given], at: datetime) -> list[_Given]:
    # What a person held at `at`, a moment past, by the laptop's clock (SYNC-5, PPL-7). A row taken away at or before
    # `at` held nothing then: at the very moment of the end the key is gone, as a suspension counts from its own moment
    # (was_working_at). A row given after `at` counts, as a laptop lets nobody use a key it hasn't heard of, so only a
    # slow laptop clock could put a record before its key (PPL-7's card, default). But not its codes that had been taken
    # away by `at`: the laptop knew those keys and hadn't heard of their end, so a key given back after the record left
    # a gap the record fell in (the PPL-7 review: Baba takes Asha's role at 11:00, she sells at 12:00 on a laptop that
    # hasn't heard, he gives it back at 13:00; a break, as a suspension and a return around her sale would be). By the
    # code, whichever row gave it and on whichever side: a role taken away and given back as an extra key leaves the
    # same gap. A rare slow clock around a key given back may raise a flag a person then reads: a flag refuses nothing.
    taken_away = {
        code for _side, codes, _given_at, ended in given if ended is not None and ended <= at for code in codes
    }
    held: list[_Given] = []
    for side_id, codes, given_at, ended in given:
        if ended is not None and ended <= at:
            continue
        if given_at > at:
            codes = [code for code in codes if code not in taken_away]
        held.append((side_id, codes, given_at, ended))
    return held


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
