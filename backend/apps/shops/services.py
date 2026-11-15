"""apps/shops/services.py — every write to the shops tables, one function per action (ADR-0015).

Five actions so far. create_shop makes a new shop with all it needs before it can work: its sides
(ADR-0001). add_side adds one side to a shop, with what a side always comes with: a default stock
location (ADR-0002) and a cash drawer. create_shop uses it for each of its sides, so a side is made the
same way whichever action makes it. rename_side gives a side a new name, unless someone else changed the
side since it was read (apps/core/editing.py); switch_side turns a side on or off the same way (ADR-0033), except on
the demo. set_setting gives a rule a new value from a day on, as a
new row, never an edit (ADR-0013). Each action runs in one transaction and refuses a broken
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
side (SYNC-15), a side switched on or off and a rule's new value (SHOP-3). The lines are numbered at the block's end,
once, however many services joined it.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.changes import record_change, recording_changes
from apps.core.editing import editing
from apps.core.settings_registry import REGISTRY, Scope
from apps.core.tenancy import ALL_SHOPS, Actor, ShopMismatch, current_shop, shop_context
from apps.shops.models import (
    PaymentAccount,
    PaymentAccountKind,
    PaymentAccountSide,
    SaleFlow,
    Setting,
    Shop,
    ShopKind,
    Side,
    StockLocation,
)
from apps.shops.selectors import shop_today


@dataclass(frozen=True)
class NewSide:
    # One side as create_shop is asked for it: NewSide("D", "Dawa"). Frozen: a value handed in, which
    # nothing changes on the way.
    code: str
    name: str
    sale_flow: SaleFlow = SaleFlow.ONE_SCREEN


def create_shop(
    *,
    name: str,
    code: str,
    sides: Sequence[NewSide],
    kind: ShopKind = ShopKind.LIVE,
    shop_id: uuid.UUID | None = None,
) -> Shop:
    """Make a shop with its sides, and for each side a default stock location and a cash drawer, all or
    nothing. For set_up_shop (apps/people/services.py), which adds the shop's roles: on its own, it makes a
    shop with no roles, where nobody may act. `kind`: live, unless the caller says otherwise. The demo seed
    (DATA-1) makes a demo shop, which its own refusal then knows as its own. `shop_id`: the new shop's id, for a
    caller that has opened the shop's block already (set_up_shop), as add_side takes `side_id`; a new one otherwise."""
    # A shop does everything on a side (ADR-0001): with none it could neither sell nor count. Refused
    # before anything is written.
    if not sides:
        raise ValidationError("A shop needs at least one side.", code="shop.no_sides")
    # The kind is set here, once: nothing changes it later (Shop.kind). A practice shop can't be made here
    # yet: it must name the live shop it copies (ADR-0014), which this takes no argument for, so full_clean
    # refuses it (shop.practice_needs_shop). The row's id is given as it is made (uuid7), before it is saved.
    shop = Shop(name=name, code=code, kind=kind)
    if shop_id is not None:
        shop.id = shop_id
    # The new shop is opened first, because the rows' full_clean reads through the guarded `objects` (CORE-2). A caller
    # can't have opened it, unless by the id it chose for it (set_up_shop): it didn't exist yet. shop_context hands back
    # whatever shop was open before. Then one block, which is the transaction: if any row below is refused, the rows
    # already written are taken back too, so there is never a shop with half its sides set up. Each add_side joins it,
    # so every side's lines are numbered once, at the very end (SYNC-15). Inside a caller's block for this same shop
    # (set_up_shop), this one joins that one in turn.
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


def switch_side(side: Side, *, version: int, is_live: bool, by: Actor | None) -> Side:
    """Turn a side on (`is_live` True) or off, unless someone else changed the side since `version` was read (02 §1).
    `by`: who switches it; None for the system or the superuser. A side starts off (SHOP-2), so it reaches the counters
    only once the owner agrees to start using it (ADR-0033). Refused on the demo (demo.sides_fixed)."""
    # On the demo every visitor shares the manager's login (OPS-3): one who switched Dawa off would stop every later
    # visitor's one-tap demo, whose laptops are on Dawa (DEMO_DEVICE_SIDE), until the next morning's seed. So the switch
    # is fixed there, as passwords and PINs are (check_logins_may_change, apps/people/services.py), read from the same
    # sign (DEMO_SEED, config/settings/base.py). Before anything is opened or written. The rules stay open on the demo:
    # trying them is the point, and the seed puts them back.
    if settings.DEMO_SEED:
        raise ValidationError("On the demo, the sides stay switched as they are.", code="demo.sides_fixed")
    # The same steps as rename_side: the block, then editing(), which checks who acts belongs to the shop (T1), locks
    # the side and refuses a stale version. The line after editing() ends: the laptops keep `is_live` on their copy of
    # the side (SYNC-2), and learn of the switch at their next pull.
    with recording_changes(side.shop_id):
        with editing(side, version=version, by=by) as fresh:
            fresh.is_live = is_live
        record_change(fresh)
    return fresh


def set_setting(
    shop: Shop,
    *,
    key: str,
    value: str,
    effective_from: date,
    side: Side | None = None,
    note: str = "",
    setting_id: uuid.UUID | None = None,
    by: Actor | None,
) -> Setting:
    """Give the rule `key` a new value from the day `effective_from` on: one new Setting row, for the whole shop, or for
    `side` alone on a side's rule. `value` is text, as a screen sends it ("2000"); it is stored in its kind's one form
    ("2000.00"). `setting_id`: the id the client made for the row (ADR-0007), if it made one. `by`: who sets it; None
    for the system or the superuser. Refuses, all together, with their codes: a day before the shop's today, a side's
    rule with no side, and whatever Setting.clean() refuses (an unknown key, a wrong value, a side on a shop's rule)."""
    _check_shop(shop, by)
    # T1: the side is of this shop. A bug in the calling code, like the shop checks: the route finds a side through the
    # visit's own shop, so a person can't send another shop's side here.
    if side is not None and side.shop_id != shop.pk:
        raise ShopMismatch("The side is of another shop.")
    row = Setting(
        shop=shop,
        side=side,
        key=key,
        value=value,
        effective_from=effective_from,
        note=note,
        created_by_id=None if by is None else by.staff_id,
    )
    if setting_id is not None:
        # The client's id, not a new one: a retry of the same request then finds the row it made.
        row.id = setting_id
    # The service's own two rules, then the row's, so a person who made several mistakes sees them all at once, each
    # beside its box. Each one a code the screens translate (ADR-0040).
    errors: dict[str, list[ValidationError]] = {}
    # Never before the shop's today (Jack, 15 Nov 2026): a row for a past day changes what that day answers, and the
    # clock-ins, fines and draft pay run already worked out from it. Today is still open: a mistake made this morning
    # is fixed with one more row for today, which wins (T2). The shop's today, not the server's, which runs in UTC.
    if effective_from < shop_today(shop):
        errors["effective_from"] = [ValidationError("A new value can't start before today.", code="setting.date_past")]
    # A side's rule is set one side at a time, never for the whole shop (Jack, 15 Nov 2026). get_setting lets a side's
    # row beat even a newer shop row (CORE-4), so a shop value set next year would be hidden by a side's old one, and
    # nobody would see why. An unknown key is left to clean(), which reports it once.
    setting_key = REGISTRY.get(key)
    if side is None and setting_key is not None and setting_key.scope is Scope.SIDE:
        errors["side"] = [ValidationError("This setting is set for one side at a time.", code="setting.side_required")]
    try:
        # Setting.clean() holds the row's own checks, which objects.create skips: only full_clean asks them.
        row.full_clean()
    except ValidationError as refused:
        for field, field_errors in refused.error_dict.items():
            errors.setdefault(field, []).extend(field_errors)
    if errors:
        raise ValidationError(errors)
    # One block: the row and its line, or neither. The line tells the laptops at their next pull, and they switch to the
    # value on its day, even offline (03 §5.8). Named after the save, at the block's own level (apps/core/changes.py).
    with recording_changes(shop):
        row.save()
        record_change(row)
    return row


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
