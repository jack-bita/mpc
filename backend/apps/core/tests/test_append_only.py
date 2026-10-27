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

The tables are test-only (backend/tests/probe/): Entry refuses every change, VoidableEntry allows the
void stamp once. The shop and the staff member come from backend/conftest.py and are typed as plain
models: `core` may not name `Shop` or `StaffMember`, not even for types (ADR-0035).
"""

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.migrations.state import ProjectState
from django.db.models import Model
from django.utils import timezone

from apps.core import operations
from apps.core.operations import AppendOnlyTrigger, VoidStampTrigger
from apps.core.tenancy import shop_context
from tests.probe.models import Entry, VoidableEntry

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


# The fingerprint (SHA-256) of each SQL string the trigger operations run. Change one letter of a
# string and its fingerprint changes completely, so the test below notices any edit.
PINNED_SQL = {
    "APPEND_ONLY_FUNCTION": "0340ac298b44023d9aca838e0de8d56f287eb45b7a70e37a7c3196b7c598dd7e",
    "CREATE_APPEND_ONLY_TRIGGER": "a3d6154b2c9eabb5c75cc98a47e67d3941c0c445a5728e5b6e09b9f96b6bc818",
    "DROP_APPEND_ONLY_TRIGGER": "9fc2b3c6c9d2738a79f3d5104fe852869bf8fa0b76ca2108cb0aa0cb34b5159a",
    "VOID_STAMP_FUNCTION": "a5ce63eaa0496fd4a6f2de0e07f95702980b3c6c97ec253cea52df80baaaf7ae",
    "CREATE_VOID_STAMP_TRIGGER": "1db289f729890b6a1f85504395c3c58be25365611ed8edd44dfbe299405b50d1",
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
