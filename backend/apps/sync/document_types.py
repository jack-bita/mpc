"""apps/sync/document_types.py — the list of document types a push takes, each in the versions of its shape the
server still reads, with its saving code and the permission its maker needs, if any (SYNC-4; 03 §6.3, §6.8).

    ("clock", 1)  its shape, its saving code, no key        (ATT-1; the laptop's side is SYNC-11's)
    ("sale", 2)   its shape, its saving code, sale.write   (SALE-2)
    ("sale", 1)   kept until every laptop sends version 2

A card that adds an offline document type lists it here, from its app's documents.py, with the other three parts
rule 6 asks for: its schema version, the device side, and tests on both sides. The four may come in two cards, the
server's first, as the clock-in's did (ATT-1, then SYNC-11; Jack): no laptop sends a type before its side is built.
A shape that changes gets a new version, and the old one stays until every laptop has updated: the server takes the
current and the previous one.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError
from rest_framework import serializers

from apps.control.models import Flag
from apps.core.permissions import Permission
from apps.people.models import Device, StaffMember
from apps.staffpay.documents import ClockShape, post_clock


@dataclass(frozen=True)
class Document:
    # One document as the push hands it to its saving code: the parts every type carries, checked, around its own
    # payload (03 §6.3). The device is the one whose key sent the push, never one the document names (AUTH-2), and
    # created_by the staff member of this shop who made it at the counter (X3).
    id: uuid.UUID
    device: Device
    device_seq: int
    client_time: datetime
    received_at: datetime
    # The laptop's clock as it sent the push that brought this document, the same for the whole batch (ATT-1). Not a
    # fact of the document, so it is not kept on it: a resend carries another. A clock-in reads it beside received_at
    # and client_time, as the evidence of 02 §12.
    sent_at: datetime
    # The laptop's own time on its record numbered last before this one, of those the server holds, whatever their type
    # or answer; None when it holds none (ATT-1). A later record with an earlier time means the laptop's clock went
    # back between the two (02 §12).
    time_before: datetime | None
    # Who made that record, as its line in the answer log names them; None when it names nobody of this shop, or
    # there is none. A later record with an earlier time says a clock moved between the two, not at which, so a
    # clock-in's flag names them too (Jack, ATT-1's review).
    made_before_by: uuid.UUID | None
    created_by: StaffMember


@dataclass(frozen=True)
class DocumentType:
    # One type of document a laptop may push, in one version of its shape.
    name: str  # as the laptop sends it in `type`: "sale"
    schema_version: int  # the shape's version: 1, 2...
    payload: type[serializers.Serializer[Any]]  # what a correct payload looks like; a wrong one is invalid
    # Saves it, inside the push's own transaction for this one document, and hands back the flags it raised.
    post: Callable[[Document, dict[str, Any]], list[Flag]]
    # What its maker needs, on the laptop's side; checked again as it arrives (apps/sync/push.py): a maker without it
    # gets a permission_break flag, never a refusal. None for a type everyone working at the shop may make, on any of
    # its laptops: a clock-in (Jack, ATT-1). Baraka works on Vyakula, and clocks in on the Dawa laptop when Vyakula's
    # is off; a key checked on the laptop's side would flag him each time. A maker who wasn't working when they made
    # it is still flagged, whatever the type (X2).
    permission: Permission | None


# The types a push takes, by name and version. The clock-in first (ATT-1); the sale joins with SALE-2.
DOCUMENT_TYPES: dict[tuple[str, int], DocumentType] = {
    # A tap of Ingia or Toka (apps/staffpay/documents.py). No key: anyone working at the shop may clock in on any of its
    # laptops (Jack, ATT-1).
    ("clock", 1): DocumentType("clock", 1, ClockShape, post_clock, None),
}


def document_type(name: str, schema_version: int) -> DocumentType:
    """The listed type a pushed document names, by its type and the version of its shape. Refused, never guessed,
    when the pair isn't listed: the push answers that document `invalid` with the refusal's code (03 §6.3)."""
    found = DOCUMENT_TYPES.get((name, schema_version))
    if found is not None:
        return found
    # Two codes, so whoever reads the flag knows what to fix: a known type in a version the server doesn't take means
    # a laptop newer than the server, or one too old to sync; an unknown type is a document no laptop should send.
    # English for the logs; the app shows the code's own sentence (ADR-0040).
    if any(listed == name for listed, _version in DOCUMENT_TYPES):
        raise ValidationError(
            f"The server takes no version {schema_version} of a {name!r} document.", code="document.version_unknown"
        )
    raise ValidationError(f"The server takes no {name!r} document.", code="document.type_unknown")
