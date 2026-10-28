"""apps/core/editing.py — how an office record is changed safely when two people may edit it at once
(02 §1, 03 §5.3).

Every Editable row (apps/core/models.py) carries a `version`: 1 when made, and 1 more at each edit. A
screen reads the row with its version, and sends that version back with its edit. If the row's version
has moved on since, someone else saved a change in between, and this edit was made on an old copy: it is
refused with VersionConflict, which the API answers as 409 version_conflict (apps/core/api/errors.py).
The app then reloads the row and lets the person try again. Without this, the later save would silently
undo the earlier one.

    owner opens Dawa (version 1) ─────────┐
    manager opens Dawa (version 1) ───────┤
    owner saves "Dawa za Mifugo"   → version 2
    manager saves "Dawa za Kuku"   → refused: Dawa is at version 2, the manager's copy was version 1

A service changes a row inside editing(): `with editing(side, version=3, by=staff) as side: side.name = …`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from django.db import transaction
from django.utils import timezone

from apps.core.models import Editable
from apps.core.tenancy import ALL_SHOPS, Actor, ShopMismatch, current_shop


class VersionConflict(Exception):
    # Someone else saved the row after this person read it. Not a bug and not a wrong input: the app reloads
    # the row and lets the person try again. The API answers 409 version_conflict.
    def __init__(self) -> None:
        super().__init__("Someone else changed this record since it was read. Load it again.")


@contextmanager
def editing[M: Editable](row: M, *, version: int, by: Actor | None) -> Iterator[M]:
    """Change `row` safely. Inside the `with` block the service changes the row it is handed: a fresh copy,
    read again and locked. If the row is no longer at `version`, the version the person read, the block
    never runs: VersionConflict. After the block, the row is checked (full_clean), its version goes up by
    1, who and when are recorded, and it is saved. All in one transaction: a refusal anywhere leaves the
    row as it was."""
    # T1: the edit stays inside one shop. The guard watches reads, not writes (CORE-2), so these checks are
    # editing()'s own. Both catch a bug in the calling code, so they raise ShopMismatch, a server error.
    open_shop = current_shop()  # NoShopSelected when no shop is open
    if open_shop is not ALL_SHOPS and open_shop != row.shop_id:
        raise ShopMismatch("This row belongs to another shop than the one open.")
    if by is not None and by.shop_id != row.shop_id:
        raise ShopMismatch("The one acting belongs to another shop.")
    with transaction.atomic():
        # Read again and locked until the transaction ends (SELECT ... FOR UPDATE). Two edits of the same
        # row take turns here: the second waits until the first is saved, then sees its new version, and is
        # refused. Compared before the lock, both could pass, and the second would undo the first.
        # cast: mypy reads the manager of type(row) as Editable's, though the row is a side, a product...
        fresh = cast(M, type(row)._default_manager.select_for_update().get(pk=row.pk))
        if fresh.version != version:
            raise VersionConflict()
        yield fresh
        # The block changed `fresh`. The same checks as any form (full_clean), then the version that tells
        # the next editor this copy has moved on.
        fresh.full_clean()
        fresh.version += 1
        fresh.updated_at = timezone.now()
        fresh.updated_by_id = None if by is None else by.staff_id
        fresh.save()
