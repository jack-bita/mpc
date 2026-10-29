"""apps/control/tests/test_edit_history.py — tests for the audit trail's second book: every change to an office
record, written by PostgreSQL itself (03 §5.16, ADR-0036).

After every UPDATE of an office table, a trigger writes one EditEvent with who changed what:

    when          who       row         before            after
    29 Oct 11:02  Staff A   a note      text: "Dawa"      text: "Dawa za Mifugo"

The test-only probe Note has the trigger (its migration lists RecordEdits), so these tests edit notes; the real
office tables switch theirs on in their own migrations, and backend/tests/test_edit_history.py checks that every
one does. Who acts comes from the visit (apps/core/acting.py), opened here with acting_as() as a visit opens it.
`control` may not import `people` (ADR-0035), so the staff come from backend/conftest.py, typed as Actors. Fake
data only: the repo is public (03 §10).
"""

import hashlib

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.migrations.state import ProjectState
from django.db.models import Model

from apps.control import operations
from apps.control.models import EditEvent
from apps.control.operations import RecordEdits
from apps.core.acting import acting_as
from apps.core.links import LINK_TYPES
from apps.core.models import AppendOnlyError
from apps.core.tenancy import Actor, shop_context
from tests.probe.models import Note

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def note_has_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    # The probe's code, for loading a history row's subject; the trigger has its own copy, from the migration.
    monkeypatch.setitem(LINK_TYPES, "probe_note", "probe.Note")


@pytest.fixture
def note(shop_a: Model) -> Note:
    note = Note(shop_id=shop_a.pk, text="Dawa")
    note.save()
    return note


def history_of(row: Note) -> list[EditEvent]:
    # A row's history, oldest first: ids are UUIDv7, which follow the order they were made in (ADR-0007).
    return list(EditEvent.objects.filter(subject_type="probe_note", subject_id=row.pk).order_by("id"))


def test_edit_recorded_with_person_and_changes(shop_a: Model, note: Note, staff_a: Actor) -> None:
    with shop_context(shop_a), acting_as(staff_a):
        note.text = "Dawa za Mifugo"
        note.save()
        [edit] = history_of(note)
        # Who and when, the row, and only what changed: the note's id, shop and creation stayed as they were.
        assert (edit.shop_id, edit.created_by_id) == (shop_a.pk, staff_a.staff_id)
        assert edit.created_at is not None
        assert (edit.before, edit.after) == ({"text": "Dawa"}, {"text": "Dawa za Mifugo"})
        assert edit.subject == note

        # A bulk update() skips every model method and every service, and still leaves its row: the trigger is
        # in the database, so no code path can skip it.
        Note.objects.filter(pk=note.pk).update(text="Dawa ya Kuku")
        assert [(edit.before, edit.after) for edit in history_of(note)] == [
            ({"text": "Dawa"}, {"text": "Dawa za Mifugo"}),
            ({"text": "Dawa za Mifugo"}, {"text": "Dawa ya Kuku"}),
        ]


def test_edit_outside_a_visit_names_nobody(shop_a: Model, note: Note) -> None:
    # A nightly job or the seed opens no visit, so nobody is named: the system acted, as an empty `created_by`
    # means on every shop row (02 §1).
    with shop_context(shop_a):
        Note.objects.filter(pk=note.pk).update(text="Dawa za Mifugo")
        [edit] = history_of(note)
        assert edit.created_by_id is None


def test_edit_that_changes_nothing_writes_no_history(shop_a: Model, note: Note, staff_a: Actor) -> None:
    # A save with nothing new, and an update() that finds no row, change nothing the owner could see.
    with shop_context(shop_a), acting_as(staff_a):
        note.save()
        Note.objects.filter(pk=note.pk).update(text="Dawa")
        Note.objects.filter(text="Hakuna").update(text="Bado hakuna")
        assert not EditEvent.objects.exists()


def test_history_rows_append_only(shop_a: Model, note: Note) -> None:
    # T2: a history row is never changed or deleted, in Python or in PostgreSQL (ADR-0021). And only the trigger
    # writes one: a row saved from Python, even a new one, would be a change nobody made.
    with shop_context(shop_a):
        Note.objects.filter(pk=note.pk).update(text="Dawa za Mifugo")
        [edit] = history_of(note)

    edit.after = {"text": "Kitu kingine"}
    with pytest.raises(AppendOnlyError):
        edit.save()
    with pytest.raises(AppendOnlyError):
        edit.delete()
    made_up = EditEvent(shop_id=note.shop_id, subject_type="probe_note", subject_id=note.pk, before={}, after={})
    with pytest.raises(AppendOnlyError, match="trigger"):
        made_up.save()
    # Plain SQL, which no model code sees: only the trigger is left to refuse it. (The table's name comes from the
    # model, not from outside, so building the SQL with it is safe; the values are parameters.)
    table = EditEvent._meta.db_table
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET after = %s WHERE id = %s", ['{"text": "Kitu kingine"}', edit.pk])
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", [edit.pk])

    edit.refresh_from_db()
    assert edit.after == {"text": "Dawa za Mifugo"}


def test_edit_trigger_removed_when_migrated_back(shop_a: Model, note: Note) -> None:
    # Undoing the migration must take the trigger off, or stepping a database back would leave a rule behind that
    # no migration knows about. In PostgreSQL even this change sits inside the test's transaction, so the rollback
    # at the end of the test puts the trigger back (as in test_flag_trigger.py).
    state = ProjectState.from_apps(apps)
    with connection.schema_editor() as editor:
        RecordEdits("note", type_code="probe_note").database_backwards("probe", editor, state, state)

    with shop_context(shop_a):
        Note.objects.filter(pk=note.pk).update(text="Dawa za Mifugo")
        assert not EditEvent.objects.exists()


def test_record_edits_checks_its_names() -> None:
    # A type code of the wrong shape would break EditEvent's own rule on every edit of the table, so every edit
    # would fail: the step refuses it as the migration is read. A column's name goes into the SQL too.
    with pytest.raises(ValueError, match="type code"):
        RecordEdits("note", type_code="Probe Note")
    with pytest.raises(ValueError, match="column"):
        RecordEdits("note", type_code="probe_note", skip=["pin_hash'; DROP TABLE probe_note; --"])


# Each SQL string of the rule, by its SHA-256 fingerprint, taken when the rule was written.
PINNED_SQL = {
    "RECORD_EDIT_FUNCTION": "13f3ceb57434ade1a1f055b2261b20668050fc26b82b2e8652b9016908ed04dd",
    "CREATE_RECORD_EDITS_TRIGGER": "3dabe4bacd3ea9c135e1e48a20030d74fe423948eed49e2d9bd1f9e5446aaa8e",
    "DROP_RECORD_EDITS_TRIGGER": "bcf9a1bf65eb27df33203fec7a0c45364b1379a3cc481273dd0ac381e2d59a9d",
}


@pytest.mark.parametrize(("name", "fingerprint"), PINNED_SQL.items())
def test_edit_trigger_sql_never_changes_once_on_main(name: str, fingerprint: str) -> None:
    # Rule 9: a migration on main is never edited. Every office table's migration runs these strings, so editing one
    # would edit those migrations from the outside: a fresh database would get the new rule, a live one would keep
    # the old. A change is a new rule instead (control_record_edit_v2), as AUTH-4's device will be.
    sql = getattr(operations, name)
    assert hashlib.sha256(sql.encode()).hexdigest() == fingerprint, (
        f"{name} was edited. Every office table's migration runs it, so don't edit it: write a new rule "
        "(a new function name and new migrations) instead (rule 9, ADR-0036)."
    )
