"""backend/tests/test_edit_history.py — every office table keeps the history of its edits (03 §5.16, ADR-0036).

An office table is a shop table people change: every table built on ShopScoped that is not a ledger (AppendOnly,
whose rows never change). Today: sides, payment accounts, stock locations and staff members' jobs. Each must carry
the trigger that writes control.EditEvent, put there by RecordEdits in its migration (apps/control/operations.py):
switched on, and recording the table's own type code from apps/core/links.py, so its history rows load back. The
few that keep their history another way are listed, each with its reason, in NO_EDIT_HISTORY
(backend/tests/sweep_lists.py), which changes only by a decision written on a card.

This module asks Django for those tables itself, as the tenancy sweep does (test_tenancy_sweep.py), so a new
office table that forgets (products, contacts, roles, devices) turns CI red with no change here. The check is a
function that returns what breaks the rule, and the check's own test hands it probe tables built to break it. It
lives outside `apps` because it names tables of several apps (ADR-0035).
"""

import re
from collections.abc import Iterable

import pytest
from django.apps import apps
from django.db import connection, models

from apps.core.links import LINK_TYPES
from apps.core.models import AppendOnly, ShopScoped
from apps.people.models import StaffMember
from tests.probe.models import Card, Note
from tests.sweep_lists import NO_EDIT_HISTORY

pytestmark = pytest.mark.django_db


def changeable_tables() -> list[type[models.Model]]:
    # Every shop table of our apps (backend/apps/; the test-only probe app is not one) whose rows can change: built
    # on ShopScoped, and not a ledger. Editable tables are among them, and so are older ones like StaffMember.
    return [
        table
        for table in apps.get_models()
        if table._meta.app_config.name.startswith("apps.")
        and issubclass(table, ShopScoped)
        and not issubclass(table, AppendOnly)
    ]


def office_tables() -> list[type[models.Model]]:
    # The ones that must keep an edit history: all of them, but the few listed with their reason.
    return [table for table in changeable_tables() if table._meta.label not in NO_EDIT_HISTORY]


# The function every office table's trigger runs (apps/control/operations.py). When AUTH-4 moves the tables to
# control_record_edit_v2(), for the device, this name moves with them, and the check finds any table left behind.
RECORD_EDIT_FUNCTION = "control_record_edit"

# How PostgreSQL stores when a trigger runs (`tgtype`), as bits added up: 1 = FOR EACH ROW, 2 = BEFORE (none =
# AFTER), 4 = INSERT, 8 = DELETE, 16 = UPDATE. The history's trigger is AFTER UPDATE FOR EACH ROW: 1 + 16. AFTER,
# because only an edit PostgreSQL has kept is written down; BEFORE could record an edit a later rule refuses.
AFTER_UPDATE_FOR_EACH_ROW = 1 + 16

# Column names that hold a secret: a PIN's hash today, and later a device's key (AUTH-1, AUTH-2), a password or a
# token, as a whole word of the name (`pin_hash`, `key_hash`, `api_token`, never `monkey`). Such a column must be on
# its table's skip list (RecordEdits(..., skip=[...])): a secret copied into the history could be read by anyone who
# reads the trail. A table's skip list is frozen in its trigger, so a secret column added later needs a new migration
# that rebuilds the trigger; this check says so the day the column is added.
SECRET_COLUMN = re.compile(r"(^|_)(hash|key|secret|password|token)(_|$)")


def skipped_columns(words: bytes) -> set[str]:
    # The trigger's second word: its skip list, as PostgreSQL writes an array of text, "{pin_hash}" ("{}" for none).
    parts = bytes(words).split(b"\x00")
    if len(parts) < 2:
        return set()
    return {name for name in parts[1].decode().strip("{}").split(",") if name}


def history_problems(tables: Iterable[type[models.Model]]) -> list[str]:
    # PostgreSQL's own list of triggers (pg_trigger) says, for each table, whether it has `record_edits`, whether it
    # is switched on (`tgenabled`: O or A fire in every session; D is off; R fires only on a copy of the database),
    # when it runs (`tgtype`), which function it runs (`tgfoid`, named in pg_proc, PostgreSQL's list of functions),
    # and the words it was given (`tgargs`: each one ends with a zero byte), the first of which is the type code.
    problems = []
    with connection.cursor() as cursor:
        for table in tables:
            label = table._meta.label
            cursor.execute(
                "SELECT t.tgargs, t.tgenabled, t.tgtype, p.proname FROM pg_trigger t "
                "JOIN pg_proc p ON p.oid = t.tgfoid WHERE t.tgrelid = %s::regclass AND t.tgname = 'record_edits'",
                [table._meta.db_table],
            )
            row = cursor.fetchone()
            if row is None:
                problems.append(f"{label}: no edit history trigger")
                continue
            words, enabled, timing, function = row
            if enabled not in ("O", "A"):
                problems.append(f"{label}: its edit history trigger is switched off")
            if function != RECORD_EDIT_FUNCTION:
                problems.append(f"{label}: its edit history trigger runs {function}(), not {RECORD_EDIT_FUNCTION}()")
            if timing != AFTER_UPDATE_FOR_EACH_ROW:
                problems.append(f"{label}: its edit history trigger is not AFTER UPDATE FOR EACH ROW")
            code = bytes(words).split(b"\x00")[0].decode()
            codes = [listed for listed, named in LINK_TYPES.items() if named == label]
            if codes != [code]:
                problems.append(f"{label}: its trigger records {code!r}, but LINK_TYPES gives {codes}")
            skipped = skipped_columns(words)
            for field in table._meta.concrete_fields:
                # Every concrete field has a column; Django's type stubs allow None.
                column = field.column or ""
                if SECRET_COLUMN.search(column) and column not in skipped:
                    problems.append(f"{label}: its trigger would copy {column} into the history")
    return problems


def test_every_office_table_records_its_edits() -> None:
    tables = office_tables()
    # Not looking at nothing: these are office tables today.
    assert {"shops.Side", "shops.PaymentAccount", "shops.StockLocation", "people.StaffMember"} <= {
        table._meta.label for table in tables
    }
    assert history_problems(tables) == []
    # And no table is listed that isn't a changeable shop table any more: a stale entry would let a new one in unseen.
    assert set(NO_EDIT_HISTORY) <= {table._meta.label for table in changeable_tables()}


def test_history_check_finds_tables_that_lose_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # The check itself, handed a table of each kind it must find. A check that finds nothing would pass every table.
    # Note has no such trigger; Card has one (its probe migration), with a code the real list doesn't hold.
    assert history_problems([Note, Card]) == [
        "probe.Note: no edit history trigger",
        "probe.Card: its trigger records 'probe_card', but LINK_TYPES gives []",
    ]
    # With its code listed, Card passes, until its trigger is switched off. (Inside the test's transaction, so the
    # rollback at the end switches it back on.)
    monkeypatch.setitem(LINK_TYPES, "probe_card", "probe.Card")
    assert history_problems([Card]) == []
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE probe_card DISABLE TRIGGER record_edits")
    assert history_problems([Card]) == ["probe.Card: its edit history trigger is switched off"]
    # A trigger with the right name, built wrong: one that runs before the edit, when the edit may still be refused,
    # and one that runs another rule altogether, with none of the words the history needs.
    with connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER record_edits ON probe_card")
        cursor.execute(
            "CREATE TRIGGER record_edits BEFORE UPDATE ON probe_card "
            "FOR EACH ROW EXECUTE FUNCTION control_record_edit('probe_card', '{}')"
        )
    assert history_problems([Card]) == ["probe.Card: its edit history trigger is not AFTER UPDATE FOR EACH ROW"]
    with connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER record_edits ON probe_card")
        cursor.execute(
            "CREATE TRIGGER record_edits AFTER UPDATE ON probe_card FOR EACH ROW EXECUTE FUNCTION core_append_only()"
        )
    assert history_problems([Card]) == [
        "probe.Card: its edit history trigger runs core_append_only(), not control_record_edit()",
        "probe.Card: its trigger records '', but LINK_TYPES gives ['probe_card']",
    ]


def test_history_check_finds_a_secret_that_would_be_copied() -> None:
    # A staff member's PIN hash is skipped (people's migration 0004). A trigger rebuilt without that word would copy
    # every new hash into the history, where anyone who reads the trail could see it. (Inside the test's transaction,
    # so the rollback at the end puts the real trigger back.)
    assert history_problems([StaffMember]) == []
    with connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER record_edits ON people_staffmember")
        cursor.execute(
            "CREATE TRIGGER record_edits AFTER UPDATE ON people_staffmember "
            "FOR EACH ROW EXECUTE FUNCTION control_record_edit('staff', '{}')"
        )
    assert history_problems([StaffMember]) == ["people.StaffMember: its trigger would copy pin_hash into the history"]
