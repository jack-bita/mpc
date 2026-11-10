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
not even for types (ADR-0041). They are made by the services, which write lines of their own (SYNC-15), so each test
reads only the lines after the one it started at, numbered from 1 again (last_line, lines_after:
backend/tests/change_log.py).
"""

import uuid
from unittest import mock

import pytest
from django.db import transaction
from django.db.models import Model
from django.db.transaction import TransactionManagementError

from apps.core.changes import record_change, recording_changes
from apps.core.links import UnknownLinkType
from apps.core.models import ChangeOp, SequenceName, ShopScoped, ShopSequence
from apps.core.sequences import next_numbers
from apps.core.tenancy import NoShopSelected, ShopMismatch, shop_context, system_context
from tests.change_log import last_line, lines_after
from tests.probe.models import Note

pytestmark = pytest.mark.django_db

UPSERT = ChangeOp.UPSERT
ARCHIVE = ChangeOp.ARCHIVE
# The refusal of a change named with no block open, word for word: the refusal of one named too deep inside a block
# also names recording_changes, so a looser match would take one for the other.
OUTSIDE_A_BLOCK = r"runs inside recording_changes\(shop\)"


def _log(shop: Model, start: int) -> list[tuple[int, str, uuid.UUID, str]]:
    # The shop's change log after the line the test started at, as a device would read it: number, table, record, what
    # to do. Numbered from 1 again, so each test reads as on a shop's first day.
    return lines_after(shop, start)


def test_changes_numbered_in_order_at_the_end(shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped) -> None:
    # Lesson 1: the numbers come at the very end of the save, not when each record changes. Inside the block there is
    # no line yet; at its end, one line per record, in the order they were recorded, and the next save goes on from
    # there.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(side_a)
            record_change(staff_a)
            assert _log(shop_a, start) == []
        assert _log(shop_a, start) == [(1, "side", side_a.pk, UPSERT), (2, "staff", staff_a.pk, UPSERT)]
        with recording_changes(shop_a):
            record_change(staff_a, ARCHIVE)
        assert _log(shop_a, start)[-1] == (3, "staff", staff_a.pk, ARCHIVE)


def test_rollback_leaves_no_changes(shop_a: Model, side_a: ShopScoped) -> None:
    # A save that fails leaves no line, and no hole in the numbers, whether it fails before its numbers are taken or
    # after: the counter's move rolls back with the rest (apps/core/sequences.py). A hole would look, to a device, like
    # a change it can never get.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with pytest.raises(RuntimeError), recording_changes(shop_a):
            record_change(side_a)
            raise RuntimeError("the save failed before its numbers were taken")
        with pytest.raises(RuntimeError), transaction.atomic():
            with recording_changes(shop_a):
                record_change(side_a)
            assert _log(shop_a, start) == [(1, "side", side_a.pk, UPSERT)]  # numbered, but not yet committed
            raise RuntimeError("the save failed after its numbers were taken")
        assert _log(shop_a, start) == []
        with recording_changes(shop_a):
            record_change(side_a)
        assert _log(shop_a, start) == [(1, "side", side_a.pk, UPSERT)]  # 1 again: no gap


def test_rollback_of_a_later_save_gives_its_numbers_back(shop_a: Model, side_a: ShopScoped) -> None:
    # The same promise on any day but a shop's first: the counter's row already exists, so a failed save's numbers go
    # back by undoing its UPDATE, not by its row vanishing (from the review). The next save gets 2, not 3.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(side_a)
        with pytest.raises(RuntimeError), transaction.atomic():
            with recording_changes(shop_a):
                record_change(side_a)
            assert [line[0] for line in _log(shop_a, start)] == [1, 2]  # numbered, but not yet committed
            raise RuntimeError("the save failed after its numbers were taken")
        with recording_changes(shop_a):
            record_change(side_a)
        assert [line[0] for line in _log(shop_a, start)] == [1, 2]  # 2 again: no gap


def test_same_record_twice_is_one_change_with_the_last_op(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped
) -> None:
    # A device reads each record as it is now, so one line per record is enough, with what was done last: Asha's job
    # changed, then ended in the same save, is one "archive" line.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(staff_a)
            record_change(side_a)
            record_change(staff_a, ARCHIVE)
        assert _log(shop_a, start) == [(1, "staff", staff_a.pk, ARCHIVE), (2, "side", side_a.pk, UPSERT)]


def test_record_change_needs_a_block(shop_a: Model, side_a: ShopScoped) -> None:
    # Outside a block nothing would ever number the change, and devices would never learn of it. A bug in the calling
    # code, so it fails loudly, as next_number does outside a transaction.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with pytest.raises(TransactionManagementError, match=OUTSIDE_A_BLOCK):
            record_change(side_a)
        with recording_changes(shop_a):
            pass
        with pytest.raises(TransactionManagementError, match=OUTSIDE_A_BLOCK):
            record_change(side_a)  # the block has ended
        assert _log(shop_a, start) == []


def test_record_change_refuses_another_shops_row(
    shop_a: Model, shop_b: Model, side_a: ShopScoped, side_b: ShopScoped
) -> None:
    # T1: shop B's side must never land in shop A's log, where A's devices would pull it. And a block for shop B is
    # refused while A is open, as next_number refuses B's counter there.
    start, start_b = last_line(shop_a), last_line(shop_b)
    with shop_context(shop_a):
        with pytest.raises(ShopMismatch), recording_changes(shop_a):
            record_change(side_b)
        with pytest.raises(ShopMismatch), recording_changes(shop_b):
            pass
    # Neither shop's log got a line. Each read opens its own shop (lines_after).
    assert _log(shop_a, start) == []
    assert _log(shop_b, start_b) == []


def test_nested_block_numbers_once_at_the_outer_end(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped, device_a: ShopScoped
) -> None:
    # A service that calls another service: both open a block, and the inner one joins the outer. Its end takes no
    # number, so not even the counter's lock (the counter is never asked): all the numbers come at the outer end, so
    # the shop's other saves wait only for the last moment (lesson 2).
    start = last_line(shop_a)
    with shop_context(shop_a), mock.patch("apps.core.changes.next_numbers", wraps=next_numbers) as numbering:
        with recording_changes(shop_a):
            record_change(side_a)
            with recording_changes(shop_a):
                record_change(staff_a)
            assert _log(shop_a, start) == []
            numbering.assert_not_called()
            record_change(device_a)
        numbering.assert_called_once_with(shop_a.pk, SequenceName.CHANGE, 3)
        assert [line[1] for line in _log(shop_a, start)] == ["side", "staff", "device"]


def test_nested_block_rolled_back_drops_its_changes(shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped) -> None:
    # The inner service fails and the outer one carries on without it: what the inner one recorded is rolled back
    # with its writes, the outer record it changed included, so the log names only what was really saved.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with recording_changes(shop_a):
            record_change(side_a)
            with pytest.raises(RuntimeError), recording_changes(shop_a):
                record_change(staff_a)
                record_change(side_a, ARCHIVE)
                raise RuntimeError("the inner service failed")
        assert _log(shop_a, start) == [(1, "side", side_a.pk, UPSERT)]


def test_block_with_no_change_takes_no_number(shop_a: Model) -> None:
    # A save that changed nothing devices see takes no number and no lock: the counter isn't even made, so it never
    # makes the shop's other saves wait.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with recording_changes(shop_a):
            pass
        assert not ShopSequence.objects.filter(name=SequenceName.CHANGE).exists()
        assert _log(shop_a, start) == []


def test_record_change_refused_inside_a_part_that_can_fail_alone(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped
) -> None:
    # An import of 50 products is one save, and product 7 fails inside a part of its own (an `atomic()`, or an
    # `editing()` block) and is skipped while the rest carry on. Had its change stayed on the list, the log would name a
    # product that was never saved, and a line can never be taken back. So a change is named only at its block's own
    # level, where a rollback takes the name away too: inside such a part it is refused, and named after the part.
    start = last_line(shop_a)
    with shop_context(shop_a):
        with recording_changes(shop_a):
            # The part that can fail on its own, with the refusal caught inside it, so the part itself succeeds.
            with transaction.atomic(), pytest.raises(TransactionManagementError, match="own level"):
                record_change(staff_a)
            record_change(side_a)  # named after the part: allowed
        assert _log(shop_a, start) == [(1, "side", side_a.pk, UPSERT)]


def test_block_inside_a_part_that_can_fail_alone_numbers_on_its_own(
    shop_a: Model, side_a: ShopScoped, staff_a: ShopScoped, device_a: ShopScoped
) -> None:
    # A service's block inside such a part doesn't join the outer block: its changes would outlive a rollback of the
    # part around it. It numbers at its own end, inside the part, so a rollback of the part takes its lines and its
    # numbers with it. (The counter then stays locked from that end to the commit: correct, only longer.)
    start = last_line(shop_a)
    with shop_context(shop_a):
        with recording_changes(shop_a):  # the import
            record_change(side_a)
            with pytest.raises(RuntimeError), transaction.atomic():  # product 7's part
                with recording_changes(shop_a):
                    record_change(staff_a)
                # Numbered at its own end, not yet committed.
                assert [line[1] for line in _log(shop_a, start)] == ["staff"]
                raise RuntimeError("product 7 failed")
            with transaction.atomic(), recording_changes(shop_a):  # product 8's part, and its service's block
                record_change(device_a)
        assert _log(shop_a, start) == [(1, "device", device_a.pk, UPSERT), (2, "side", side_a.pk, UPSERT)]


def _log_of(shop: Model, start: int) -> list[tuple[int, str]]:
    # One shop's change log after the line the test started at, read while every shop is open (system_context): each
    # line's number, from 1 again, and table.
    return [(number, entity) for number, entity, _record, _op in lines_after(shop, start)]


def test_blocks_of_two_shops_one_inside_the_other(
    shop_a: Model, shop_b: Model, side_a: ShopScoped, side_b: ShopScoped, staff_a: ShopScoped
) -> None:
    # A system job with every shop open (system_context, 03 §5.4) saves in shop A, and opens shop B's block inside A's.
    # B's block doesn't join A's: it numbers at its own end, in B's own log, from 1. Once it ends, A's block is the
    # job's block again, and A's next change lands in A's log.
    start_a, start_b = last_line(shop_a), last_line(shop_b)
    with system_context():
        with recording_changes(shop_a):
            record_change(side_a)
            with recording_changes(shop_b):
                record_change(side_b)
            assert _log_of(shop_b, start_b) == [(1, "side")]
            assert _log_of(shop_a, start_a) == []
            record_change(staff_a)
        assert _log_of(shop_a, start_a) == [(1, "side"), (2, "staff")]


def test_a_shops_block_inside_another_shops_block_numbers_on_its_own(
    shop_a: Model, shop_b: Model, side_a: ShopScoped, side_b: ShopScoped, staff_a: ShopScoped
) -> None:
    # A, then B inside it, then A again inside B. The innermost A block doesn't join the outer one, as B's block sits
    # between them and could fail alone: it numbers at its own end, so its line comes first in A's log. Its numbers stay
    # locked until the commit, as the outer A block's will: two saves that nest the same two shops in opposite orders
    # could each wait for the other, so a save over several shops takes them in a fixed order (SYNC-2's note).
    start_a, start_b = last_line(shop_a), last_line(shop_b)
    with system_context():
        with recording_changes(shop_a):
            record_change(side_a)
            with recording_changes(shop_b):
                record_change(side_b)
                with recording_changes(shop_a):
                    record_change(staff_a)
        assert _log_of(shop_a, start_a) == [(1, "staff"), (2, "side")]
        assert _log_of(shop_b, start_b) == [(1, "side")]


def test_block_needs_an_open_shop(shop_a: Model) -> None:
    # With no shop open, nothing could check that the records belong to the block's shop (T1), nor number them: refused
    # as the block starts, before the service writes anything, as every read with no shop is (CORE-2).
    start = last_line(shop_a)
    with pytest.raises(NoShopSelected), recording_changes(shop_a):
        pass
    with shop_context(shop_a):
        assert _log(shop_a, start) == []


def test_record_change_refuses_a_table_with_no_type_code(shop_a: Model) -> None:
    # A line names its table by its link type code (apps/core/links.py). A table with none can't be named, so its
    # change is refused, and the whole save with it, rather than written under a made-up name no device could read.
    # The test-only Note has no code.
    start = last_line(shop_a)
    note = Note(shop_id=shop_a.pk, text="no code")
    note.save()
    with shop_context(shop_a):
        with pytest.raises(UnknownLinkType), recording_changes(shop_a):
            record_change(note)
        assert _log(shop_a, start) == []


def test_record_change_refused_after_a_failed_block(shop_a: Model, side_a: ShopScoped) -> None:
    # A failed block lets go of its list as surely as a finished one: a change named after it would otherwise land in
    # a block that no longer exists, and never be numbered (from the review).
    start = last_line(shop_a)
    with shop_context(shop_a):
        with pytest.raises(RuntimeError), recording_changes(shop_a):
            raise RuntimeError("the save failed")
        with pytest.raises(TransactionManagementError, match=OUTSIDE_A_BLOCK):
            record_change(side_a)
        assert _log(shop_a, start) == []
