"""apps/core/tests/test_sequences.py — tests for a shop's counters (next_number, apps/core/sequences.py; AUTH-1).

A counter gives 1, 2, 3... per shop and per name, inside the caller's transaction, with its row locked until that
transaction ends. These tests pin each promise: it counts up from 1; each shop counts alone; it refuses to run
outside a transaction, or for a shop that isn't open, or for a name not on the list; a number rolled back is given
again; and a second pairing at the same moment waits for the first, then gets the next number, never the same one.
`core` may not import `shops` (ADR-0035), so the two shops come from backend/conftest.py, typed as plain models.
"""

import threading
import time

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import Model
from django.db.transaction import TransactionManagementError

from apps.core.models import SequenceName, ShopSequence
from apps.core.sequences import UnknownSequence, next_number
from apps.core.tenancy import ShopMismatch, shop_context

pytestmark = pytest.mark.django_db

DEVICE = SequenceName.DEVICE


def test_counter_starts_at_one_and_counts_up(shop_a: Model) -> None:
    with shop_context(shop_a), transaction.atomic():
        assert [next_number(shop_a, DEVICE) for _ in range(3)] == [1, 2, 3]
        # One row, made on first use, holding the last number given.
        assert ShopSequence.objects.get(name=DEVICE).value == 3


def test_each_shop_counts_alone(shop_a: Model, shop_b: Model) -> None:
    # MPC's third device and another shop's first: each shop has its own codes (D7 is per shop).
    with shop_context(shop_a), transaction.atomic():
        next_number(shop_a, DEVICE)
        next_number(shop_a, DEVICE)
    with shop_context(shop_b), transaction.atomic():
        assert next_number(shop_b, DEVICE) == 1
    with shop_context(shop_a), transaction.atomic():
        assert next_number(shop_a, DEVICE) == 3


def test_rolled_back_number_is_given_again(shop_a: Model) -> None:
    # A pairing that fails after taking its number rolls the number back with it. Nothing kept that number, so the
    # next pairing gets it: a counter leaves no gap (SYNC-1 relies on this), and still gives no number twice.
    with shop_context(shop_a):
        with transaction.atomic():
            assert next_number(shop_a, DEVICE) == 1
        with pytest.raises(RuntimeError), transaction.atomic():
            assert next_number(shop_a, DEVICE) == 2
            raise RuntimeError("the pairing failed after taking its number")
        with transaction.atomic():
            assert next_number(shop_a, DEVICE) == 2


def test_unknown_counter_name_refused(shop_a: Model) -> None:
    # A typo would start a second counter at 1 and give device codes already in use (D7). Refused in Python first...
    with shop_context(shop_a), transaction.atomic():
        with pytest.raises(UnknownSequence):
            next_number(shop_a, "devcie")
        assert not ShopSequence.objects.exists()
        # ...and by the database, for code that writes a counter some other way. (A savepoint, so the refused insert
        # leaves the test's transaction usable.)
        with pytest.raises(IntegrityError, match="core_shopsequence_name_known"), transaction.atomic():
            ShopSequence.objects.create(shop_id=shop_a.pk, name="devcie")


def test_counter_of_another_shop_refused(shop_a: Model, shop_b: Model) -> None:
    # T1: shop B's numbers are given only while B is open. Inside A's visit it is a bug in the calling code.
    with shop_context(shop_a), transaction.atomic(), pytest.raises(ShopMismatch):
        next_number(shop_b, DEVICE)
    with shop_context(shop_b):
        assert not ShopSequence.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_counter_needs_a_transaction(shop_a: Model) -> None:
    # Outside a transaction the lock would be let go after each query, so two pairings could read the same value.
    # This test runs without the transaction pytest wraps every other test in (transaction=True), so the call below
    # really is outside one; the tables are emptied afterwards.
    with shop_context(shop_a):
        with pytest.raises(TransactionManagementError, match="transaction"):
            next_number(shop_a, DEVICE)
        assert not ShopSequence.objects.exists()


def _second_pairing(shop: Model, got: list[int | BaseException]) -> None:
    # The second pairing, in a thread of its own. Django gives each thread its own database connection, so this is
    # a second transaction at the same moment, as a second manager's phone would be. A new thread starts with no shop
    # open (a context variable starts empty there), so it opens its own.
    try:
        with shop_context(shop), transaction.atomic():
            got.append(next_number(shop, DEVICE))
    except BaseException as error:  # handed back to the test, which fails with it
        got.append(error)
    finally:
        connection.close()


def _someone_waits_for_me() -> bool:
    # PostgreSQL's own list of open connections (pg_stat_activity), and for each one, the connections it waits for
    # (pg_blocking_pids): is any connection waiting for this one, the test's own (pg_backend_pid)? Asked this way, not
    # by the database's name, which this list may leave empty for a connection still waiting.
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE pg_backend_pid() = ANY(pg_blocking_pids(pid))")
        (waiting,) = cursor.fetchone() or (0,)
    return waiting > 0


@pytest.mark.django_db(transaction=True)
def test_counter_row_locked_until_commit(shop_a: Model) -> None:
    # Two pairings at once in one shop. Without the lock, both would read 1, both write 2, and two devices would
    # print the same receipt numbers (a "lost update"). With it, the second waits until the first commits, then
    # reads 2 and gives 3. transaction=True: each pairing must really commit, as in production, for the other to
    # see it.
    with shop_context(shop_a), transaction.atomic():
        next_number(shop_a, DEVICE)  # 1, committed: the row exists for both
    got: list[int | BaseException] = []
    with shop_context(shop_a), transaction.atomic():
        assert next_number(shop_a, DEVICE) == 2  # the first pairing holds the row now
        second = threading.Thread(target=_second_pairing, args=(shop_a, got))
        second.start()
        # Commit only once the second pairing is really waiting for the lock: committing earlier would let it run
        # after, and the test would pass even without a lock.
        deadline = time.monotonic() + 5
        while not _someone_waits_for_me():
            assert time.monotonic() < deadline, f"the second pairing never waited for the first: {got}"
            time.sleep(0.02)
        assert got == []  # still waiting: it has no number yet
    second.join(timeout=5)
    assert got == [3]
