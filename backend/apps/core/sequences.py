"""apps/core/sequences.py — a shop's counters: next_number(shop, name) gives the next number of one of them, and
next_numbers(shop, name, how_many) the next few in one go (ShopSequence, apps/core/models.py; 03 §5.1, §6.4).

A counter belongs to one shop and has a name from a fixed list (SequenceName): MPC's "device" counter gives
each new device its code, 1, 2, 3... (AUTH-1, D7). Each number is given inside the caller's transaction, with
the counter's row locked until that transaction ends:

    Juma's pairing (transaction 1)          Asha's pairing (transaction 2), at the same moment
    lock MPC's "device" row, 4 → 5
                                            waits for the lock...
    save device 5, commit (lock let go)
                                            ...takes the lock, reads 5 → 6

So two devices never get the same code. And if transaction 1 failed and rolled back, its 5 would go back with
it, and Asha would get 5: a number nobody kept is given again, so a counter has no gaps. From SYNC-1, the
change log needs both promises: numbers in the order transactions commit, and no gap left by a rollback.

Why not a PostgreSQL sequence (CREATE SEQUENCE)? It is faster, but it keeps neither promise: it never waits
for a transaction to end, so numbers can commit out of order, and it never goes back, so a rollback leaves a
gap. It is also one sequence for every shop, not one counter per shop.
"""

import uuid

from django.db import connection, models
from django.db.transaction import TransactionManagementError

from apps.core.models import SequenceName, ShopSequence
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop


class UnknownSequence(Exception):
    # A bug, not a user's mistake: the code asked for a counter that isn't on the list (SequenceName), a typo such as
    # "devcie". Like UnknownPermission, it becomes a server error and a log line, with no error code (ADR-0032).
    pass


def next_number(shop: models.Model | uuid.UUID, name: str) -> int:
    """The next number of `shop`'s counter `name`: 1 the first time, then one more each time. Call it inside the
    transaction that saves the number: the counter stays locked until that transaction ends. `shop` is a Shop row,
    typed as any model because `core` may not name `Shop` (ADR-0035), or a shop's id."""
    return next_numbers(shop, name, 1)[0]


def next_numbers(shop: models.Model | uuid.UUID, name: str, how_many: int) -> range:
    """The next `how_many` numbers of `shop`'s counter `name`, one after another: with 4 given so far, asking for 3
    gives range(5, 8), so 5, 6 and 7. Same promises as next_number: call it inside the transaction that saves the
    numbers, and the counter stays locked until that transaction ends."""
    # A save that changes many records takes all their change numbers here in one go (SYNC-1, apps/core/changes.py):
    # one lock and one write, however many, so the shop's other saves wait for one write, not one per record.
    if how_many < 1:
        # A bug in the calling code: zero numbers would lock the counter for nothing. Refused before it is touched.
        raise ValueError(f"A counter gives at least one number, not {how_many}.")
    if name not in SequenceName.values:
        raise UnknownSequence(f"{name!r} is not a counter's name (SequenceName, apps/core/models.py).")
    # Outside a transaction (Django's default, autocommit), each query would end its own transaction, so the lock
    # below would be let go at once: two pairings could read the same value, and the change log's numbers could
    # commit out of order. As audit() does (apps/control/services.py), refuse rather than give a number unguarded.
    if not connection.in_atomic_block:
        raise TransactionManagementError("next_number() runs inside the transaction that keeps the number.")
    shop_id = shop if isinstance(shop, uuid.UUID) else shop.pk
    # T1: a shop's numbers are given while that shop is open. The guard filters reads, so a counter of shop B
    # asked for while A is open would look missing, and a second "device" row would be made for B from inside A's
    # visit. A bug in the calling code, so a server error (apps/core/tenancy.py).
    open_shop = current_shop()  # raises NoShopSelected when no shop is open
    if open_shop is not ALL_SHOPS and open_shop != shop_id:
        raise ShopMismatch("The counter's shop is not the one open.")
    counters = ShopSequence.objects.select_for_update()
    try:
        # SELECT ... FOR UPDATE: read the row and lock it. Another transaction that asks for the same counter waits
        # here until this one commits or rolls back, then reads the value this one left.
        counter = counters.get(shop_id=shop_id, name=name)
    except ShopSequence.DoesNotExist:
        # The first number of this counter in this shop: make its row, at 0. Made here, on first use, not when the
        # shop is made, so a counter a later card adds works at once in the shops that already exist, with no data
        # migration. ignore_conflicts is PostgreSQL's ON CONFLICT DO NOTHING: if another transaction is making the
        # same row at this moment, this insert waits for it to end, then does nothing (one_per_name, the unique
        # rule, keeps one row), and the read below finds and locks the row it made.
        ShopSequence.objects.bulk_create([ShopSequence(shop_id=shop_id, name=name)], ignore_conflicts=True)
        counter = counters.get(shop_id=shop_id, name=name)
    first = counter.value + 1
    # Safe to add in Python, not in SQL: the row is locked, so nobody else moves it between the read and this write.
    counter.value += how_many
    # Only `value` is written: the row's other columns never change.
    counter.save(update_fields=["value"])
    return range(first, counter.value + 1)
