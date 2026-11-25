"""apps/core/tests/test_append_only.py — tests for the append-only triggers (ADR-0021, 03 §5.6, T2).

A ledger keeps history: a row, once written, is never changed or deleted, and a mistake is fixed with a
new row. A payment entered twice is the one kind of row that may change: it is stamped void once (who,
when, why), and is then frozen:

    amount   voided_at   voided_by   void_reason
    50,000   —           —           —               written
    50,000   10:42       Staff A     Entered twice   voided: allowed, once
     5,000   ...                                     any other change: refused

PostgreSQL refuses these changes itself, with a trigger on each table (apps/core/operations.py), so they
fail however they are sent: Django's save(), a bulk update(), or SQL typed by hand. These tests send
them as plain SQL or as bulk update() and delete() calls: the paths no Python check sees, so only the
database can stop them.

Then the rule of a row that changes freely until one of its columns is filled, and then never again
(FrozenTrigger, WAGE-3): an attendance day, once a payslip paid it (A3).

The tables are test-only (backend/tests/probe/): Entry refuses every change, VoidableEntry allows the
void stamp once, and Note takes the frozen rule here, inside each test. The shop and the staff member
come from backend/conftest.py and are typed as plain models: `core` may not name `Shop` or
`StaffMember`, not even for types (ADR-0035).
"""

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, connection, transaction
from django.db.migrations.state import ProjectState
from django.db.models import Model
from django.utils import timezone

from apps.core import operations
from apps.core.operations import AppendOnlyTrigger, FrozenTrigger, VoidStampTrigger
from apps.core.tenancy import shop_context
from tests.probe.models import Entry, Note, VoidableEntry

pytestmark = pytest.mark.django_db

# Money is a Decimal, never a float (ADR-0024). Fake amounts only.
FIFTY_THOUSAND = Decimal("50000.00")
FIVE_THOUSAND = Decimal("5000.00")

# How to read the refusals below: `pytest.raises` expects the error and checks its message;
# `transaction.atomic()` inside it is a savepoint. Each test runs inside one transaction, and in
# PostgreSQL a failed command breaks the whole transaction: every later query would fail too. The
# savepoint rolls back only the refused command, so the test can go on and read the row afterwards.
# The error is IntegrityError: the trigger reports a broken rule, as a foreign key or a unique index does.


@pytest.fixture
def entry(shop_a: Model) -> Entry:
    # save() writes a new row (an INSERT): the one change an append-only table always allows.
    row = Entry(shop_id=shop_a.pk, amount=FIFTY_THOUSAND)
    row.save()
    return row


@pytest.fixture
def voidable(shop_a: Model) -> VoidableEntry:
    row = VoidableEntry(shop_id=shop_a.pk, amount=FIFTY_THOUSAND)
    row.save()
    return row


def test_append_only_update_fails_in_database(entry: Entry) -> None:
    # Plain SQL through a cursor: no Django model code runs, as when someone types SQL by hand or a
    # migration goes wrong. Only the database is left to refuse it. (The table's name comes from the
    # model, not from outside, so building the SQL with it is safe; the values are parameters.)
    with (
        pytest.raises(IntegrityError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f"UPDATE {Entry._meta.db_table} SET amount = %s WHERE id = %s", [FIVE_THOUSAND, entry.pk])

    # refresh_from_db() reads through Django's plain base manager, so it needs no current shop.
    entry.refresh_from_db()
    assert entry.amount == FIFTY_THOUSAND


@pytest.mark.parametrize(
    ("operation", "fixture"),
    [(AppendOnlyTrigger("entry"), "entry"), (VoidStampTrigger("voidableentry"), "voidable")],
    ids=["plain", "void"],
)
def test_trigger_removed_when_migrated_back(
    operation: AppendOnlyTrigger, fixture: str, request: pytest.FixtureRequest
) -> None:
    # Undoing the migration must take the trigger off, or stepping a database back (`migrate probe
    # 0003`) would leave a rule behind that no migration knows about. The probe's 0004 and 0005 put the
    # two triggers on; here the same steps run backwards. The void one has no undo of its own: it
    # relies on its parent's, which this proves. In PostgreSQL even this change to the table sits
    # inside the test's transaction, so the rollback at the end of the test puts the trigger back.
    row = request.getfixturevalue(fixture)
    state = ProjectState.from_apps(apps)
    with connection.schema_editor() as editor:
        operation.database_backwards("probe", editor, state, state)

    # The plain SQL the first test sends now goes through.
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {type(row)._meta.db_table} SET amount = %s WHERE id = %s", [FIVE_THOUSAND, row.pk])
    row.refresh_from_db()
    assert row.amount == FIVE_THOUSAND


def test_append_only_delete_fails(shop_a: Model, entry: Entry) -> None:
    # A bulk delete is one DELETE command: no row's own delete() runs, so Python can't refuse it.
    with shop_context(shop_a), pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        Entry.objects.filter(pk=entry.pk).delete()

    # Still there: refresh_from_db() raises DoesNotExist for a row that is gone.
    entry.refresh_from_db()


def test_void_delete_fails(shop_a: Model, voidable: VoidableEntry) -> None:
    # A voidable row is voided, never deleted (T3): the void rule refuses a DELETE as the plain one does.
    with shop_context(shop_a), pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        VoidableEntry.objects.filter(pk=voidable.pk).delete()

    voidable.refresh_from_db()


def test_void_stamp_set_once(shop_a: Model, staff_a: Model, voidable: VoidableEntry) -> None:
    with shop_context(shop_a):
        rows = VoidableEntry.objects.filter(pk=voidable.pk)
        # The first void fills the stamp: who, when, why. Allowed, even though the table has a stored
        # generated column (`applied_total`, as a payment will), which the rule must leave out.
        rows.update(voided_at=timezone.now(), voided_by=staff_a, void_reason="Entered twice")
        # A second change to the stamp would rewrite who voided it, or why. Refused.
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(void_reason="Another reason")

    voidable.refresh_from_db()
    assert voidable.voided_at is not None
    assert voidable.voided_by_id == staff_a.pk
    assert voidable.void_reason == "Entered twice"


def test_void_must_fill_voided_at(shop_a: Model, voidable: VoidableEntry) -> None:
    # Half a stamp (a reason, but no time) would leave the row open: a later update could still fill
    # `voided_at` and count as the first void. So the one allowed change must fill `voided_at`.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="must fill voided_at"),
        transaction.atomic(),
    ):
        VoidableEntry.objects.filter(pk=voidable.pk).update(void_reason="Entered twice")

    voidable.refresh_from_db()
    assert voidable.void_reason == ""


@pytest.mark.parametrize("column", ["amount", "shop", "created_at", "id"])
def test_void_cannot_change_other_columns(column: str, shop_a: Model, shop_b: Model, voidable: VoidableEntry) -> None:
    # Every column outside the stamp, not only the money: `shop` is the tenancy case (a void must never
    # move a row to another shop, T1), and `id` and `created_at` say which row it is and when it came.
    change = {
        "amount": FIVE_THOUSAND,
        "shop": shop_b,
        "created_at": timezone.now() - timedelta(days=1),
        "id": uuid.uuid7(),
    }[column]
    with shop_context(shop_a):
        rows = VoidableEntry.objects.filter(pk=voidable.pk)
        # Another column on its own.
        with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
            rows.update(**{column: change})
        # Another column hidden inside a real void: the whole change is refused, the stamp too.
        with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
            rows.update(voided_at=timezone.now(), void_reason="Entered twice", **{column: change})

    # Found by its old id, so the id didn't change either.
    voidable.refresh_from_db()
    assert voidable.amount == FIFTY_THOUSAND
    assert voidable.shop_id == shop_a.pk
    assert voidable.voided_at is None


# The frozen rule's column in these tests: Note's `created_by`, which any table of a shop has, empty or filled.
FROZEN = FrozenTrigger("note", "created_by")


def put_on(operation: AppendOnlyTrigger) -> None:
    # The rule put on the probe's table the way a migration does. A change to a table sits inside the test's transaction
    # in PostgreSQL, so the rollback at the test's end takes it off again.
    state = ProjectState.from_apps(apps)
    with connection.schema_editor() as editor:
        operation.database_forwards("probe", editor, state, state)


def test_a_row_is_frozen_once_its_column_is_filled(shop_a: Model, staff_a: Model, staff_a2: Model) -> None:
    put_on(FROZEN)
    note = Note(shop_id=shop_a.pk, text="15 Nov")
    note.save()
    with shop_context(shop_a):
        rows = Note.objects.filter(pk=note.pk)
        # Not frozen yet: it changes freely, as often as it is asked, and the column itself is filled once.
        rows.update(text="16 Nov")
        rows.update(text="17 Nov", created_by=staff_a)
        # Frozen: nothing of it changes, the column that froze it neither, emptied or pointed elsewhere; and it stays.
        for change in ({"text": "18 Nov"}, {"created_by": None}, {"created_by": staff_a2}, {"text": "17 Nov"}):
            with pytest.raises(IntegrityError, match="frozen, as its created_by_id is filled"), transaction.atomic():
                rows.update(**change)
        with pytest.raises(IntegrityError, match="DELETE on probe_note refused"), transaction.atomic():
            rows.delete()
    note.refresh_from_db()
    assert (note.text, note.created_by_id) == ("17 Nov", staff_a.pk)


def test_one_frozen_row_freezes_no_other(shop_a: Model, staff_a: Model) -> None:
    # Juma's day paid, Asha's still open: hers is worked out again as before.
    put_on(FROZEN)
    with shop_context(shop_a):
        Note(shop_id=shop_a.pk, text="Juma", created_by_id=staff_a.pk).save()
        Note(shop_id=shop_a.pk, text="Asha").save()
        Note.objects.filter(created_by__isnull=True).update(text="Asha, tena")
        assert set(Note.objects.values_list("text", flat=True)) == {"Juma", "Asha, tena"}


def test_the_frozen_rule_is_removed_when_migrated_back(shop_a: Model, staff_a: Model) -> None:
    put_on(FROZEN)
    note = Note(shop_id=shop_a.pk, text="15 Nov", created_by_id=staff_a.pk)
    note.save()
    state = ProjectState.from_apps(apps)
    with connection.schema_editor() as editor:
        FROZEN.database_backwards("probe", editor, state, state)
    with shop_context(shop_a):
        Note.objects.filter(pk=note.pk).update(text="16 Nov")
    note.refresh_from_db()
    assert note.text == "16 Nov"


def test_a_rule_for_a_column_there_is_not_is_refused() -> None:
    # A slip of the field's name in a migration stops the migration, never leaves a table unguarded without a word.
    with pytest.raises(FieldDoesNotExist):
        put_on(FrozenTrigger("note", "payslp"))


def test_the_frozen_step_says_what_it_does() -> None:
    # What `migrate` prints for the step, and what Django writes again when it squashes migrations.
    assert FROZEN.describe() == "Frozen trigger on note, once created_by is filled"
    assert FROZEN.deconstruct() == ("FrozenTrigger", ("note", "created_by"), {})


# The fingerprint (SHA-256) of each SQL string the trigger operations run. Change one letter of a
# string and its fingerprint changes completely, so the test below notices any edit.
PINNED_SQL = {
    "APPEND_ONLY_FUNCTION": "0340ac298b44023d9aca838e0de8d56f287eb45b7a70e37a7c3196b7c598dd7e",
    "CREATE_APPEND_ONLY_TRIGGER": "a3d6154b2c9eabb5c75cc98a47e67d3941c0c445a5728e5b6e09b9f96b6bc818",
    "DROP_APPEND_ONLY_TRIGGER": "9fc2b3c6c9d2738a79f3d5104fe852869bf8fa0b76ca2108cb0aa0cb34b5159a",
    "VOID_STAMP_FUNCTION": "a5ce63eaa0496fd4a6f2de0e07f95702980b3c6c97ec253cea52df80baaaf7ae",
    "CREATE_VOID_STAMP_TRIGGER": "1db289f729890b6a1f85504395c3c58be25365611ed8edd44dfbe299405b50d1",
    # The no-delete rule (ATT-8), pinned from its first commit, as it will be on main.
    "NO_DELETE_FUNCTION": "73bbabae636007491a8c3699743ebaddd07ac7bb42b42b51cbe1da856da63920",
    "CREATE_NO_DELETE_TRIGGER": "731674a8b287461b7dcb60dc91f7489729de7f04325d7fcc810ee57b9a6bd25a",
    "DROP_NO_DELETE_TRIGGER": "7d427992556072253e007b53965a7a83587b73e1ee3f171af2fbb1148bb36399",
    # The frozen rule (WAGE-3), pinned from its first commit too.
    "FROZEN_FUNCTION": "742e5771e5b86f3f6eb8f6500b37b85e7c115f03c480cae31e8f36899e96d33d",
    "CREATE_FROZEN_TRIGGER": "c1d08fa02bbd31c8568b3508c842c62bbf94fd20358a21856b00b512fbeb9028",
    "DROP_FROZEN_TRIGGER": "31865397cb41ee79d7b6f50c8229b33fa0cf63c5f3b95c2696db09df79fa1699",
}


@pytest.mark.parametrize(("name", "fingerprint"), PINNED_SQL.items())
def test_trigger_sql_never_changes_once_on_main(name: str, fingerprint: str) -> None:
    # Rule 9: a migration on main is never edited. Every ledger's migration calls these strings, so
    # editing one would edit those migrations from the outside: a fresh database (CI, a new shop) would
    # get the new rule, a live one would keep the old, and the next ledger's migration would swap it on
    # every table at once. A change is a new rule instead: a new function name (core_append_only_v2),
    # new strings and new migrations, while these stay, pinned (apps/core/operations.py says so too).
    sql = getattr(operations, name)
    assert hashlib.sha256(sql.encode()).hexdigest() == fingerprint, (
        f"{name} was edited. Migrations on main run it, so don't edit it: write a new rule "
        "(a new function name and new migrations) instead (rule 9, ADR-0021)."
    )
