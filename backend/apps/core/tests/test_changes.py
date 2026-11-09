"""apps/core/tests/test_changes.py — tests for recording a shop's changes (recording_changes and record_change,
apps/core/changes.py; SYNC-1).

A service saves inside `with recording_changes(shop):` and names each record it changed with record_change(row).
The block numbers them only at its end, still inside the transaction, so the numbers follow the order transactions
commit (03 §6.4). These tests pin what one connection can show: the numbers come at the end, in the order recorded;
a rollback leaves no line and no gap; a record changed twice is one line; record_change refuses to run outside a
block or for another shop's record; a block inside another of the same shop waits for the outer end, and drops its
own changes if it fails; and a block that changed nothing takes no number. What only two connections at once can
show, that the order holds when two saves meet, is in test_change_order.py.

The rows come from backend/conftest.py: a side, a staff member's job and a paired device, each a table with a link
type code (apps/core/links.py). They are typed by their base, ShopScoped: `core` may not name a higher app's table,
not even for types (ADR-0035).
"""

import pytest
from django.db import transaction
from django.db.models import Model
from django.db.transaction import TransactionManagementError

from apps.core.changes import record_change, recording_changes
from apps.core.models import Change, ChangeOp, SequenceName, ShopScoped, ShopSequence
from apps.core.tenancy import ShopMismatch, shop_context

pytestmark = pytest.mark.django_db

UPSERT = ChangeOp.UPSERT
ARCHIVE = ChangeOp.ARCHIVE


def _log() -> list[tuple[int, str, object, str]]:
    # The open shop's change log, as a device would read it: number, table, record, what to do.
    return list(Change.objects.order_by("seq").values_list("seq", "entity", "record_id", "op"))


def test_changes_numbered_in_order_at_the_end(shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped) -> None:
    # Lesson 1: the numbers come at the very end of the save, not when each record changes. Inside the block there is
    # no line yet; at its end, one line per record, in the order they were recorded, and the next save goes on from
    # there.
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(side_a)
            record_change(staff_a)
            assert _log() == []
        assert _log() == [(1, "side", side_a.pk, UPSERT), (2, "staff", staff_a.pk, UPSERT)]
        with recording_changes(shop_a):
            record_change(staff_a, ARCHIVE)
        assert _log()[-1] == (3, "staff", staff_a.pk, ARCHIVE)


def test_rollback_leaves_no_changes(shop_a: Model, side_a: ShopScoped) -> None:
    # A save that fails leaves no line, and no hole in the numbers, whether it fails before its numbers are taken or
    # after: the counter's move rolls back with the rest (apps/core/sequences.py). A hole would look, to a device, like
    # a change it can never get.
    with shop_context(shop_a):
        with pytest.raises(RuntimeError), recording_changes(shop_a):
            record_change(side_a)
            raise RuntimeError("the save failed before its numbers were taken")
        with pytest.raises(RuntimeError), transaction.atomic():
            with recording_changes(shop_a):
                record_change(side_a)
            assert _log() == [(1, "side", side_a.pk, UPSERT)]  # numbered, but not yet committed
            raise RuntimeError("the save failed after its numbers were taken")
        assert _log() == []
        with recording_changes(shop_a):
            record_change(side_a)
        assert _log() == [(1, "side", side_a.pk, UPSERT)]  # 1 again: no gap


def test_same_record_twice_is_one_change_with_the_last_op(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped
) -> None:
    # A device reads each record as it is now, so one line per record is enough, with what was done last: Asha's job
    # changed, then ended in the same save, is one "archive" line.
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(staff_a)
            record_change(side_a)
            record_change(staff_a, ARCHIVE)
        assert _log() == [(1, "staff", staff_a.pk, ARCHIVE), (2, "side", side_a.pk, UPSERT)]


def test_record_change_needs_a_block(shop_a: Model, side_a: ShopScoped) -> None:
    # Outside a block nothing would ever number the change, and devices would never learn of it. A bug in the calling
    # code, so it fails loudly, as next_number does outside a transaction.
    with shop_context(shop_a):
        with pytest.raises(TransactionManagementError, match="recording_changes"):
            record_change(side_a)
        with recording_changes(shop_a):
            pass
        with pytest.raises(TransactionManagementError, match="recording_changes"):
            record_change(side_a)  # the block has ended
        assert _log() == []


def test_record_change_refuses_another_shops_row(
    shop_a: Model, shop_b: Model, side_a: ShopScoped, side_b: ShopScoped
) -> None:
    # T1: shop B's side must never land in shop A's log, where A's devices would pull it. And a block for shop B is
    # refused while A is open, as next_number refuses B's counter there.
    with shop_context(shop_a):
        with pytest.raises(ShopMismatch), recording_changes(shop_a):
            record_change(side_b)
        with pytest.raises(ShopMismatch), recording_changes(shop_b):
            pass
        assert _log() == []
    with shop_context(shop_b):
        assert _log() == []


def test_nested_block_numbers_once_at_the_outer_end(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped, device_a: ShopScoped
) -> None:
    # A service that calls another service: both open a block, and the inner one joins the outer. Its end takes no
    # number, not even the counter's lock (the counter has no row yet): all the numbers come at the outer end, so the
    # shop's other saves wait only for the last moment (lesson 2).
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(side_a)
            with recording_changes(shop_a):
                record_change(staff_a)
            assert _log() == []
            assert not ShopSequence.objects.filter(name=SequenceName.CHANGE).exists()
            record_change(device_a)
        assert [line[1] for line in _log()] == ["side", "staff", "device"]


def test_nested_block_rolled_back_drops_its_changes(shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped) -> None:
    # The inner service fails and the outer one carries on without it: what the inner one recorded is rolled back
    # with its writes, the outer record it changed included, so the log names only what was really saved.
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(side_a)
            with pytest.raises(RuntimeError), recording_changes(shop_a):
                record_change(staff_a)
                record_change(side_a, ARCHIVE)
                raise RuntimeError("the inner service failed")
        assert _log() == [(1, "side", side_a.pk, UPSERT)]


def test_block_with_no_change_takes_no_number(shop_a: Model) -> None:
    # A save that changed nothing devices see takes no number and no lock: the counter isn't even made, so it never
    # makes the shop's other saves wait.
    with shop_context(shop_a):
        with recording_changes(shop_a):
            pass
        assert not ShopSequence.objects.filter(name=SequenceName.CHANGE).exists()
        assert _log() == []


def test_record_change_refused_inside_a_part_that_can_fail_alone(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped
) -> None:
    # An import of 50 products is one save, and product 7 fails inside a part of its own (an `atomic()`, or an
    # `editing()` block) and is skipped while the rest carry on. Had its change stayed on the list, the log would name a
    # product that was never saved, and a line can never be taken back. So a change is named only at its block's own
    # level, where a rollback takes the name away too: inside such a part it is refused, and named after the part.
    with shop_context(shop_a):
        with recording_changes(shop_a):
            # The part that can fail on its own, with the refusal caught inside it, so the part itself succeeds.
            with transaction.atomic(), pytest.raises(TransactionManagementError, match="own level"):
                record_change(staff_a)
            record_change(side_a)  # named after the part: allowed
        assert _log() == [(1, "side", side_a.pk, UPSERT)]


def test_block_inside_a_part_that_can_fail_alone_numbers_on_its_own(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped, device_a: ShopScoped
) -> None:
    # A service's block inside such a part doesn't join the outer block: its changes would outlive a rollback of the
    # part around it. It numbers at its own end, inside the part, so a rollback of the part takes its lines and its
    # numbers with it. (The counter then stays locked from that end to the commit: correct, only longer.)
    with shop_context(shop_a):
        with recording_changes(shop_a):  # the import
            record_change(side_a)
            with pytest.raises(RuntimeError), transaction.atomic():  # product 7's part
                with recording_changes(shop_a):
                    record_change(staff_a)
                assert [line[1] for line in _log()] == ["staff"]  # numbered at its own end, not yet committed
                raise RuntimeError("product 7 failed")
            with transaction.atomic(), recording_changes(shop_a):  # product 8's part, and its service's block
                record_change(device_a)
        assert _log() == [(1, "device", device_a.pk, UPSERT), (2, "side", side_a.pk, UPSERT)]
