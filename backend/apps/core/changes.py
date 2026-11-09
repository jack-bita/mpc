"""apps/core/changes.py — recording a shop's changes for its devices: the block every saving service opens,
recording_changes(shop), and record_change(row), which names one record the save changed (SYNC-1, 03 §6.4).

A shop device keeps a copy of the shop's lists and learns what changed by pulling the shop's change log (Change,
apps/core/models.py) after the last number it read. That only works if a number never arrives late:

    numbered at the start (wrong)                 numbered at the end (this file)
    Juma's save starts, takes 42                  Juma's save starts
    Asha's save starts, takes 43                  Asha's save starts
    Asha's save commits (43)                      Asha's save ends: takes 42, commits
      a device reads up to 43                     Juma's save ends: takes 43, commits
    Juma's save commits (42): never read          a device reads 42, then 43: nothing skipped

So a service saves inside the block, and names each record as it changes it:

    with recording_changes(shop):
        side.name = "Dawa"
        side.save()
        record_change(side)

The block collects the names and, as its last step inside the transaction, takes all their numbers at once from the
shop's "change" counter (next_numbers, apps/core/sequences.py). The counter's row stays locked from then until the
commit, so the next save of the same shop waits for that last moment, and takes the numbers after (lesson 2: one
numbers book, one writer at a time). Each shop has a counter of its own, so shops never wait for each other.

This file owns the block and record_change. It names no table of a higher app: a record's table is read from the
record itself, by its link type code (apps/core/links.py).
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from django.db import models, transaction
from django.db.transaction import TransactionManagementError

from apps.core.links import link_type_of
from apps.core.models import Change, ChangeOp, SequenceName, ShopScoped
from apps.core.sequences import next_numbers
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop


@dataclass
class _Block:
    # One open block: the shop it records for, and what was recorded so far. One entry per record, keyed by its table's
    # code and its id, holding what was done to it last: a device reads each record as it is now, so a record changed
    # twice in one save needs one line (the op of the last change). A dict keeps the order the records were first
    # recorded, and the lines are numbered in that order.
    shop_id: uuid.UUID
    changes: dict[tuple[str, uuid.UUID], ChangeOp] = field(default_factory=dict)


# The block open in this visit, if any. A context variable, as the open shop is (apps/core/tenancy.py): each request,
# and each thread, sees its own, so two saves at once never mix their changes.
_open_block: ContextVar[_Block | None] = ContextVar("open_change_block", default=None)


@contextmanager
def recording_changes(shop: models.Model | uuid.UUID) -> Iterator[None]:
    """The block a service saves in, in place of `transaction.atomic()`: one transaction, whose changes record_change
    names, numbered as its last step. `shop` is a Shop row, typed as any model because `core` may not name `Shop`
    (ADR-0035), or a shop's id. The shop must be the one open."""
    shop_id = shop if isinstance(shop, uuid.UUID) else shop.pk
    # T1: a shop's changes are recorded while that shop is open, as its numbers are given (next_number). Checked here,
    # at the start, so the service fails before it writes anything, not at the end.
    open_shop = current_shop()  # raises NoShopSelected when no shop is open
    if open_shop is not ALL_SHOPS and open_shop != shop_id:
        raise ShopMismatch("The shop recording changes is not the one open.")
    outer = _open_block.get()
    if outer is not None and outer.shop_id == shop_id:
        # A service called by another service of the same shop: join the outer block, so all the numbers come once,
        # at its end, the last moment of the whole transaction. Numbered here instead, the counter would stay locked
        # from now until the outer commit, making the shop's other saves wait longer.
        # Its own savepoint, as any nested `atomic()` has: if this part fails and the outer service carries on, its
        # writes roll back, so what it recorded must go too, any outer record it changed included.
        before = dict(outer.changes)
        try:
            with transaction.atomic():
                yield
        except BaseException:
            outer.changes.clear()
            outer.changes.update(before)
            raise
        return
    # The outermost block of this shop. (A block of another shop opened inside it starts its own, and numbers at its
    # own end: correct, as that shop's counter stays locked until the commit, only for a little longer.)
    block = _Block(shop_id)
    token = _open_block.set(block)
    try:
        with transaction.atomic():
            yield
            # The last step inside the transaction. Reached only if the service's work succeeded: an error above skips
            # it, and the whole transaction, its numbers included, rolls back, leaving no line and no gap.
            _number_and_write(block)
    finally:
        _open_block.reset(token)  # the visit's block is the outer one again, or none


def _number_and_write(block: _Block) -> None:
    # A save that changed nothing devices see takes no number, so it never locks the counter, and never makes the
    # shop's other saves wait.
    if not block.changes:
        return
    # All the numbers in one go: one lock, one write, however many records changed. From here until the commit the
    # counter's row stays locked, so no later save of this shop can number before this one commits.
    numbers = next_numbers(block.shop_id, SequenceName.CHANGE, len(block.changes))
    # One INSERT for all the lines. `objects` needs the shop open, which recording_changes checked at the start.
    Change.objects.bulk_create(
        Change(shop_id=block.shop_id, seq=seq, entity=entity, record_id=record_id, op=op)
        for seq, ((entity, record_id), op) in zip(numbers, block.changes.items(), strict=True)
    )


def record_change(row: ShopScoped, op: ChangeOp = ChangeOp.UPSERT) -> None:
    """Name `row` as changed by this save: `upsert` when it is new or changed, `archive` when it leaves the lists.
    Call it inside recording_changes, after the change; its number comes at the block's end."""
    block = _open_block.get()
    if block is None:
        # Outside a block nothing would number this change, and devices would never learn of it: a bug in the calling
        # code, so a server error, as next_number outside a transaction is.
        raise TransactionManagementError("record_change() runs inside recording_changes(shop).")
    # T1: another shop's record would land in this shop's log, where this shop's devices would pull it.
    if row.shop_id != block.shop_id:
        raise ShopMismatch("The changed record's shop is not the one recording changes.")
    # The table's code, such as "side": UnknownLinkType for a table with none, as a link to it would raise.
    block.changes[(link_type_of(row), row.pk)] = op
