"""apps/core/tests/test_change_order.py — two saves at the same moment, on two database connections: the change log's
numbers follow the order the saves commit, and shops never wait for each other (SYNC-1, 03 §6.4).

The three lessons of the card, each proven the only way it can be, with two transactions really open at once:

    1. numbers come at the end      Juma's save starts first, Asha's commits first: Asha gets the lower number
    2. one numbers book per shop    Juma holds MPC's book until he commits: Asha waits, then gets the next number
    3. each shop has its own book   while MPC holds its book, the other shop saves without waiting

The second save runs in a thread, on its own connection, as a second laptop would (backend/tests/concurrency.py).
Each transaction must really commit, or the other could never see it, so these tests run with
`django_db(transaction=True)`, and the tables are emptied after each one. The single-connection promises are in
test_changes.py. The rows come from backend/conftest.py, typed by their base, ShopScoped: `core` may not name a higher
app's table (ADR-0041). They are made by the services, which write lines of their own (SYNC-15), so each test reads
only the lines after the one it started at, numbered from 1 again (backend/tests/change_log.py).
"""

import pytest
from django.db import transaction
from django.db.models import Model

from apps.core.changes import record_change, recording_changes
from apps.core.models import ShopScoped
from apps.core.tenancy import shop_context
from tests.change_log import last_line, lines_after
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db(transaction=True)


def _save(shop: Model, row: ShopScoped) -> None:
    # The other laptop's save: one changed record, in a block of its own, committed at its end.
    with shop_context(shop), recording_changes(shop):
        record_change(row)


def _log(shop: Model, start: int) -> list[tuple[int, str]]:
    # A shop's change log as a device reads it, after the line the test started at: each line's number, from 1 again,
    # and table.
    return [(number, entity) for number, entity, _record, _op in lines_after(shop, start)]


def test_change_numbers_follow_commit_order(shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped) -> None:
    # Lesson 1. Juma's save starts first and ends last; Asha's starts later and commits while his is still open. Had
    # the numbers been given at the start, Juma would hold 1 and Asha 2, and a device that read Asha's 2 before Juma
    # committed would never read his 1. Given at the end, Asha's save, committed first, gets 1.
    start = last_line(shop_a)
    with shop_context(shop_a), recording_changes(shop_a):  # Juma's save starts
        record_change(side_a)
        asha, ended = in_another_transaction(lambda: _save(shop_a, staff_a))
        asha.join(timeout=5)
        # Asha's save committed without waiting: Juma's holds no lock until its own end.
        assert ended == [None]
        assert _log(shop_a, start) == [(1, "staff")]
    # Juma's save ends and commits, second.
    assert _log(shop_a, start) == [(1, "staff"), (2, "side")]


def test_late_numbers_wait_for_the_shops_last_commit(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped, device_a: ShopScoped
) -> None:
    # Lesson 2. Juma has taken his number but not yet committed: Asha's save, ending now, must wait for him. Without
    # the lock she would take the next number and could commit before him, and a device could read hers and skip his.
    start = last_line(shop_a)
    _save(shop_a, device_a)  # yesterday's change: the counter's row exists, as on any day but a shop's first
    with shop_context(shop_a):
        with transaction.atomic():  # Juma's transaction: his block ends inside it, his commit comes after
            with recording_changes(shop_a):
                record_change(side_a)
            # Juma holds MPC's numbers book now: number 2 taken, not committed.
            asha, ended = in_another_transaction(lambda: _save(shop_a, staff_a))
            wait_until_someone_waits_for_me()
            assert ended == []  # Asha waits: no number of hers can commit before Juma's
        # Juma commits, and lets go of the book.
        asha.join(timeout=5)
    assert ended == [None]
    assert _log(shop_a, start) == [(1, "device"), (2, "side"), (3, "staff")]


def test_shops_do_not_block_each_other(
    shop_a: Model,
    shop_b: Model,
    side_a: ShopScoped,
    side_b: ShopScoped,
    device_a: ShopScoped,
    staff_b: ShopScoped,
) -> None:
    # Lesson 3. MPC's save holds MPC's numbers book; a save in the other shop, at that very moment, takes its own
    # shop's numbers and commits without waiting. One shop's busy morning never slows another's.
    # Yesterday's changes first, so both counters' rows exist, as on any day but a shop's first. Without them MPC's
    # row would be new and not yet committed, which the other shop can't even see, so a lock on every shop's counter
    # would still pass this test (found by breaking it on purpose).
    start_a, start_b = last_line(shop_a), last_line(shop_b)
    _save(shop_a, device_a)
    _save(shop_b, staff_b)
    with shop_context(shop_a), transaction.atomic():
        with recording_changes(shop_a):
            record_change(side_a)
        # MPC holds its book until this transaction commits.
        other, ended = in_another_transaction(lambda: _save(shop_b, side_b))
        other.join(timeout=5)
        assert ended == [None]  # the other shop saved while MPC still held its book
    assert _log(shop_b, start_b) == [(1, "staff"), (2, "side")]
    assert _log(shop_a, start_a) == [(1, "device"), (2, "side")]
