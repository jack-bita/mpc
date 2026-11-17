"""apps/sync/tests/test_device_numbers.py — a laptop's numbers, and the flag a missing one raises (SYNC-5; 02 §17,
03 §6.3).

A laptop numbers each record it saves, 1, 2, 3, in the order it made them, and never skips one. The server keeps the
last number it saw from each laptop, and a jump raises one `device_gap` flag: a record deleted on the laptop, or lost.

    the laptop's last number    the record that comes    the answer        the flag
    41                          42                       saved             none
    41                          44                       saved             42 and 43 missing: expected 42, actual 44
    44                          43 (a late one)          saved             none new: it fills the gap (its closing:
                                                                           test_late_record_resolves_gap_flag)
    44                          1 (a laptop reset)       saved             the numbers went back: expected 45, actual 1;
                                                                           counting carries on from 1

The record is always saved: a broken rule never stops a batch (03 §6.3). These tests send pretend "ticket" documents
(tests/probe/documents.py) through the push service itself. Fake data only: the repo is public (03 §10).
"""

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, cast

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Model
from django.db.transaction import TransactionManagementError

from apps.control.models import Flag, FlagKind, FlagNote, FlagStatus, FlagStep
from apps.control.services import dismiss_flag, explain_flag
from apps.core.links import LINK_TYPES
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import lock_device_numbers
from apps.shops.models import Shop, Side
from apps.sync import push as push_module
from apps.sync.document_types import DOCUMENT_TYPES, Document
from apps.sync.models import PushedDocument
from apps.sync.push import HIGHEST_DEVICE_SEQ, Answer, Sent, push
from apps.sync.selectors import highest_pushed_number, last_device_number
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me
from tests.probe.documents import TICKET, TICKET_CODE, post_ticket
from tests.probe.models import Ticket

pytestmark = pytest.mark.django_db

CLIENT_TIME = dt.datetime(2026, 11, 10, 7, 42, tzinfo=dt.UTC)
RECEIVED_AT = dt.datetime(2026, 11, 10, 11, 5, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def ticket_type(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pretend ticket on the list of document types, and its table's link type code, for as long as each test runs.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET)
    monkeypatch.setitem(LINK_TYPES, TICKET_CODE, "probe.Ticket")


def _sent(device_seq: int, maker: StaffMember, **envelope: Any) -> Sent:
    # One ticket as the laptop sent it, its number `device_seq`; `envelope` overrides its type or id.
    return Sent(
        id=envelope.get("id", uuid.uuid7()),
        type=envelope.get("type", "ticket"),
        schema_version=1,
        device_seq=device_seq,
        client_time=CLIENT_TIME,
        created_by=maker.pk,
        payload={"text": "2 bags of pumba"},
    )


def _push(device: Device, documents: Sequence[Sent]) -> list[Answer]:
    # The push as the route runs it: inside the laptop's shop, which its key opened.
    with shop_context(device.shop_id):
        return push(
            device,
            documents,
            received_at=RECEIVED_AT,
            sent_at=RECEIVED_AT,
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )


def _push_numbers(device: Device, maker: StaffMember, *numbers: int) -> list[Answer]:
    return _push(device, [_sent(number, maker) for number in numbers])


def _gaps(shop: Model) -> list[Flag]:
    # The shop's missing-number flags, oldest first: ids are UUIDv7, which follow the order they were made in.
    with shop_context(shop):
        return list(Flag.objects.filter(kind=FlagKind.DEVICE_GAP).order_by("id"))


def _numbers(flag: Flag) -> tuple[Decimal | None, Decimal | None]:
    # What the flag says: the number the server waited for, and the number that came.
    return flag.expected, flag.actual


def _last(device: Device) -> int | None:
    with shop_context(device.shop_id):
        return Device.objects.get(pk=device.pk).last_device_seq


def _counted(device: Device) -> int:
    # The number the bootstrap tells the laptop its count stands at (SYNC-8), read as the bootstrap reads it.
    with shop_context(device.shop_id):
        return last_device_number(device)


def test_numbers_in_order_raise_no_flag(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # The usual morning: 1, 2, 3, over two pushes. Nothing is missing, so nothing is flagged.
    _push_numbers(device_a, staff_a, 1, 2)
    _push_numbers(device_a, staff_a, 3)
    assert _gaps(shop_a) == []
    assert _last(device_a) == 3


def test_device_seq_gap_raises_flag(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Done when #1: the Dawa laptop sent #1 and #2; the next push brings #5. #3 and #4 never came: one flag, about #5's
    # line in the answer log, on the laptop's own side so its people see it (X1). It names nobody: the server can't
    # know who made a record it never got. #5 itself is saved, as any record is.
    _push_numbers(device_a, staff_a, 1, 2)
    [answer] = _push_numbers(device_a, staff_a, 5)
    assert answer.status == "accepted"
    [gap] = _gaps(shop_a)
    with shop_context(shop_a):
        line = PushedDocument.objects.get(device_seq=5)
        assert (gap.subject_type, gap.subject_id) == ("pushed_document", line.pk)
        assert not gap.people.exists()
    assert _numbers(gap) == (Decimal(3), Decimal(5))
    # actual − expected: how many are missing.
    assert gap.difference == Decimal(2)
    assert (gap.side_id, gap.status, gap.created_by_id) == (device_a.home_side_id, FlagStatus.OPEN, None)
    assert _last(device_a) == 5


def test_gap_inside_one_batch_raises_one_flag(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # #1 and #3 in the same push: #2 is missing all the same.
    _push_numbers(device_a, staff_a, 1, 3, 4)
    [gap] = _gaps(shop_a)
    assert _numbers(gap) == (Decimal(2), Decimal(3))


def test_a_new_laptop_starts_at_one(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # A laptop just paired sends its first push: it numbers from 1, so a first #3 means #1 and #2 are missing.
    _push_numbers(device_a, staff_a, 3)
    [gap] = _gaps(shop_a)
    assert _numbers(gap) == (Decimal(1), Decimal(3))


def test_a_laptop_that_pushed_before_its_numbers_were_kept_counts_on_from_its_last_record(
    shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # A laptop sent #1 to #3 before the server kept its last number (SYNC-4): its row says nothing, but its answer log
    # holds them. Its next record, #4, follows its last one, and is no gap from 1 to 3 that would never close
    # (SYNC-5's review).
    _push_numbers(device_a, staff_a, 1, 2, 3)
    with shop_context(shop_a):
        Device.objects.filter(pk=device_a.pk).update(last_device_seq=None)
    _push_numbers(device_a, staff_a, 4)
    assert _gaps(shop_a) == []
    assert _last(device_a) == 4


def test_a_new_laptop_has_counted_nothing(device_a: Device) -> None:
    # A laptop just paired has sent nothing: its bootstrap says 0, so its first record is #1.
    assert _counted(device_a) == 0


def test_a_laptop_counts_on_from_the_number_the_server_keeps(device_a: Device, staff_a: StaffMember) -> None:
    # The Dawa laptop's database is wiped, and the bootstrap fills it again (SYNC-8): it carries on from the server's
    # last number, so its next record is #4, never #1 again. #2 came late, after #3: it doesn't pull the count back.
    _push_numbers(device_a, staff_a, 1, 3)
    _push_numbers(device_a, staff_a, 2)
    assert _counted(device_a) == 3


def test_a_laptop_that_pushed_before_its_numbers_were_kept_counts_from_its_highest_line(
    shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # Its row says nothing, as the push's own count reads it (the test above this pair): its answer log says #3.
    _push_numbers(device_a, staff_a, 1, 2, 3)
    with shop_context(shop_a):
        Device.objects.filter(pk=device_a.pk).update(last_device_seq=None)
    assert _counted(device_a) == 3


def test_another_laptops_numbers_are_not_this_ones(
    shop_a: Shop, side_a: Side, device_a: Device, staff_a: StaffMember
) -> None:
    # The office laptop has sent #1 to #5; the Dawa laptop nothing. Each laptop counts on its own (03 §6.3): the Dawa
    # laptop still starts at #1, or the server would flag its #1 as five records gone.
    with shop_context(shop_a):
        office = Device.objects.create(shop=shop_a, home_side=side_a, name="Laptop ya ofisi", code=2, key_hash="b" * 64)
    _push_numbers(office, staff_a, 1, 2, 3, 4, 5)
    assert _counted(office) == 5
    assert _counted(device_a) == 0


def test_a_laptops_number_is_read_only_inside_its_shop(device_a: Device, staff_a: StaffMember, shop_b: Shop) -> None:
    # T1, as every read in apps/sync/selectors.py: asked with another shop open, it fails loudly, never answering
    # a number of another shop's laptop, nor a quiet 0 that would start its count again from #1.
    _push_numbers(device_a, staff_a, 1, 2)
    with shop_context(shop_b):
        with pytest.raises(ShopMismatch):
            last_device_number(device_a)
        with pytest.raises(ShopMismatch):
            highest_pushed_number(device_a)


def test_a_late_record_raises_no_new_flag(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # #3 came before #2, which was only late: #2 fills the gap #3 opened, and is no "number gone back". The laptop's
    # last number stays 3: #4 comes next.
    _push_numbers(device_a, staff_a, 1, 3)
    [answer] = _push_numbers(device_a, staff_a, 2)
    assert answer.status == "accepted"
    assert len(_gaps(shop_a)) == 1
    assert _last(device_a) == 3
    _push_numbers(device_a, staff_a, 4)
    assert len(_gaps(shop_a)) == 1


def _notes(flag: Flag) -> list[tuple[str, str, uuid.UUID | None]]:
    # A flag's notes, oldest first: the step, the words, and who wrote them (None: the system).
    with shop_context(flag.shop_id):
        rows = FlagNote.objects.filter(flag=flag).order_by("created_at", "id")
        return [(note.step, note.text, note.created_by_id) for note in rows]


def _status(flag: Flag) -> str:
    with shop_context(flag.shop_id):
        return Flag.objects.get(pk=flag.pk).status


def test_late_record_resolves_gap_flag(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Done when #1: #1, then #4, so #2 and #3 are missing. #3 comes late: #2 is still missing, so the flag stays open.
    # Then #2 comes: every number the flag waited for is here, so the system closes it with its own note, naming
    # nobody (Jack, SYNC-5; 02 v1.22). The records were only late; nothing was lost.
    _push_numbers(device_a, staff_a, 1, 4)
    [gap] = _gaps(shop_a)
    _push_numbers(device_a, staff_a, 3)
    assert (_status(gap), _notes(gap)) == (FlagStatus.OPEN, [])
    _push_numbers(device_a, staff_a, 2)
    assert _status(gap) == FlagStatus.RESOLVED
    assert _notes(gap) == [(FlagStep.RESOLVED, "flag.device_gap_filled", None)]
    assert len(_gaps(shop_a)) == 1


def test_late_record_beside_new_ones_resolves_its_gap(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # #2 comes late in the same push as the new #4: #2 closes the gap #3 opened, and #4 follows #3 as usual.
    _push(device_a, [_sent(1, staff_a), _sent(3, staff_a)])
    _push(device_a, [_sent(2, staff_a), _sent(4, staff_a)])
    [gap] = _gaps(shop_a)
    assert _status(gap) == FlagStatus.RESOLVED


def test_a_late_invalid_record_resolves_its_gap_too(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # #2 comes late and is set aside as invalid: it came all the same, so nothing is missing any more. Its own flag
    # (invalid_document) says what is wrong with it.
    _push_numbers(device_a, staff_a, 1, 3)
    [gap] = _gaps(shop_a)
    _push(device_a, [_sent(2, staff_a, type="no_such_type")])
    assert _status(gap) == FlagStatus.RESOLVED


def test_late_record_closes_an_explained_gap_flag(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # The manager explained the flag before #2 came: their words stay, and the system's note closes it.
    _push_numbers(device_a, staff_a, 1, 3)
    [gap] = _gaps(shop_a)
    with shop_context(shop_a):
        explain_flag(gap, text="Juma ameifuta?", by=staff_a2)
    _push_numbers(device_a, staff_a, 2)
    assert _status(gap) == FlagStatus.RESOLVED
    assert [step for step, _text, _by in _notes(gap)] == [FlagStep.EXPLAINED, FlagStep.RESOLVED]


def test_late_record_leaves_a_closed_gap_flag_as_it_is(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # A manager dismissed the flag ("the laptop was switched off"); #2 comes later. The flag stays as the manager left
    # it, with no second note, and #2 is no "number gone back": it is still late, not lost.
    _push_numbers(device_a, staff_a, 1, 3)
    [gap] = _gaps(shop_a)
    with shop_context(shop_a):
        dismiss_flag(gap, text="Laptop ilizimwa", by=staff_a2)
    _push_numbers(device_a, staff_a, 2)
    assert _status(gap) == FlagStatus.DISMISSED
    assert [step for step, _text, _by in _notes(gap)] == [FlagStep.DISMISSED]
    assert len(_gaps(shop_a)) == 1


def test_a_record_from_before_a_reset_fills_no_new_gap(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The laptop sent #1 to #10, then was reset: new #1 (its numbers went back), #2, then #5, so the new #3 and #4 are
    # missing. The new #4 was deleted on the laptop; the new #3 comes late. The old #4, from before the reset, is not
    # the new one: the gap stays open, or the deletion would hide behind a record of last week (SYNC-5's review).
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=_keeps_no_row))
    _push_numbers(device_a, staff_a, *range(1, 11))
    _push_numbers(device_a, staff_a, 1, 2, 5)
    back, gap = _gaps(shop_a)
    assert _numbers(gap) == (Decimal(3), Decimal(5))
    _push_numbers(device_a, staff_a, 3)
    assert _status(gap) == FlagStatus.OPEN
    # Once the new #4 comes too, the gap is whole.
    _push_numbers(device_a, staff_a, 4)
    assert _status(gap) == FlagStatus.RESOLVED


def test_another_shops_gap_is_never_filled_or_closed(
    shop_a: Model,
    shop_b: Shop,
    side_b: Side,
    device_a: Device,
    staff_a: StaffMember,
    staff_b: StaffMember,
) -> None:
    # Shop B's laptop misses #2 and #3, as shop A's does. A's late #2 and #3 close A's gap alone: a laptop's numbers
    # are its own, and a gap of another shop is never seen, let alone closed (03 §5.4; SYNC-5's review).
    with shop_context(shop_b):
        device_b = Device.objects.create(shop=shop_b, home_side=side_b, name="Laptop B", code=1, key_hash="b" * 64)
    _push_numbers(device_b, staff_b, 1, 4)
    _push_numbers(device_a, staff_a, 1, 4)
    _push_numbers(device_a, staff_a, 2, 3)
    [gap_a] = _gaps(shop_a)
    [gap_b] = _gaps(shop_b)
    assert (_status(gap_a), _status(gap_b)) == (FlagStatus.RESOLVED, FlagStatus.OPEN)
    assert _notes(gap_b) == []


@pytest.mark.django_db(transaction=True)
def test_a_late_record_and_a_managers_close_take_turns(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # The manager dismisses the gap's flag at the very moment the late #2 arrives. The system's close waits for the
    # manager's, then finds the flag closed, and leaves it as the manager left it: one note, never a second on a
    # closed flag (SYNC-5's review).
    _push_numbers(device_a, staff_a, 1, 3)
    [gap] = _gaps(shop_a)
    with shop_context(shop_a), transaction.atomic():
        dismiss_flag(gap, text="Laptop ilizimwa", by=staff_a2)
        late, ended = in_another_transaction(lambda: _push_numbers(device_a, staff_a, 2))
        wait_until_someone_waits_for_me()
    late.join()
    [answers] = ended
    assert [answer.status for answer in cast(list[Answer], answers)] == ["accepted"]
    assert _status(gap) == FlagStatus.DISMISSED
    assert [step for step, _text, _by in _notes(gap)] == [FlagStep.DISMISSED]


@pytest.mark.django_db(transaction=True)
def test_the_numbers_lock_needs_a_transaction(shop_a: Model, device_a: Device) -> None:
    # Outside a transaction the lock would end with its own query, and two pushes of one laptop could read the same
    # number: refused loudly, as a bug in the calling code.
    with shop_context(shop_a), pytest.raises(TransactionManagementError, match="transaction"):
        lock_device_numbers(device_a)


def test_numbers_gone_back_never_close_by_themselves(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # A flag of numbers gone back waits for no record: nothing can arrive that makes the reset not have happened, so
    # it stays open for a person. #1 to #3, then a reset: #1 to #4 again. Then a #2 below the laptop's count, the one
    # kind of number the server asks the gaps about: the reset's flag is not one it fills, so it stays open, and the
    # stray #2 raises a flag of its own (SYNC-5's review: before, no number here reached that question).
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=_keeps_no_row))
    _push_numbers(device_a, staff_a, 1, 2, 3)
    _push_numbers(device_a, staff_a, 1, 2, 3, 4)
    [back] = _gaps(shop_a)
    _push_numbers(device_a, staff_a, 2)
    first, stray = _gaps(shop_a)
    assert first == back
    assert _status(back) == FlagStatus.OPEN
    assert _numbers(stray) == (Decimal(5), Decimal(2))


def _keeps_no_row(document: Document, payload: dict[str, Any]) -> list[Flag]:
    # A saving code that writes no row of its own. The pretend ticket keeps one ticket per laptop number, as a sale
    # will keep one receipt number per laptop (D2-0457), so it would refuse a second #1 whatever the push decides; with
    # no row, the push's own answer to numbers gone back shows (SYNC-8's and SALE-2's notes).
    return []


def test_numbers_that_go_back_raise_one_flag_and_counting_follows(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The laptop sent #1 to #5, then was reset and numbers again from 1. Its records are kept, one flag says the
    # numbers went back (expected 6, came 1), and the server counts on from 1, so #2 and #3 raise nothing more: a
    # flag for every record after a reset would bury the review list.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=_keeps_no_row))
    _push_numbers(device_a, staff_a, 1, 2, 3, 4, 5)
    answers = _push_numbers(device_a, staff_a, 1, 2, 3)
    assert [answer.status for answer in answers] == ["accepted"] * 3
    [back] = _gaps(shop_a)
    assert _numbers(back) == (Decimal(6), Decimal(1))
    assert _last(device_a) == 3


def test_the_highest_number_and_a_lower_one_after_it_are_both_kept(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # A broken or tampered laptop jumps to the highest number a record may have, then numbers again from 1. Both are
    # kept, each with its flag: the number awaited after the highest one must fit a flag's columns too, or the second
    # flag couldn't be written, and every push after it would answer retry, for good (SYNC-5's review).
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=_keeps_no_row))
    answers = _push_numbers(device_a, staff_a, 1, HIGHEST_DEVICE_SEQ)
    answers += _push_numbers(device_a, staff_a, 1)
    assert [answer.status for answer in answers] == ["accepted"] * 3
    jump, back = _gaps(shop_a)
    assert _numbers(jump) == (Decimal(2), Decimal(HIGHEST_DEVICE_SEQ))
    assert _numbers(back) == (Decimal(HIGHEST_DEVICE_SEQ + 1), Decimal(1))


def test_an_invalid_document_keeps_its_number(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # #2 is a type the server doesn't take: set aside, but it came, so its number is not missing.
    answers = _push(device_a, [_sent(1, staff_a), _sent(2, staff_a, type="no_such_type"), _sent(3, staff_a)])
    assert [answer.status for answer in answers] == ["accepted", "invalid", "accepted"]
    assert _gaps(shop_a) == []
    # And an invalid one can open a gap itself.
    _push(device_a, [_sent(5, staff_a, type="no_such_type")])
    [gap] = _gaps(shop_a)
    assert _numbers(gap) == (Decimal(4), Decimal(5))


def test_a_duplicate_moves_no_number(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # #1 sent again after #2: the first answer again, and no "number gone back".
    first = _sent(1, staff_a)
    _push(device_a, [first, _sent(2, staff_a)])
    [again] = _push(device_a, [first])
    assert again.status == "duplicate"
    assert _gaps(shop_a) == []
    assert _last(device_a) == 2


def test_a_retry_takes_no_number(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # #2 hits a server problem: nothing of it is saved, its number neither. Sent again with #3, both go in, and no gap.
    def crash_on_two(document: Document, payload: dict[str, Any]) -> list[Flag]:
        if document.device_seq == 2:
            raise RuntimeError("the server broke")
        return post_ticket(document, payload)

    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=crash_on_two))
    batch = [_sent(1, staff_a), _sent(2, staff_a), _sent(3, staff_a)]
    assert [answer.status for answer in _push(device_a, batch)] == ["accepted", "retry"]
    assert _last(device_a) == 1
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET)
    assert [answer.status for answer in _push(device_a, batch)] == ["duplicate", "accepted", "accepted"]
    assert _gaps(shop_a) == []
    assert _last(device_a) == 3


@pytest.mark.django_db(transaction=True)
def test_two_pushes_of_one_laptop_take_turns_on_its_numbers(
    shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The laptop sent #1, and, before that push had finished, #2 in a second push (a retry sent too soon). The second
    # waits for the first to finish before it reads the laptop's last number: read at once, it would find none yet,
    # and flag #1 as missing though it is on its way.
    with shop_context(shop_a), transaction.atomic():
        push(
            device_a,
            [_sent(1, staff_a)],
            received_at=RECEIVED_AT,
            sent_at=RECEIVED_AT,
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )
        second, ended = in_another_transaction(lambda: _push_numbers(device_a, staff_a, 2))
        wait_until_someone_waits_for_me()
    second.join()
    [answers] = ended
    assert [answer.status for answer in cast(list[Answer], answers)] == ["accepted"]
    assert _gaps(shop_a) == []
    assert _last(device_a) == 2


@pytest.mark.parametrize("error", [ValidationError("refused", code="flag.numbers_unpaired"), IntegrityError("refused")])
@pytest.mark.parametrize("kind", [FlagKind.DEVICE_GAP, FlagKind.PERMISSION_BREAK])
def test_a_checks_own_error_is_a_retry_never_an_invalid_record(
    monkeypatch: pytest.MonkeyPatch,
    shop_a: Model,
    device_a: Device,
    staff_a: StaffMember,
    kind: FlagKind,
    error: Exception,
) -> None:
    # Writing a flag after the record's line fails: a bug in our code, not in the record. The record isn't set aside
    # as invalid, with a reason about the flag's own columns: it is a server problem, so retry, nothing of it saved,
    # and the laptop sends it again once the bug is fixed (SYNC-5's review). #3 opens a gap, and its maker holds no
    # key, so each flag's write is broken in turn.
    def broken(**kwargs: object) -> None:
        if kwargs["kind"] == kind:
            raise error

    _push_numbers(device_a, staff_a, 1)
    monkeypatch.setattr(push_module, "raise_flag", broken)
    assert [answer.status for answer in _push_numbers(device_a, staff_a, 3)] == ["retry"]
    with shop_context(shop_a):
        assert list(PushedDocument.objects.values_list("device_seq", flat=True)) == [1]
        assert not Ticket.objects.filter(device_seq=3).exists()
    assert _last(device_a) == 1


def test_the_number_check_is_all_or_nothing_with_its_record(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The number's check runs in the record's own transaction: if it fails, nothing of the record is saved, its line
    # neither, and the laptop sends it again (03 §5.5).
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the check broke")

    monkeypatch.setattr(push_module, "_check_number", broken)
    [answer] = _push_numbers(device_a, staff_a, 1)
    assert answer.status == "retry"
    with shop_context(shop_a):
        assert not PushedDocument.objects.exists()
