"""backend/tests/test_edit_history.py — every office table keeps the history of its edits (03 §5.16, ADR-0036).

An office table is one that people change from the office: every table built on Editable (CORE-6), and
StaffMember, which is older than Editable. Each must carry the trigger that writes control.EditEvent, put there by
RecordEdits in its migration (apps/control/operations.py): switched on, and recording the table's own type code
from apps/core/links.py, so its history rows load back.

This module asks Django for those tables itself, as the tenancy sweep does (test_tenancy_sweep.py), so a new
office table that forgets (products, contacts, roles, devices) turns CI red with no change here. The check is a
function that returns what breaks the rule, and the check's own test hands it probe tables built to break it. It
lives outside `apps` because it names tables of several apps (ADR-0035).
"""

from collections.abc import Iterable

import pytest
from django.apps import apps
from django.db import connection, models

from apps.core.links import LINK_TYPES
from apps.core.models import Editable
from apps.people.models import StaffMember
from tests.probe.models import Card, Note

pytestmark = pytest.mark.django_db


def office_tables() -> list[type[models.Model]]:
    # Every Editable table of our apps (backend/apps/; the test-only probe app is not one), and StaffMember.
    editable = [
        table
        for table in apps.get_models()
        if issubclass(table, Editable) and table._meta.app_config.name.startswith("apps.")
    ]
    return [*editable, StaffMember]


def history_problems(tables: Iterable[type[models.Model]]) -> list[str]:
    # PostgreSQL's own list of triggers (pg_trigger) says, for each table, whether it has `record_edits`, whether it
    # is switched on (`tgenabled`: O or A fire in every session; D is off; R fires only on a copy of the database),
    # and the words it was given (`tgargs`: each one ends with a zero byte), the first of which is the type code.
    problems = []
    with connection.cursor() as cursor:
        for table in tables:
            label = table._meta.label
            cursor.execute(
                "SELECT tgargs, tgenabled FROM pg_trigger WHERE tgrelid = %s::regclass AND tgname = 'record_edits'",
                [table._meta.db_table],
            )
            row = cursor.fetchone()
            if row is None:
                problems.append(f"{label}: no edit history trigger")
                continue
            words, enabled = row
            if enabled not in ("O", "A"):
                problems.append(f"{label}: its edit history trigger is switched off")
            code = bytes(words).split(b"\x00")[0].decode()
            codes = [listed for listed, named in LINK_TYPES.items() if named == label]
            if codes != [code]:
                problems.append(f"{label}: its trigger records {code!r}, but LINK_TYPES gives {codes}")
    return problems


def test_every_office_table_records_its_edits() -> None:
    tables = office_tables()
    # Not looking at nothing: the sides and the staff are office tables today.
    assert {"shops.Side", "people.StaffMember"} <= {table._meta.label for table in tables}
    assert history_problems(tables) == []


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
