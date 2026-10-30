"""apps/core/tests/test_sequences.py — tests for a shop's counters (next_number, apps/core/sequences.py; AUTH-1).

A counter gives 1, 2, 3... per shop and per name, inside the caller's transaction, with its row locked until that
transaction ends. These tests pin each promise: it counts up from 1; each shop counts alone; it refuses to run
outside a transaction, or for a shop that isn't open, or for a name not on the list; a number rolled back is given
again; and a second pairing at the same moment waits for the first, then gets the next number, never the same one,
even when both are the shop's first. `core` may not import `shops` (ADR-0035), so the two shops come from
backend/conftest.py, typed as plain models.
"""

import pytest
from django.db import IntegrityError, transaction
from django.db.models import Model
from django.db.transaction import TransactionManagementError

from apps.core.models import SequenceName, ShopSequence
from apps.core.sequences import UnknownSequence, next_number
from apps.core.tenancy import ShopMismatch, shop_context
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

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


def test_database_keeps_one_counter_per_name(shop_a: Model) -> None:
    # Two "device" counters in one shop would each count from 1, and give the same code twice (D7). next_number never
    # makes a second (ON CONFLICT DO NOTHING); the database refuses code that would.
    with shop_context(shop_a), transaction.atomic():
        next_number(shop_a, DEVICE)
        with pytest.raises(IntegrityError, match="core_shopsequence_one_per_name"), transaction.atomic():
            ShopSequence.objects.create(shop_id=shop_a.pk, name=DEVICE)


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


def _number_in_its_own_transaction(shop: Model) -> int:
    # The second pairing's part: the next number, in a transaction of its own (backend/tests/concurrency.py).
    with shop_context(shop), transaction.atomic():
        return next_number(shop, DEVICE)


@pytest.mark.django_db(transaction=True)
def test_counter_row_locked_until_commit(shop_a: Model) -> None:
    # Two pairings at once in one shop. Without the lock, both would read 1, both write 2, and two devices would
    # print the same receipt numbers (a "lost update"). With it, the second waits until the first commits, then
    # reads 2 and gives 3.
    with shop_context(shop_a), transaction.atomic():
        next_number(shop_a, DEVICE)  # 1, committed: the row exists for both
    with shop_context(shop_a), transaction.atomic():
        assert next_number(shop_a, DEVICE) == 2  # the first pairing holds the row now
        second, ended = in_another_transaction(lambda: _number_in_its_own_transaction(shop_a))
        wait_until_someone_waits_for_me()
        assert ended == []  # still waiting: it has no number yet
    second.join(timeout=5)
    assert ended == [3]


@pytest.mark.django_db(transaction=True)
def test_first_numbers_at_once_make_one_counter(shop_a: Model) -> None:
    # The shop's first two pairings at the same moment, before its counter has a row. The first makes the row and
    # takes 1. The second can't see that row until the first commits, so it tries to make the row too: ON CONFLICT DO
    # NOTHING makes it wait for the first, then do nothing, and its next read finds the row and takes 2. Without it,
    # the second would fail on the unique rule (core_shopsequence_one_per_name), and its pairing with it.
    with shop_context(shop_a), transaction.atomic():
        assert next_number(shop_a, DEVICE) == 1  # the row is made, but not yet committed
        second, ended = in_another_transaction(lambda: _number_in_its_own_transaction(shop_a))
        wait_until_someone_waits_for_me()
    second.join(timeout=5)
    assert ended == [2]
    with shop_context(shop_a):
        assert ShopSequence.objects.count() == 1
