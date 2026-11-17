"""tests/probe/documents.py — a pretend offline document type, the ticket, for the push's tests (SYNC-4).

A ticket stands for a sale: the laptop makes it at the counter, and the push saves it as one Ticket row (the test-only
table built on CounterRecord, tests/probe/models.py), as SALE-2 will save a sale. Its handler does what every real one
will do: it saves inside a recording_changes block, which joins the push's own block for the document, so its change
lines are numbered once, at the document's end; and it raises a flag for a broken rule instead of refusing it (accept,
then flag, 03 §6.3). The tests put it on the list of document types (apps/sync/document_types.py), and give Ticket a
link type code, for as long as each test runs.
"""

from typing import Any

from rest_framework import serializers

from apps.control.models import Flag, FlagKind
from apps.control.services import raise_flag
from apps.core.changes import record_change, recording_changes
from apps.core.permissions import Permission
from apps.sync.document_types import Document, DocumentType
from tests.probe.models import Ticket

# The link type code the tests give Ticket: its change lines and its flags name it by this.
TICKET_CODE = "ticket"


class TicketShape(serializers.Serializer[Any]):
    # What the pretend sale sold, at most 100 letters: a longer text is a wrong shape, and the document is invalid.
    text = serializers.CharField(max_length=100)
    # A rule the pretend sale broke, as a sale below its floor price would: it is saved, and flagged with this kind.
    broke = serializers.ChoiceField(choices=FlagKind.choices, required=False)


def post_ticket(document: Document, payload: dict[str, Any]) -> list[Flag]:
    """Save the ticket, and flag the rule it broke, if any."""
    shop_id = document.device.shop_id
    with recording_changes(shop_id):
        ticket = Ticket(
            id=document.id,
            shop_id=shop_id,
            device=document.device,
            device_seq=document.device_seq,
            client_time=document.client_time,
            received_at=document.received_at,
            text=payload["text"],
            created_by=document.created_by,
        )
        # An INSERT, never an UPDATE: a ticket's id comes from the laptop, and one another shop already holds must
        # clash on the primary key, not overwrite that shop's row (03 §5.4).
        ticket.save(force_insert=True)
        record_change(ticket)
    if "broke" not in payload:
        return []
    return [raise_flag(kind=payload["broke"], subject=ticket, people=[document.created_by], by=None)]


TICKET = DocumentType("ticket", 1, TicketShape, post_ticket, Permission.SALE_WRITE)
