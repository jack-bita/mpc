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

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.migrations.state import ProjectState
from django.db.models import Model
from django.utils import timezone

from apps.core.operations import AppendOnlyTrigger
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


def test_trigger_removed_when_migrated_back(entry: Entry) -> None:
    # Undoing the migration must take the trigger off, or stepping a database back (`migrate probe
    # 0003`) would leave a rule behind that no migration knows about. The probe's 0004 put it on; here
    # the same step runs backwards. In PostgreSQL even this change to the table sits inside the test's
    # transaction, so the rollback at the end of the test puts the trigger back for the next test.
    state = ProjectState.from_apps(apps)
    with connection.schema_editor() as editor:
        AppendOnlyTrigger("entry").database_backwards("probe", editor, state, state)

    # The same plain SQL the first test sends now goes through.
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {Entry._meta.db_table} SET amount = %s WHERE id = %s", [FIVE_THOUSAND, entry.pk])
    entry.refresh_from_db()
    assert entry.amount == FIVE_THOUSAND


def test_append_only_delete_fails(shop_a: Model, entry: Entry, voidable: VoidableEntry) -> None:
    # A bulk delete is one DELETE command: no row's own delete() runs, so Python can't refuse it.
    # Both kinds of ledger refuse it: a voidable row is voided, never deleted (T3).
    with shop_context(shop_a):
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            Entry.objects.filter(pk=entry.pk).delete()
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            VoidableEntry.objects.filter(pk=voidable.pk).delete()

    # Both rows are still there: refresh_from_db() raises DoesNotExist for a row that is gone.
    entry.refresh_from_db()
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


def test_void_cannot_change_other_columns(shop_a: Model, voidable: VoidableEntry) -> None:
    with shop_context(shop_a):
        rows = VoidableEntry.objects.filter(pk=voidable.pk)
        # Another column on its own.
        with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
            rows.update(amount=FIVE_THOUSAND)
        # Another column hidden inside a real void: the whole change is refused, the stamp too.
        with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
            rows.update(voided_at=timezone.now(), void_reason="Entered twice", amount=FIVE_THOUSAND)

    voidable.refresh_from_db()
    assert voidable.amount == FIFTY_THOUSAND
    assert voidable.voided_at is None
