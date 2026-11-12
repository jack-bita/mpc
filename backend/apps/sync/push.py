"""apps/sync/push.py — saving a batch of documents a laptop pushed: each in the laptop's own order, each in a
transaction of its own, each answered once, and the same way every time it comes again (SYNC-4; 03 §5.5, §6.3).

    for each document, by its laptop number (device_seq):
      in the answer log already?       → duplicate, with the first answer
      type, maker and shape all right?   no → invalid: its line and a flag, and the batch goes on
      save it, in one transaction        → accepted: the document, its change lines, its line, its change number
      its laptop number skips some?      → a device_gap flag about its line, in the same transaction (SYNC-5)
      ... or fills a gap's last place?   → that gap's flag closes itself, with the system's note (SYNC-5)
      its maker holds no key for it?     → a permission_break flag about its line, naming them (SYNC-5)
      made while its maker wasn't working? → a suspended_staff_activity flag, naming them (SYNC-5, X2)
      a server problem?                  → retry, and the batch stops here
    then the laptop's report on itself  → its row: last synced, records still unsent, app version; its outages (SYNC-5)

The route (apps/sync/api/views.py) checks each document's envelope and hands the batch here, with the laptop its key
opened, and that laptop's shop open. Each document's saving code comes from the list of document types
(apps/sync/document_types.py). A broken business rule is never a refusal here: the saving code accepts and flags it.
This file owns the order, the transactions and the answers; the answer log's own rules are in apps/sync/models.py.
"""

import logging
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import psycopg
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import exceptions

from apps.control.models import Flag, FlagKind, FlagStatus
from apps.control.services import raise_flag, resolve_flag_by_system
from apps.core.acting import acting_as
from apps.core.api.errors import INVALID as ONLY_FIELDS_WRONG
from apps.core.api.errors import refusal_parts
from apps.core.changes import recording_changes
from apps.core.links import link_type_of
from apps.people.models import Device, StaffMember
from apps.people.permissions import given_permissions
from apps.people.selectors import was_working_at
from apps.people.services import Outage, lock_device_numbers, move_device_number, record_outages, record_sync
from apps.sync.document_types import Document, DocumentType, document_type
from apps.sync.models import PushedDocument, PushedStatus
from apps.sync.selectors import highest_pushed_number

logger = logging.getLogger(__name__)

# The four answers (03 §6.3). Two are kept in the answer log (PushedStatus); a duplicate is one of them given again,
# and a retry is never kept, as nothing of it was saved.
ACCEPTED = PushedStatus.ACCEPTED.value
INVALID = PushedStatus.INVALID.value
DUPLICATE = "duplicate"
RETRY = "retry"

# The highest number a laptop may give a record (SYNC-5). A missing number's flag keeps two numbers in its own columns
# (Flag.expected and .actual, numeric(15,3): 12 digits before the point): the one that came, and the one awaited, which
# is the laptop's last + 1. So the last may be at most 999,999,999,998, one short of the largest 12-digit number, or
# the next flag couldn't be written and every push after it would answer retry (SYNC-5's review). At 1,000 records
# a day, a laptop would reach it in about 2.7 billion years.
HIGHEST_DEVICE_SEQ = 10**12 - 2


@dataclass(frozen=True)
class Sent:
    # One document as the laptop sent it, its envelope already checked by the route (03 §6.3): its id, made on the
    # laptop (ADR-0007), its type and the version of its shape, the laptop's number for it, the laptop's clock, and
    # the staff member who made it. `payload` is checked here, against its type's shape.
    id: uuid.UUID
    type: str
    schema_version: int
    device_seq: int
    client_time: datetime
    created_by: uuid.UUID
    payload: dict[str, Any]


@dataclass(frozen=True)
class Answer:
    # The answer for one document. `first`: a duplicate's first answer, accepted or invalid, so the laptop knows to
    # mark it sent or set it aside. `posted_seq` and `flags`: an accepted one's. `code` and `fields`: an invalid one's,
    # as the API's error shape names them (apps/core/api/errors.py).
    id: uuid.UUID
    status: str
    first: str | None = None
    posted_seq: int | None = None
    flags: list[dict[str, str]] = field(default_factory=list)
    code: str = ""
    fields: dict[str, list[str]] = field(default_factory=dict)


def push(
    device: Device,
    documents: Sequence[Sent],
    *,
    received_at: datetime,
    sent_at: datetime,
    unsent_count: int,
    app_version: str,
    outages: Sequence[Outage],
) -> list[Answer]:
    """Save a laptop's batch, in its own order, and answer each document. `received_at`: the server's clock when the
    push arrived, the same for the whole batch; `sent_at`: the laptop's clock as it sent it, handed to each document's
    saving code beside it (ATT-1). Stops at the first `retry`: the documents after it get no answer, and
    the laptop sends them again later, in the same order. Then keeps the laptop's report on itself (SYNC-5):
    `unsent_count`, the records it holds besides this batch; `app_version`, the app it runs; and `outages`, the
    offline periods it recorded since it last reported."""
    answers: list[Answer] = []
    # The laptop's order, not the order they arrived in: #3 may be a repayment of the debt #2 made. sorted() keeps two
    # documents with the same number in the order they were sent.
    for sent in sorted(documents, key=lambda document: document.device_seq):
        answer = _answer(device, sent, received_at, sent_at)
        answers.append(answer)
        if answer.status == RETRY:
            break
    # After the batch, so the count is the laptop's as this push leaves it: what it holds besides this batch, and the
    # documents of the batch it must send again, the retry and those after it. An invalid one counts as sent: it was
    # answered, and the laptop sets it aside. The office reads it before approving a drawer's day (M8), so it must not
    # say 0 while a sale waits on the laptop.
    answered = sum(1 for answer in answers if answer.status != RETRY)
    record_outages(device, outages)
    record_sync(device, at=received_at, unsent_count=unsent_count + len(documents) - answered, app_version=app_version)
    return answers


def _answer(device: Device, sent: Sent, received_at: datetime, sent_at: datetime) -> Answer:
    try:
        # Sent before? Look first, before any check: the first copy's own rows would make this one's checks fail.
        # Inside the `try`, as a lost database here is a server problem like any other: this document's `retry`, with
        # the answers before it kept, not a refusal of the whole push.
        stored = _stored(sent.id)
        if stored is not None:
            return _replay(stored)
        return _post(device, sent, received_at, sent_at)
    except Exception:
        # A server problem, not the document's: a bug, or a database that went away. Nothing of it was saved (its
        # transaction rolled back), so the laptop keeps it and sends it again, and the batch stops here to keep the
        # order. Logged with its id, type and laptop, and its traceback, as Django logs any server error: like any
        # server error's, the traceback can quote the row the database refused (03 §5.17).
        logger.exception("Push: server error on document %s (%s) from device %s.", sent.id, sent.type, device.pk)
        return Answer(id=sent.id, status=RETRY)


def _post(device: Device, sent: Sent, received_at: datetime, sent_at: datetime) -> Answer:
    # The maker, read through the guard: a staff member of this shop, or nobody. Someone of another shop is "unknown"
    # here, the same answer as an id no shop has, so the answer tells nothing of other shops (03 §5.4). A maker who
    # was suspended is still found: their document is kept, and SYNC-5 flags it (X2).
    maker = StaffMember.objects.filter(pk=sent.created_by).first()
    try:
        # The checks, in this order, so the first thing wrong is the one named: the type, the maker, the shape.
        kind = document_type(sent.type, sent.schema_version)
        if maker is None:
            raise ValidationError(
                "The document's maker is no staff member of this shop.", code="document.maker_unknown"
            )
        shape = kind.payload(data=sent.payload)
        shape.is_valid(raise_exception=True)
    except (ValidationError, exceptions.ValidationError) as refusal:
        code, fields = refusal_parts(refusal)
        return _invalid(device, sent, received_at, maker, code, fields)
    return _save(device, sent, received_at, sent_at, kind, maker, shape.validated_data)


def _save(
    device: Device,
    sent: Sent,
    received_at: datetime,
    sent_at: datetime,
    kind: DocumentType,
    maker: StaffMember,
    payload: dict[str, Any],
) -> Answer:
    try:
        # One document, one transaction (03 §5.5): its rows, its change lines, its line in the answer log and its
        # laptop's number are saved together, or not at all. X3: both books name its maker and the laptop, for every
        # row its saving code writes or edits. The block opens first, so the services the saving code calls join it,
        # and the change numbers come once, at its end (SYNC-1).
        with acting_as(maker, device=device), transaction.atomic():
            # The laptop's last number, its row locked first of all: every record takes this lock before any other,
            # so two pushes of one laptop take turns in the same order, and can't each wait for the other.
            last = _last_number(device)
            # The document as its saving code gets it. Built under the laptop's lock, so its record before it is read
            # once every record of this laptop that came before it has finished saving (ATT-1).
            time_before, made_before_by = _record_before(device, sent.device_seq)
            document = Document(
                id=sent.id,
                device=device,
                device_seq=sent.device_seq,
                client_time=sent.client_time,
                received_at=received_at,
                sent_at=sent_at,
                time_before=time_before,
                made_before_by=made_before_by,
                created_by=maker,
            )
            # What is wrong with its maker, read now, before the block: once the block has taken the shop's change
            # numbers, the shop's counter stays locked until the commit, and every save of the shop waits (SYNC-1).
            with _checks_of_our_own():
                broken = _maker_breaks(device, kind, maker, made_at=sent.client_time)
            with recording_changes(device.shop_id) as numbers:
                flags = kind.post(document, payload)
            flagged = [{"id": str(flag.pk), "kind": flag.kind} for flag in flags]
            # After the block, still in the transaction: the line keeps the block's last number, known only once the
            # block has ended. The shop's counter stays locked from here to the commit, so only writes come after it:
            # the line, the laptop's number and the flags, and, for a late record alone, the two reads that say
            # whether its gap is whole, as they count the line just saved.
            line = _line(device, sent, received_at, maker, status=ACCEPTED, posted_seq=numbers.last, flags=flagged)
            line.save()
            with _checks_of_our_own():
                _check_number(device, line, last)
                for broken_rule in broken:
                    raise_flag(kind=broken_rule, subject=line, side=device.home_side, people=[maker], by=None)
    except (ValidationError, IntegrityError) as refusal:
        # Refused, and all of it rolled back. Perhaps by a twin: another copy of this document, sent at the same
        # moment, that finished while this one was saving, so its rows or its line clash with this copy's. Its
        # answer is the answer (CORE-6), so the answer log is read again after every refusal, not only a clash.
        twin = _stored(sent.id)
        if twin is not None:
            return _replay(twin)
        if isinstance(refusal, ValidationError):
            # A refusal of the saving code's own, for what can't be saved even with a flag. Its check before the insert
            # (full_clean) reads through the shop's guard: it calls an id of a row of this shop "unique", while another
            # shop's only the insert finds. So that "unique" is left out, as CORE-6's create does
            # (_without_the_ids_clash, apps/core/api/base.py): the rest of what is wrong is the answer, else the id is
            # taken, the same two answers as for another shop's row (03 §5.4).
            code, fields = refusal_parts(refusal)
            fields, an_id_was_taken = _without_ids_taken(fields)
            if an_id_was_taken and not fields and code == ONLY_FIELDS_WRONG:
                return _invalid(device, sent, received_at, maker, "id.taken", {})
            return _invalid(device, sent, received_at, maker, code, fields)
        if _id_taken(refusal):
            # No twin, yet an id clashes: a row this shop can't see has it, another shop's (03 §5.4). Answered without
            # a word about that row, not even which table it is in.
            return _invalid(device, sent, received_at, maker, "id.taken", {})
        # Another database rule, which the saving code should have checked first: a bug, so a retry (_answer).
        raise
    return Answer(id=sent.id, status=ACCEPTED, posted_seq=numbers.last, flags=flagged)


def _invalid(
    device: Device,
    sent: Sent,
    received_at: datetime,
    maker: StaffMember | None,
    code: str,
    fields: dict[str, list[str]],
) -> Answer:
    # Set aside: its line, with the reason, and a flag about the line, naming its maker if known, in one transaction
    # of their own, so a repeat gets the same answer and raises no second flag (03 §6.3). The laptop keeps the
    # document under "needs attention". It came, so its number is not missing: it moves the laptop's number as a
    # saved one does, in the same transaction.
    try:
        with transaction.atomic():
            last = _last_number(device)
            line = _line(device, sent, received_at, maker, status=INVALID, reason=code, reason_fields=fields)
            line.save()
            raise_flag(kind=FlagKind.INVALID_DOCUMENT, subject=line, people=[] if maker is None else [maker], by=None)
            with _checks_of_our_own():
                _check_number(device, line, last)
    except IntegrityError:
        # A twin wrote its line first: its answer is the answer, as in _save.
        twin = _stored(sent.id)
        if twin is None:
            raise
        return _replay(twin)
    return Answer(id=sent.id, status=INVALID, code=code, fields=fields)


class CheckFailed(Exception):
    # A check of the push's own, after the record's line, refused: a flag that couldn't be written, a device row that
    # couldn't be moved. A bug in our code, never a fault of the record.
    pass


@contextmanager
def _checks_of_our_own() -> Iterator[None]:
    # The push's own checks run after the record's line, inside the record's transaction, inside the `try` that reads
    # the saving code's refusals. A ValidationError or IntegrityError of theirs would read as the record's own: set
    # aside as invalid, its rows rolled back, the laptop told a reason about a flag's columns. So each becomes a plain
    # server error, which rolls the whole record back and answers retry (_answer), as any bug does (SYNC-5's review).
    try:
        yield
    except (ValidationError, IntegrityError) as error:
        raise CheckFailed("A check of the push's own failed after the record's line.") from error


def _last_number(device: Device) -> int:
    # The number the laptop's next record should follow, its row locked until the record's transaction ends
    # (lock_device_numbers). When the server never kept one, the laptop's highest line in the answer log says it: a
    # laptop that pushed before SYNC-5 counts on from its last record, not from 0, which would flag every number it
    # ever sent as missing (SYNC-5's review). A new laptop has no line, so it starts at 1.
    last = lock_device_numbers(device)
    if last is not None:
        return last
    # The same fallback the bootstrap sends a laptop (last_device_number), from one function, so the two never differ.
    return highest_pushed_number(device)


def _record_before(device: Device, device_seq: int) -> tuple[datetime | None, uuid.UUID | None]:
    # The laptop's own time on the record it numbered last before this one, of those the server holds, and who made
    # it (ATT-1): the evidence a clock-in's time check reads, as only this log holds every record of the laptop,
    # whatever its type; (None, None) when it holds none. A set-aside one counts too: it was made at the counter all
    # the same. After a laptop reset, which numbers again from 1 (SYNC-5), two lines can share a number: the newer is
    # the new count's, so it is the one before. Read through the index on (shop, device, device_seq): one row, however
    # many records the laptop has sent.
    found = (
        PushedDocument.objects.filter(device=device, device_seq__lt=device_seq)
        .order_by("-device_seq", "-created_at", "-id")
        .values_list("client_time", "created_by_id")
        .first()
    )
    return (None, None) if found is None else found


def _check_number(device: Device, line: PushedDocument, last: int) -> None:
    # The laptop numbers its records 1, 2, 3 and never skips one (03 §6.3), so after `last` comes `last + 1` (SYNC-5).
    # Run after the record's line, in its transaction: the flag is about the line, and a record rolled back takes its
    # number and its flag with it. Never a refusal: the record is kept whatever its number (accept, then flag).
    number = line.device_seq
    awaited = last + 1
    if number == awaited:
        move_device_number(device, number)
    elif number > awaited:
        # A jump: the numbers from `awaited` to `number - 1` never came, deleted on the laptop or lost.
        _flag_numbers(device, line, awaited)
        move_device_number(device, number)
    elif gaps := _gaps_waiting_for(device, line):
        # Late, not lost: one of the numbers a gap's flag waits for. The laptop's count stays where it was, and a gap
        # whose every number has now come closes by itself (Jack, SYNC-5; 02 v1.22).
        for gap in gaps:
            # Still open: one a manager closed stays as they left it, and its numbers aren't counted again.
            if gap.status in (FlagStatus.OPEN, FlagStatus.EXPLAINED) and _every_number_came(device, gap):
                resolve_flag_by_system(gap)
    else:
        # The numbers went back: a laptop reset that numbers again from 1, or a bug on it. Kept and flagged once, then
        # counted on from here, or every record after a reset would raise a flag of its own.
        _flag_numbers(device, line, awaited)
        move_device_number(device, number)


def _maker_breaks(device: Device, kind: DocumentType, maker: StaffMember, *, made_at: datetime) -> list[FlagKind]:
    # The rules the maker broke by making this record, checked again on the server (SYNC-5): the laptop checked them at
    # the counter, but against its own copy of the shop, which can be old, on a laptop that can be tampered with. Each
    # becomes one flag about the record's line, naming the maker, on the laptop's side, for its managers to see; none
    # refuses the record (accept, then flag).
    broken = []
    # The key for this type, on the laptop's own side, as its counter asks (X1): a seller of Vyakula holds no key on
    # the Dawa laptop. Among the keys the person was given, whatever their status: a suspended maker's sale is the
    # suspension's flag, not a second one saying they hold no key. A note for SALE-2: a sale that names its own side is
    # checked on the laptop's side all the same, until that card says otherwise. A type that names no key, a clock-in,
    # has nothing to check here (Jack, ATT-1).
    if kind.permission is not None and kind.permission not in given_permissions(maker).on(device.home_side_id):
        broken.append(FlagKind.PERMISSION_BREAK)
    # Working here when they made it (X2)? A laptop offline when Baba suspended Juma doesn't know, so its PIN check
    # still lets him in. By the laptop's clock, the one time the record carries: Juma's sale made at 09:00 is his,
    # though Baba suspended him at 11:00, before the laptop synced. Leaving counts too (Jack, SYNC-5): a person's keys
    # stay given when they go, so the key check alone would let their sale pass.
    if not was_working_at(maker, made_at):
        broken.append(FlagKind.SUSPENDED_STAFF_ACTIVITY)
    return broken


def _flag_numbers(device: Device, line: PushedDocument, awaited: int) -> None:
    # One device_gap flag about the record that came: the number the server waited for, and the one that came. Their
    # difference is how many are missing, or below zero when the numbers went back. On the laptop's own side, so its
    # people see it (X1); naming nobody, as the server can't know who made a record it never got.
    raise_flag(
        kind=FlagKind.DEVICE_GAP,
        subject=line,
        expected=Decimal(awaited),
        actual=Decimal(line.device_seq),
        side=device.home_side,
        by=None,
    )


def _gaps_waiting_for(device: Device, line: PushedDocument) -> list[Flag]:
    # The device_gap flags of this laptop that wait for the line's number: between the number a flag waited for and
    # the one that came after the gap, that one left out. Whatever their status: a record that comes late is late,
    # even after a manager closed its flag. A flag of numbers gone back waits for none (its `expected` is above its
    # `actual`), so it never matches. Asked only of a number below the laptop's count, which is rare.
    lines = PushedDocument.objects.filter(device=device).values("pk")
    return list(
        Flag.objects.filter(
            kind=FlagKind.DEVICE_GAP,
            subject_type=link_type_of(line),
            subject_id__in=lines,
            expected__lte=line.device_seq,
            actual__gt=line.device_seq,
        )
    )


def _every_number_came(device: Device, gap: Flag) -> bool:
    # Whether every number the gap waited for, from `expected` to `actual - 1`, now has a line from this laptop, the
    # record just saved included (its line is in this transaction). Only lines saved after the flag count: a late
    # record always comes after the gap was flagged, and a line from before it is an older count's, before a reset,
    # which must not fill the new count's place and hide a record deleted since (SYNC-5's review). Counted once each:
    # a number that came twice, as two documents, fills one place. A number of the new count can still fill an old
    # gap's place after a reset: the server can't tell the two counts apart, and the reset's own flag stays open for a
    # person.
    first, after = int(cast(Decimal, gap.expected)), int(cast(Decimal, gap.actual))
    came = (
        PushedDocument.objects.filter(
            device=device, device_seq__gte=first, device_seq__lt=after, created_at__gt=gap.created_at
        )
        .values("device_seq")
        .distinct()
        .count()
    )
    return came == after - first


def _line(
    device: Device, sent: Sent, received_at: datetime, maker: StaffMember | None, **answer: Any
) -> PushedDocument:
    # The document's line in the answer log: what the laptop sent, as it sent it, and the answer it got.
    return PushedDocument(
        shop_id=device.shop_id,
        device=device,
        device_seq=sent.device_seq,
        client_time=sent.client_time,
        received_at=received_at,
        document_id=sent.id,
        type=sent.type,
        schema_version=sent.schema_version,
        created_by=maker,
        **answer,
    )


def _stored(document_id: uuid.UUID) -> PushedDocument | None:
    # The document's line in the open shop's answer log, if it has one: the guard hides every other shop's.
    return PushedDocument.objects.filter(document_id=document_id).first()


def _replay(line: PushedDocument) -> Answer:
    # The first answer again, as its line keeps it, never worked out anew (03 §5.5): "duplicate", with what it was.
    return Answer(
        id=line.document_id,
        status=DUPLICATE,
        first=line.status,
        posted_seq=line.posted_seq,
        flags=line.flags,
        code=line.reason,
        fields=line.reason_fields,
    )


def _without_ids_taken(fields: dict[str, list[str]]) -> tuple[dict[str, list[str]], bool]:
    # The refusal's fields less "unique" on an id, the document's (`id`) or one of its rows' (`lines.0.id`): every such
    # id is the laptop's own. And whether one was there.
    kept: dict[str, list[str]] = {}
    taken = False
    for name, codes in fields.items():
        if name == "id" or name.endswith(".id"):
            rest = [code for code in codes if code != "unique"]
            taken = taken or len(rest) < len(codes)
            codes = rest
        if codes:
            kept[name] = codes
    return kept, taken


def _id_taken(error: IntegrityError) -> bool:
    # True when the refused insert broke a table's primary key: an id the laptop made, a document's or one of its
    # rows', is already taken. PostgreSQL names the broken rule, and names a table's primary key "<table>_pkey". The
    # answer log's own ids are the server's, so they never clash.
    cause = error.__cause__
    return isinstance(cause, psycopg.errors.UniqueViolation) and (cause.diag.constraint_name or "").endswith("_pkey")
