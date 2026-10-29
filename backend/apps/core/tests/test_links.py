"""apps/core/tests/test_links.py — tests for generic links: a row named by a short type code and its UUID
(apps/core/links.py, 03 §5.1).

    code         table        row
    probe_note   probe.Note   0199…  ← stored on a flag as ("probe_note", 0199…), loaded back from both

No real table has a code yet: each card adds the tables its links point at. So these tests give one to the
test-only probe Note (backend/tests/probe/), for the length of each test: `core` may not import a higher app's
table to test with (ADR-0035). The shops come from backend/conftest.py, typed as plain models.
"""

import uuid
from decimal import Decimal

import pytest
from django.db.models import Model

from apps.core.links import LINK_TYPES, UnknownLinkType, link_type_of, load_link
from apps.core.tenancy import NoShopSelected, shop_context
from tests.probe.models import Entry, Note

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def note_has_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    # monkeypatch puts the list back as it was after each test, so the code never reaches the real list.
    monkeypatch.setitem(LINK_TYPES, "probe_note", "probe.Note")


def test_row_named_by_its_type_code(shop_a: Model) -> None:
    note = Note(shop_id=shop_a.pk, text="Customer A")

    assert link_type_of(note) == "probe_note"


def test_link_loads_its_row_inside_its_shop(shop_a: Model, shop_b: Model) -> None:
    note = Note(shop_id=shop_a.pk, text="Customer A")
    note.save()

    with shop_context(shop_a):
        assert load_link("probe_note", note.pk) == note
    # Another shop's visit can't load it: the link reads through the guard, so the row is "not found", exactly
    # as an id no shop has (03 §5.4).
    with shop_context(shop_b), pytest.raises(Note.DoesNotExist):
        load_link("probe_note", note.pk)
    with shop_context(shop_a), pytest.raises(Note.DoesNotExist):
        load_link("probe_note", uuid.uuid7())
    # And with no shop open, nothing is read at all (CORE-2).
    with pytest.raises(NoShopSelected):
        load_link("probe_note", note.pk)


def test_table_without_type_code_refused(shop_a: Model, monkeypatch: pytest.MonkeyPatch) -> None:
    # A probe ledger row, whose table has no code: a link to it could not be stored.
    entry = Entry(shop_id=shop_a.pk, amount=Decimal("1000.00"))
    with pytest.raises(UnknownLinkType, match="no type code"):
        link_type_of(entry)
    # A code the list doesn't hold names nothing.
    with pytest.raises(UnknownLinkType, match="not a type code"):
        load_link("probe_entry", uuid.uuid7())
    # Two codes for one table: the same row could be stored two ways.
    monkeypatch.setitem(LINK_TYPES, "probe_note_again", "probe.Note")
    with pytest.raises(UnknownLinkType, match="two type codes"):
        link_type_of(Note(shop_id=shop_a.pk, text="Customer A"))


@pytest.mark.parametrize(
    "table",
    [
        # A person, who belongs to no one shop (02 §5): no guard, so a link could read anyone.
        "people.User",
        # A table that doesn't exist, such as a typo.
        "probe.Missing",
        # Text that isn't "app.Model" at all.
        "Note",
    ],
)
def test_type_code_must_name_a_shop_table(table: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(LINK_TYPES, "wrong", table)

    # Refused before any read, so no shop needs to be open.
    with pytest.raises(UnknownLinkType):
        load_link("wrong", uuid.uuid7())
