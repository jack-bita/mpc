"""apps/shops/services.py — every write to the shops tables, one function per action (ADR-0015).

Three actions so far. create_shop makes a new shop with all it needs before it can work: its sides
(ADR-0001). add_side adds one side to a shop, with what a side always comes with: a default stock
location (ADR-0002) and a cash drawer. create_shop uses it for each of its sides, so a side is made the
same way whichever action makes it. rename_side gives a side a new name, unless someone else changed the
side since it was read (apps/core/editing.py). Each action runs in one transaction and refuses a broken
rule with a ValidationError that carries a code (ADR-0032), which the API's error handler
(apps/core/api/errors.py) turns into its error shape.

`shops` is layer 1 and may not import `people`, not even as a type (ADR-0035). Who acts is an Actor
(apps/core/tenancy.py): anything with a `shop_id` and a `staff_id`, as a staff member has. create_shop needs
none: a new shop has no staff yet, so every row it makes has `created_by` empty, like any row the system
makes (02 §1). A new shop's roles live in `people`, so a `people` service, set_up_shop, calls create_shop and
then copies the role templates in, in one transaction (PPL-3, 03 §5.8). A shop is live unless it is made as
something else: the demo seed (DATA-1, apps/demo) makes its shop as a demo one.

A shop's devices keep a copy of its sides and its payment accounts (apps/sync/registry.py), and learn what changed
from the shop's change log (03 §6.4). So each action saves inside `recording_changes(shop)` (apps/core/changes.py), in
place of a plain transaction, and names what it changed with record_change: a new side and its cash drawer, a renamed
side (SYNC-15). The lines are numbered at the block's end, once, however many services joined it.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.changes import record_change, recording_changes
from apps.core.editing import editing
from apps.core.tenancy import ALL_SHOPS, Actor, ShopMismatch, current_shop, shop_context
from apps.shops.models import (
    PaymentAccount,
    PaymentAccountKind,
    PaymentAccountSide,
    SaleFlow,
    Shop,
    ShopKind,
    Side,
    StockLocation,
)


@dataclass(frozen=True)
class NewSide:
    # One side as create_shop is asked for it: NewSide("D", "Dawa"). Frozen: a value handed in, which
    # nothing changes on the way.
    code: str
    name: str
    sale_flow: SaleFlow = SaleFlow.ONE_SCREEN


def create_shop(*, name: str, code: str, sides: Sequence[NewSide], kind: ShopKind = ShopKind.LIVE) -> Shop:
    """Make a shop with its sides, and for each side a default stock location and a cash drawer, all or
    nothing. For set_up_shop (apps/people/services.py), which adds the shop's roles: on its own, it makes a
    shop with no roles, where nobody may act. `kind`: live, unless the caller says otherwise. The demo seed
    (DATA-1) makes a demo shop, which its own refusal then knows as its own."""
    # A shop does everything on a side (ADR-0001): with none it could neither sell nor count. Refused
    # before anything is written.
    if not sides:
        raise ValidationError("A shop needs at least one side.", code="shop.no_sides")
    # The kind is set here, once: nothing changes it later (Shop.kind). A practice shop can't be made here
    # yet: it must name the live shop it copies (ADR-0014), which this takes no argument for, so full_clean
    # refuses it (shop.practice_needs_shop). The row's id is given as it is made (uuid7), before it is saved.
    shop = Shop(name=name, code=code, kind=kind)
    # The new shop is opened first, because the rows' full_clean reads through the guarded `objects`
    # (CORE-2). No caller could have opened it: it didn't exist yet. shop_context hands back whatever shop
    # was open before. Then one block, which is the transaction: if any row below is refused, the rows
    # already written are taken back too, so there is never a shop with half its sides set up. Each
    # add_side joins it, so every side's lines are numbered once, at the very end (SYNC-15).
    with shop_context(shop), recording_changes(shop):
        # Two shops made with the same code at the very same moment can both pass full_clean; the unique
        # rule on `code` then refuses the second. The shop's own row has no line: no device keeps it.
        _saved(shop)
        for new_side in sides:
            add_side(shop=shop, code=new_side.code, name=new_side.name, sale_flow=new_side.sale_flow, by=None)
    return shop


def add_side(
    *,
    shop: Shop,
    code: str,
    name: str,
    sale_flow: SaleFlow = SaleFlow.ONE_SCREEN,
    side_id: uuid.UUID | None = None,
    by: Actor | None,
) -> Side:
    """Add a side to a shop, with its default stock location and its cash drawer, all or nothing.
    `side_id`: the id the client made for the new side (ADR-0007), if it made one. `by`: who adds it; None
    for the system or the superuser."""
    _check_shop(shop, by)
    created_by_id = None if by is None else by.staff_id
    # One block, so a side never exists without its location and its drawer, nor without its lines. Inside
    # create_shop's block, it joins that one: a part that is taken back with the rest, numbered at its end.
    with recording_changes(shop):
        side = Side(shop=shop, code=code, name=name, sale_flow=sale_flow, created_by_id=created_by_id)
        if side_id is not None:
            # The client's id, not a new one: a retry of the same request then finds the side it made.
            side.id = side_id
        _saved(side)
        # T1 holds by construction: every row gets this shop, and links only to rows made here for it. The
        # location and the drawer take the side's name ("Dawa"); the screens add the translated kind, so the
        # server makes up no words (ADR-0032).
        _saved(StockLocation(shop=shop, side=side, name=side.name, is_default=True, created_by_id=created_by_id))
        drawer = _saved(
            PaymentAccount(shop=shop, kind=PaymentAccountKind.CASH_DRAWER, name=side.name, created_by_id=created_by_id)
        )
        _saved(PaymentAccountSide(shop=shop, account=drawer, side=side, created_by_id=created_by_id))
        # What a device keeps a copy of: the side, and its drawer, which carries the sides it serves, so its
        # link travels on it. The stock location stays on the server. Named last, after every row is saved.
        record_change(side)
        record_change(drawer)
    return side


def rename_side(side: Side, *, version: int, name: str, by: Actor | None) -> Side:
    """Give a side a new name, unless someone else changed the side since `version` was read (02 §1).
    `by`: who renames it; None for the system or the superuser. Only the name: the letter starts every
    number printed on the side's receipts (D7), so it never changes."""
    # The block opens the transaction; editing() checks who acts belongs to the shop (T1), locks the side,
    # refuses a stale version, then checks the new name (full_clean trims it, and refuses a name of only
    # spaces) and saves it with the next version. The block refuses a shop that isn't the one open (T1).
    with recording_changes(side.shop_id):
        with editing(side, version=version, by=by) as fresh:
            fresh.name = name
        # After editing() ends, at the block's own level, never inside it: that part could roll back alone,
        # and leave a line for a name never saved (apps/core/changes.py). A refused edit never gets here.
        record_change(fresh)
    return fresh


def _check_shop(shop: Shop, by: Actor | None) -> None:
    # T1: an action works inside one shop. The guard watches reads, not writes (CORE-2), so these checks are
    # the service's own. Both catch a bug in the calling code, not a person's mistake, so they raise
    # ShopMismatch, a server error, before anything is written.
    # 1. The shop written to is the one this visit opened. Otherwise full_clean's checks would read the
    #    open shop's rows while the rows are written into another shop. A system job, under
    #    system_context(), has every shop open; no shop open at all raises NoShopSelected.
    open_shop = current_shop()
    if open_shop is not ALL_SHOPS and open_shop != shop.pk:
        raise ShopMismatch("This shop is not the one open.")
    # 2. Who acts belongs to that shop too: a staff member of shop B can't add shop A's side.
    if by is not None and by.shop_id != shop.pk:
        raise ShopMismatch("The one acting belongs to another shop.")


def _saved[M: models.Model](row: M) -> M:
    # Every field, clean() and the rules in Meta, before the row is written: " mfano " is stored as
    # MFANO, and a clash, such as a second side D, comes back as a code instead of a database error.
    row.full_clean()
    row.save()
    return row
