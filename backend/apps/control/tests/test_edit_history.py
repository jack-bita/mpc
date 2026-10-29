"""apps/control/tests/test_edit_history.py — tests for the audit trail's second book: every change to an office
record, written by PostgreSQL itself (03 §5.16, ADR-0036).

After every UPDATE of an office table, a trigger writes one EditEvent with who changed what:

    when          who       row         before            after
    29 Oct 11:02  Staff A   a card      name: "Dawa"      name: "Dawa za Mifugo"

The test-only probe Card stands for an office record and has the trigger (its migration lists RecordEdits), so
these tests edit cards; the real office tables switch theirs on in their own migrations, and
backend/tests/test_edit_history.py checks that every one does. Who acts comes from the visit
(apps/core/acting.py), opened here with acting_as() as a visit opens it. `control` may not import `people`
(ADR-0035), so the staff come from backend/conftest.py, typed as Actors. Fake data only: the repo is public
(03 §10).
"""

import hashlib

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.migrations.state import ProjectState
from django.db.models import Model

from apps.control import operations
from apps.control.models import EditEvent
from apps.control.operations import EditsByTriggerOnly, RecordEdits
from apps.core.acting import acting_as
from apps.core.links import LINK_TYPES
from apps.core.models import AppendOnlyError
from apps.core.tenancy import Actor, shop_context
from tests.probe.models import Card

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def card_has_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    # The probe's code, for loading a history row's subject; the trigger has its own copy, from the migration.
    monkeypatch.setitem(LINK_TYPES, "probe_card", "probe.Card")


@pytest.fixture
def card(shop_a: Model) -> Card:
    card = Card(shop_id=shop_a.pk, name="Dawa")
    card.save()
    return card


def history_of(row: Card) -> list[EditEvent]:
    # A row's history, oldest first: ids are UUIDv7, which follow the order they were made in (ADR-0007).
    return list(EditEvent.objects.filter(subject_type="probe_card", subject_id=row.pk).order_by("id"))


def test_edit_recorded_with_person_and_changes(shop_a: Model, card: Card, staff_a: Actor) -> None:
    with shop_context(shop_a), acting_as(staff_a):
        card.name = "Dawa za Mifugo"
        card.save()
        [edit] = history_of(card)
        # Who and when, the row, and only what changed: the card's id, shop and creation stayed as they were.
        assert (edit.shop_id, edit.created_by_id) == (shop_a.pk, staff_a.staff_id)
        assert edit.created_at is not None
        assert (edit.before, edit.after) == ({"name": "Dawa"}, {"name": "Dawa za Mifugo"})
        assert edit.subject == card

        # A bulk update() skips every model method and every service, and still leaves its row: the trigger is
        # in the database, so no code path can skip it.
        Card.objects.filter(pk=card.pk).update(name="Dawa ya Kuku")
        assert [(edit.before, edit.after) for edit in history_of(card)] == [
            ({"name": "Dawa"}, {"name": "Dawa za Mifugo"}),
            ({"name": "Dawa za Mifugo"}, {"name": "Dawa ya Kuku"}),
        ]


def test_each_edit_keeps_its_own_time(shop_a: Model, card: Card, staff_a: Actor) -> None:
    # The owner's trail (CTRL-5) shows a row's edits in the order they happened, by their time. Two edits in one
    # transaction, as editing() and the staff services make, must get two times, the second after the first;
    # the transaction's start time would give both the same one, and an edit that waited for a lock an earlier
    # time than the edit it waited for.
    with shop_context(shop_a), acting_as(staff_a), transaction.atomic():
        Card.objects.filter(pk=card.pk).update(name="Dawa za Mifugo")
        Card.objects.filter(pk=card.pk).update(name="Dawa ya Kuku")
        first, second = history_of(card)
    assert first.created_at < second.created_at


def test_edit_of_another_shops_row_refused(shop_b: Model, staff_a: Actor) -> None:
    # T1: a visit works for one shop (03 §5.4). If a bug let shop A's visit change shop B's row, the history row,
    # written in shop B, would name shop A's staff member, and shop B's trail would load that person. So the trigger
    # compares the edited row's shop with the shop the visit told PostgreSQL, and refuses the edit itself: the
    # database is the last guard (03 §5.6).
    their_card = Card(shop_id=shop_b.pk, name="Pembejeo")
    their_card.save()
    with shop_context(shop_b), acting_as(staff_a):
        with pytest.raises(IntegrityError, match="another shop"), transaction.atomic():
            Card.objects.filter(pk=their_card.pk).update(name="Imeibiwa")
        assert Card.objects.get(pk=their_card.pk).name == "Pembejeo"
        assert not EditEvent.objects.exists()


def test_edit_outside_a_visit_names_nobody(shop_a: Model, card: Card) -> None:
    # A nightly job or the seed opens no visit, so nobody is named: the system acted, as an empty `created_by`
    # means on every shop row (02 §1).
    with shop_context(shop_a):
        Card.objects.filter(pk=card.pk).update(name="Dawa za Mifugo")
        [edit] = history_of(card)
        assert edit.created_by_id is None


def test_edit_that_changes_nothing_writes_no_history(shop_a: Model, card: Card, staff_a: Actor) -> None:
    # A save with nothing new, and an update() that finds no row, change nothing the owner could see.
    with shop_context(shop_a), acting_as(staff_a):
        card.save()
        Card.objects.filter(pk=card.pk).update(name="Dawa")
        Card.objects.filter(name="Hakuna").update(name="Bado hakuna")
        assert not EditEvent.objects.exists()


def test_history_rows_append_only(shop_a: Model, card: Card) -> None:
    # T2: a history row is never changed or deleted, in Python or in PostgreSQL (ADR-0021). And only the trigger
    # writes one: a row saved from Python, even a new one, would be a change nobody made.
    with shop_context(shop_a):
        Card.objects.filter(pk=card.pk).update(name="Dawa za Mifugo")
        [edit] = history_of(card)

    edit.after = {"name": "Kitu kingine"}
    with pytest.raises(AppendOnlyError):
        edit.save()
    with pytest.raises(AppendOnlyError):
        edit.delete()
    made_up = EditEvent(shop_id=card.shop_id, subject_type="probe_card", subject_id=card.pk, before={}, after={})
    with pytest.raises(AppendOnlyError, match="trigger"):
        made_up.save()
    # Plain SQL, which no model code sees: only the trigger is left to refuse it. (The table's name comes from the
    # model, not from outside, so building the SQL with it is safe; the values are parameters.)
    table = EditEvent._meta.db_table
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET after = %s WHERE id = %s", ['{"name": "Kitu kingine"}', edit.pk])
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", [edit.pk])

    edit.refresh_from_db()
    assert edit.after == {"name": "Dawa za Mifugo"}


def test_only_the_trigger_writes_history(shop_a: Model, card: Card, staff_a: Actor) -> None:
    # save() refuses a made-up row (above), but two ways skip save(): bulk_create, and SQL typed by hand. A history
    # row that nobody's edit wrote, naming Staff A, would be a lie in the owner's trail (ADR-0036). So PostgreSQL
    # refuses every INSERT that doesn't come from the edit history's own trigger.
    made_up = EditEvent(
        shop_id=card.shop_id,
        subject_type="probe_card",
        subject_id=card.pk,
        before={"name": "Dawa"},
        after={"name": "Kitu kingine"},
        created_by_id=staff_a.staff_id,
    )
    table = EditEvent._meta.db_table
    with shop_context(shop_a):
        with pytest.raises(IntegrityError, match="only the edit history's trigger"), transaction.atomic():
            EditEvent.objects.bulk_create([made_up])
        with (
            pytest.raises(IntegrityError, match="only the edit history's trigger"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                f"INSERT INTO {table} (id, shop_id, created_at, subject_type, subject_id, before, after) "
                "VALUES (uuidv7(), %s, now(), 'probe_card', %s, '{}', '{}')",
                [card.shop_id, card.pk],
            )
        assert not EditEvent.objects.exists()

        # The trigger itself still writes: a real edit leaves its row.
        Card.objects.filter(pk=card.pk).update(name="Dawa za Mifugo")
        assert EditEvent.objects.count() == 1


def test_edit_trigger_removed_when_migrated_back(shop_a: Model, card: Card) -> None:
    # Undoing a migration must take its trigger off, or stepping a database back would leave a rule behind that no
    # migration knows about. In PostgreSQL even this change sits inside the test's transaction, so the rollback at
    # the end of the test puts the triggers back (as in test_flag_trigger.py).
    state = ProjectState.from_apps(apps)
    with connection.schema_editor() as editor:
        RecordEdits("card", type_code="probe_card").database_backwards("probe", editor, state, state)
        EditsByTriggerOnly("editevent").database_backwards("control", editor, state, state)

    with shop_context(shop_a):
        # The card's trigger is off: an edit writes nothing.
        Card.objects.filter(pk=card.pk).update(name="Dawa za Mifugo")
        assert not EditEvent.objects.exists()
        # The history's guard is off: a row bulk_create sends goes in.
        EditEvent.objects.bulk_create(
            [EditEvent(shop_id=card.shop_id, subject_type="probe_card", subject_id=card.pk, before={}, after={})]
        )
        assert EditEvent.objects.count() == 1


def test_record_edits_checks_its_names() -> None:
    # A type code of the wrong shape would break EditEvent's own rule on every edit of the table, so every edit
    # would fail: the step refuses it as the migration is read. A column's name goes into the SQL too.
    with pytest.raises(ValueError, match="type code"):
        RecordEdits("card", type_code="Probe Card")
    with pytest.raises(ValueError, match="column"):
        RecordEdits("card", type_code="probe_card", skip=["pin_hash'; DROP TABLE probe_card; --"])


# Each SQL string of the rule, by its SHA-256 fingerprint, taken when the rule was written.
PINNED_SQL = {
    "RECORD_EDIT_FUNCTION": "f304792db801aed85c04f1c6a9fec126232fb3c090c09929cde2540e868d25a9",
    "CREATE_RECORD_EDITS_TRIGGER": "3dabe4bacd3ea9c135e1e48a20030d74fe423948eed49e2d9bd1f9e5446aaa8e",
    "DROP_RECORD_EDITS_TRIGGER": "bcf9a1bf65eb27df33203fec7a0c45364b1379a3cc481273dd0ac381e2d59a9d",
    "EDITS_BY_TRIGGER_ONLY_FUNCTION": "d7550bb29e00e98194c0c6d4f59ce12fbab1d3c3765c14473836adcc721be4c0",
    "CREATE_EDITS_BY_TRIGGER_ONLY_TRIGGER": "952c35c87f01c56dc67006f73666ac00f370898694638b974a50adea951fd9ef",
    "DROP_EDITS_BY_TRIGGER_ONLY_TRIGGER": "2887133fdc07dc1f30a5cf4a969f6260806fab33ad0a764352161ead73675341",
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
