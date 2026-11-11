"""apps/sync/push.py — saving a batch of documents a laptop pushed: each in the laptop's own order, each in a
transaction of its own, each answered once, and the same way every time it comes again (SYNC-4; 03 §5.5, §6.3).

    for each document, by its laptop number (device_seq):
      in the answer log already?       → duplicate, with the first answer
      type, maker and shape all right?   no → invalid: its line and a flag, and the batch goes on
      save it, in one transaction        → accepted: the document, its change lines, its line, its change number
      a server problem?                  → retry, and the batch stops here
    then the laptop's report on itself  → its row: last synced, records still unsent, app version (SYNC-5)

The route (apps/sync/api/views.py) checks each document's envelope and hands the batch here, with the laptop its key
opened, and that laptop's shop open. Each document's saving code comes from the list of document types
(apps/sync/document_types.py). A broken business rule is never a refusal here: the saving code accepts and flags it.
This file owns the order, the transactions and the answers; the answer log's own rules are in apps/sync/models.py.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psycopg
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import exceptions

from apps.control.models import FlagKind
from apps.control.services import raise_flag
from apps.core.acting import acting_as
from apps.core.api.errors import INVALID as ONLY_FIELDS_WRONG
from apps.core.api.errors import refusal_parts
from apps.core.changes import recording_changes
from apps.people.models import Device, StaffMember
from apps.people.services import record_sync
from apps.sync.document_types import Document, DocumentType, document_type
from apps.sync.models import PushedDocument, PushedStatus

logger = logging.getLogger(__name__)

# The four answers (03 §6.3). Two are kept in the answer log (PushedStatus); a duplicate is one of them given again,
# and a retry is never kept, as nothing of it was saved.
ACCEPTED = PushedStatus.ACCEPTED.value
INVALID = PushedStatus.INVALID.value
DUPLICATE = "duplicate"
RETRY = "retry"


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
    device: Device, documents: Sequence[Sent], *, received_at: datetime, unsent_count: int, app_version: str
) -> list[Answer]:
    """Save a laptop's batch, in its own order, and answer each document. `received_at`: the server's clock when the
    push arrived, the same for the whole batch. Stops at the first `retry`: the documents after it get no answer, and
    the laptop sends them again later, in the same order. Then keeps the laptop's report on itself (SYNC-5):
    `unsent_count`, the records it holds besides this batch, and `app_version`, the app it runs."""
    answers: list[Answer] = []
    # The laptop's order, not the order they arrived in: #3 may be a repayment of the debt #2 made. sorted() keeps two
    # documents with the same number in the order they were sent.
    for sent in sorted(documents, key=lambda document: document.device_seq):
        answer = _answer(device, sent, received_at)
        answers.append(answer)
        if answer.status == RETRY:
            break
    # After the batch, so the count is the laptop's as this push leaves it: what it holds besides this batch, and the
    # documents of the batch it must send again, the retry and those after it. An invalid one counts as sent: it was
    # answered, and the laptop sets it aside. The office reads it before approving a drawer's day (M8), so it must not
    # say 0 while a sale waits on the laptop.
    answered = sum(1 for answer in answers if answer.status != RETRY)
    record_sync(device, at=received_at, unsent_count=unsent_count + len(documents) - answered, app_version=app_version)
    return answers


def _answer(device: Device, sent: Sent, received_at: datetime) -> Answer:
    try:
        # Sent before? Look first, before any check: the first copy's own rows would make this one's checks fail.
        # Inside the `try`, as a lost database here is a server problem like any other: this document's `retry`, with
        # the answers before it kept, not a refusal of the whole push.
        stored = _stored(sent.id)
        if stored is not None:
            return _replay(stored)
        return _post(device, sent, received_at)
    except Exception:
        # A server problem, not the document's: a bug, or a database that went away. Nothing of it was saved (its
        # transaction rolled back), so the laptop keeps it and sends it again, and the batch stops here to keep the
        # order. Logged with its id, type and laptop, and its traceback, as Django logs any server error: like any
        # server error's, the traceback can quote the row the database refused (03 §5.17).
        logger.exception("Push: server error on document %s (%s) from device %s.", sent.id, sent.type, device.pk)
        return Answer(id=sent.id, status=RETRY)


def _post(device: Device, sent: Sent, received_at: datetime) -> Answer:
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
    return _save(device, sent, received_at, kind, maker, shape.validated_data)


def _save(
    device: Device, sent: Sent, received_at: datetime, kind: DocumentType, maker: StaffMember, payload: dict[str, Any]
) -> Answer:
    document = Document(
        id=sent.id,
        device=device,
        device_seq=sent.device_seq,
        client_time=sent.client_time,
        received_at=received_at,
        created_by=maker,
    )
    try:
        # One document, one transaction (03 §5.5): its rows, its change lines and its line in the answer log are
        # saved together, or not at all. X3: both books name its maker and the laptop, for every row its saving code
        # writes or edits. The block opens first, so the services the saving code calls join it, and the change
        # numbers come once, at its end (SYNC-1).
        with acting_as(maker, device=device), transaction.atomic():
            with recording_changes(device.shop_id) as numbers:
                flags = kind.post(document, payload)
            flagged = [{"id": str(flag.pk), "kind": flag.kind} for flag in flags]
            # After the block, still in the transaction: the line keeps the block's last number, known only once the
            # block has ended. The shop's change counter stays locked for this one more INSERT, until the commit.
            _line(device, sent, received_at, maker, status=ACCEPTED, posted_seq=numbers.last, flags=flagged).save()
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
    # document under "needs attention".
    try:
        with transaction.atomic():
            line = _line(device, sent, received_at, maker, status=INVALID, reason=code, reason_fields=fields)
            line.save()
            raise_flag(kind=FlagKind.INVALID_DOCUMENT, subject=line, people=[] if maker is None else [maker], by=None)
    except IntegrityError:
        # A twin wrote its line first: its answer is the answer, as in _save.
        twin = _stored(sent.id)
        if twin is None:
            raise
        return _replay(twin)
    return Answer(id=sent.id, status=INVALID, code=code, fields=fields)


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
