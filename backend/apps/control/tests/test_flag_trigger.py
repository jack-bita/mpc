"""apps/control/tests/test_flag_trigger.py — tests for the flag table's trigger: PostgreSQL keeps a flag's facts
as they were raised, and lets its status move forward only (02 §13, apps/control/operations.py).

The services keep both rules (test_flags.py), but a bug, a bulk update() or SQL typed by hand would go
straight past them. These tests send exactly that, so only the database is left to refuse:

    open ──▶ explained ──▶ resolved | dismissed      ✓ forward
    resolved ──▶ open,  explained ──▶ open           ✗ back
    kind, numbers, subject, side, shop, who raised   ✗ never change

The subject is the test-only probe Note, as in test_flags.py; the shops come from backend/conftest.py.
"""

import hashlib

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.migrations.state import ProjectState
from django.db.models import Model

from apps.control import operations
from apps.control.models import Flag, FlagKind, FlagStatus
from apps.control.operations import FlagForwardOnlyTrigger
from apps.control.services import raise_flag
from apps.core.links import LINK_TYPES
from apps.core.tenancy import shop_context
from tests.probe.models import Note

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def note_has_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(LINK_TYPES, "probe_note", "probe.Note")


@pytest.fixture
def flag(shop_a: Model) -> Flag:
    # A flag with no people and no notes, so that only the trigger stands in a DELETE's way: a flag with
    # either is also kept by PROTECT on their links.
    note = Note(shop_id=shop_a.pk, text="Droo ya Dawa, 28 Oct")
    note.save()
    with shop_context(shop_a):
        return raise_flag(kind=FlagKind.DUPLICATE_CODE, subject=note, by=None)


def set_status(flag: Flag, status: str) -> None:
    # One bulk update(), which skips every model method and every service check, as a bug or a quick fix
    # in a shell would.
    Flag.objects.filter(pk=flag.pk).update(status=status)


def test_flag_status_moves_forward_only_in_database(shop_a: Model, flag: Flag) -> None:
    with shop_context(shop_a):
        # Forward is allowed, here straight from open, as the services allow (02 v1.8).
        set_status(flag, FlagStatus.EXPLAINED)
        # Back is not, from explained...
        with pytest.raises(IntegrityError, match="forward only"), transaction.atomic():
            set_status(flag, FlagStatus.OPEN)
        set_status(flag, FlagStatus.RESOLVED)
        # ...nor from a closed flag, to any status at all.
        for status in (FlagStatus.OPEN, FlagStatus.EXPLAINED, FlagStatus.DISMISSED):
            with pytest.raises(IntegrityError, match="forward only"), transaction.atomic():
                set_status(flag, status)

    flag.refresh_from_db()
    assert flag.status == FlagStatus.RESOLVED


def test_flag_facts_never_change_in_database(shop_a: Model, flag: Flag) -> None:
    # A flag says what was found when it was raised. Changing its kind or its numbers afterwards would
    # rewrite history (T2), as editing a ledger row would.
    with shop_context(shop_a):
        for change in ({"kind": FlagKind.CASH_DIFFERENCE}, {"subject_type": "probe_entry"}):
            with pytest.raises(IntegrityError, match="only a flag's status"), transaction.atomic():
                Flag.objects.filter(pk=flag.pk).update(**change)

    flag.refresh_from_db()
    assert (flag.kind, flag.subject_type) == (FlagKind.DUPLICATE_CODE, "probe_note")


def test_flag_never_deleted_in_database(flag: Flag) -> None:
    # Plain SQL, which no model code sees (T3: nothing is deleted).
    with (
        pytest.raises(IntegrityError, match="never deleted"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f"DELETE FROM {Flag._meta.db_table} WHERE id = %s", [flag.pk])

    # Still there: refresh_from_db() raises DoesNotExist for a row that is gone.
    flag.refresh_from_db()


def test_flag_trigger_removed_when_migrated_back(shop_a: Model, flag: Flag) -> None:
    # Undoing the migration must take the trigger off, or stepping a database back would leave a rule behind
    # that no migration knows about. In PostgreSQL even this change sits inside the test's transaction, so
    # the rollback at the end of the test puts the trigger back (as in apps/core/tests/test_append_only.py).
    state = ProjectState.from_apps(apps)
    with connection.schema_editor() as editor:
        FlagForwardOnlyTrigger("flag").database_backwards("control", editor, state, state)

    # The move back the first test refuses now goes through.
    with shop_context(shop_a):
        set_status(flag, FlagStatus.RESOLVED)
        set_status(flag, FlagStatus.OPEN)
    flag.refresh_from_db()
    assert flag.status == FlagStatus.OPEN


# Each SQL string of the rule, by its SHA-256 fingerprint, taken when the rule was written.
PINNED_SQL = {
    "FLAG_FORWARD_ONLY_FUNCTION": "809ffcb1fa96a21e5d99f0c4bc7a8cae24b40c7a4ede5071c64790f96344e9e0",
    "CREATE_FLAG_FORWARD_ONLY_TRIGGER": "65a8eee2a87203a9aaf2a8ecf58bbe1adbc9da44df7b925a326b934ddd38a333",
    "DROP_FLAG_FORWARD_ONLY_TRIGGER": "114cbce8789747064431b71cc602eee1ce4e82e6deeeab0334430b5bf954e357",
}


@pytest.mark.parametrize(("name", "fingerprint"), PINNED_SQL.items())
def test_flag_trigger_sql_never_changes_once_on_main(name: str, fingerprint: str) -> None:
    # Rule 9: a migration on main is never edited. The flag table's migration runs these strings, so editing
    # one would edit that migration from the outside: a fresh database would get the new rule, a live one
    # would keep the old. A change is a new rule instead (control_flag_forward_only_v2), as for core's.
    sql = getattr(operations, name)
    assert hashlib.sha256(sql.encode()).hexdigest() == fingerprint, (
        f"{name} was edited. The flag table's migration runs it, so don't edit it: write a new rule "
        "(a new function name and a new migration) instead (rule 9, ADR-0021)."
    )
