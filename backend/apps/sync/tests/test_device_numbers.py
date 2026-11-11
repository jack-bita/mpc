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
from django.db import transaction
from django.db.models import Model

from apps.control.models import Flag, FlagKind, FlagNote, FlagStatus, FlagStep
from apps.control.services import dismiss_flag, explain_flag
from apps.core.links import LINK_TYPES
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.sync import push as push_module
from apps.sync.document_types import DOCUMENT_TYPES, Document
from apps.sync.models import PushedDocument
from apps.sync.push import Answer, Sent, push
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me
from tests.probe.documents import TICKET, TICKET_CODE, post_ticket

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
        return push(device, documents, received_at=RECEIVED_AT, unsent_count=0, app_version="2026.11.1", outages=[])


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


def test_numbers_gone_back_never_close_by_themselves(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # A flag of numbers gone back waits for no record: nothing can arrive that makes the reset not have happened, so
    # it stays open for a person.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=_keeps_no_row))
    _push_numbers(device_a, staff_a, 1, 2, 3)
    _push_numbers(device_a, staff_a, 1, 2, 3, 4)
    [back] = _gaps(shop_a)
    assert _status(back) == FlagStatus.OPEN


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


def test_the_number_check_runs_after_the_line(
    monkeypatch: pytest.MonkeyPatch, shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The flag is about the record's line, so the line must be saved first; and if the check fails, the record is not
    # saved without it: one transaction, all or nothing (03 §5.5).
    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the check broke")

    monkeypatch.setattr(push_module, "_check_number", broken)
    [answer] = _push_numbers(device_a, staff_a, 1)
    assert answer.status == "retry"
    with shop_context(shop_a):
        assert not PushedDocument.objects.exists()
