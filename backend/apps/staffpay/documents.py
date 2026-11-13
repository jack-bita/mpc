"""apps/staffpay/documents.py — the clock document: a tap of Ingia or Toka a shop laptop pushes, saved as one line
in the attendance book (ATT-1; 02 §12, 03 §6.3).

    {"type": "clock", "schema_version": 1, ..., "payload": {"kind": "in", "last_server_time": "2026-11-10T03:50:00Z"}}

The push (apps/sync/push.py) checks the envelope, the maker and the shape, then calls post_clock inside its own
transaction for the document; the list of document types (apps/sync/document_types.py) names it. As every saving
code does (tests/probe/documents.py): it saves inside a recording_changes block, which joins the push's; an INSERT
with the laptop's id, so an id another shop holds clashes and is never overwritten; and a broken rule is a flag,
never a refusal (accept, then flag). A clock-in needs no key: anyone working at the shop may clock in on any of its
laptops (Jack, ATT-1).
"""

import datetime as dt
import uuid
from typing import Any, Protocol

from rest_framework import serializers

from apps.control.models import Flag, FlagKind
from apps.control.services import raise_flag
from apps.core.api.times import ZonedDateTimeField
from apps.core.changes import record_change, recording_changes
from apps.people.models import Device, StaffMember
from apps.staffpay.calculations import Evidence, Sign, check_time
from apps.staffpay.models import AttendanceEvent, ClockKind, TimeCheck


class Pushed(Protocol):
    # What the saving code reads of a pushed document; the push's Document (apps/sync/document_types.py) has each
    # part. Written here as a shape, not imported: `sync` is the layer above (ADR-0041), and hands its Document in.
    # The type checker proves it fits where the list of types names post_clock. Read-only, as the Document is frozen.
    @property
    def id(self) -> uuid.UUID: ...
    @property
    def device(self) -> Device: ...
    @property
    def device_seq(self) -> int: ...
    @property
    def client_time(self) -> dt.datetime: ...
    @property
    def received_at(self) -> dt.datetime: ...
    @property
    def sent_at(self) -> dt.datetime: ...
    @property
    def time_before(self) -> dt.datetime | None: ...
    @property
    def made_before_by(self) -> uuid.UUID | None: ...
    @property
    def created_by(self) -> StaffMember: ...
    @property
    def carried(self) -> bool: ...


class ClockShape(serializers.Serializer[Any]):
    # A clock document's payload, its shape's version 1: a wrong one is set aside as invalid, with the field that is
    # wrong, and nothing goes in the book. What the worker tapped: in or out.
    kind = serializers.ChoiceField(choices=ClockKind.choices)
    # The last time the server had told the laptop, at a pull before the tap: the evidence for sign 2 of the time
    # check. The laptop keeps it in its `meta` store (03 §6.1) and writes it on the clock-in as it saves it, so it is
    # the one the laptop knew at the tap, not at the push. With its zone, as every time a laptop sends (ATT-1's review).
    last_server_time = ZonedDateTimeField()


def post_clock(document: Pushed, payload: dict[str, Any]) -> list[Flag]:
    """Save one tap of Ingia or Toka in the attendance book, its time checked, and flag it when the time can't be
    trusted. The line is its maker's: a worker clocks in for themselves, by their PIN (X3)."""
    shop_id = document.device.shop_id
    # The time check, from the evidence the push handed over and the payload's own (apps/staffpay/calculations.py).
    checked = check_time(
        Evidence(
            client_time=document.client_time,
            sent_at=document.sent_at,
            time_before=document.time_before,
            received_at=document.received_at,
            last_server_time=payload["last_server_time"],
            carried=document.carried,
        )
    )
    with recording_changes(shop_id):
        event = AttendanceEvent(
            id=document.id,
            shop_id=shop_id,
            device=document.device,
            device_seq=document.device_seq,
            client_time=document.client_time,
            received_at=document.received_at,
            created_by=document.created_by,
            staff=document.created_by,
            kind=payload["kind"],
            trusted_time=checked.trusted_time,
            time_check=checked.time_check,
            last_server_time=payload["last_server_time"],
            clock_error=checked.clock_error,
        )
        # An INSERT, never an UPDATE: the id comes from the laptop, and one another shop already holds must clash on
        # the primary key, not overwrite that shop's line (03 §5.4).
        event.save(force_insert=True)
        record_change(event)
    if checked.time_check != TimeCheck.UNVERIFIED:
        return []
    # A sign the laptop's clock moved, or a record carried in a rescue file: the line is kept, and flagged for a
    # manager, naming the worker (02 §12, SYNC-12). On no side: attendance belongs to the whole shop, as its rules do,
    # so the flag is the shop's. A carried one has no sign 1, so its flag names nobody else.
    people = [document.created_by]
    # Sign 1 says two records disagree, not whose clock moved: back for this tap, or forward for the one before. So the
    # flag names that record's maker too, for a manager to check both (Jack, ATT-1's review). Read only now, through
    # the shop's guard, as a flag is rare; someone the guard can't find is left out.
    if Sign.RECORD_BEFORE_IS_LATER in checked.signs and document.made_before_by is not None:
        people.extend(StaffMember.objects.filter(pk=document.made_before_by))
    return [raise_flag(kind=FlagKind.UNVERIFIED_TIME, subject=event, people=people, by=None)]
