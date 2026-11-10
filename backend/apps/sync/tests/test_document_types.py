"""apps/sync/tests/test_document_types.py — the list of document types a push takes (SYNC-4; 03 §6.3).

A laptop sends each document with its type and the version of its shape, and the list (apps/sync/document_types.py)
says, for each pair, what a correct one looks like, which code saves it, and the permission its maker needs:

    ("sale", 2)   its shape, its saving code, sale.write
    ("sale", 1)   kept while some laptops still send the old shape (03 §6.8)

A pair that isn't listed is refused, with a code that says which half is unknown. The real list is empty until SALE-2
and ATT-1 add the first types, so these tests list pretend ones, two versions of a "ticket", for as long as each test
runs (monkeypatch puts the list back after it).
"""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from rest_framework import serializers

from apps.control.models import Flag
from apps.core.permissions import Permission
from apps.sync.document_types import DOCUMENT_TYPES, Document, DocumentType, document_type


class _TicketShape(serializers.Serializer[Any]):
    # The pretend ticket's shape: one line of text, as the test-only Ticket table holds (backend/tests/probe/).
    text = serializers.CharField(max_length=100)


def _post_nothing(document: Document, payload: dict[str, Any]) -> list[Flag]:
    # Saving is the push's to test (test_push.py): here only the list itself is looked at.
    return []


TICKET_V1 = DocumentType("ticket", 1, _TicketShape, _post_nothing, Permission.SALE_WRITE)
TICKET_V2 = DocumentType("ticket", 2, _TicketShape, _post_nothing, Permission.SALE_WRITE)


@pytest.fixture
def pretend_types(monkeypatch: pytest.MonkeyPatch) -> None:
    # Both versions of the ticket on the list, the way SALE-2 will list a sale's while laptops update.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET_V1)
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 2), TICKET_V2)


def _refusal_code(name: str, schema_version: int) -> str | None:
    # The code a lookup is refused with: what the push will put in its `invalid` answer.
    with pytest.raises(ValidationError) as refusal:
        document_type(name, schema_version)
    return refusal.value.code


@pytest.mark.usefixtures("pretend_types")
def test_a_listed_type_is_found_by_name_and_version() -> None:
    # A laptop that sends "ticket, version 2" gets version 2's shape and saving code.
    assert document_type("ticket", 2) is TICKET_V2


@pytest.mark.usefixtures("pretend_types")
def test_the_previous_version_is_still_found() -> None:
    # The server takes the current version and the one before it (03 §6.8): a laptop that hasn't updated yet still
    # sends the old shape, and its offline sales must still go in.
    assert document_type("ticket", 1) is TICKET_V1


@pytest.mark.usefixtures("pretend_types")
def test_an_unknown_type_is_refused() -> None:
    # A type the server doesn't take offline, or never heard of: refused, and the laptop sets the document aside under
    # "needs attention" (03 §6.3). Never guessed at.
    assert _refusal_code("receipt", 1) == "document.type_unknown"


@pytest.mark.usefixtures("pretend_types")
def test_an_unknown_version_of_a_known_type_is_refused() -> None:
    # A known type in a shape the server doesn't take: a laptop newer than the server (3), or one so old its shape was
    # dropped (0). Its own code, so whoever reads the flag knows to update the laptop, or the server, not to look for a
    # broken document.
    assert _refusal_code("ticket", 3) == "document.version_unknown"
    assert _refusal_code("ticket", 0) == "document.version_unknown"


def test_every_type_is_listed_under_its_own_name_and_version() -> None:
    # A typo in the list, ("sale", 2) holding the clock-in's entry, would send every sale to the wrong saving code. Each
    # entry says its own name and version, and must be listed under them. The real list: empty today, so this guards
    # the first types that join it (SALE-2, ATT-1).
    for (name, schema_version), entry in DOCUMENT_TYPES.items():
        assert (entry.name, entry.schema_version) == (name, schema_version)
