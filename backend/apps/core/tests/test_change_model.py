"""apps/core/tests/test_change_model.py — tests for the change log's table (Change, apps/core/models.py; SYNC-1).

Each line of a shop's change log says "record X of table Y changed, and this is change number N":

    shop  seq  entity  record_id  op
    MPC   41   staff   0199…      upsert     Asha's PIN changed
    MPC   42   side    0199…      upsert     side Dawa renamed

These tests pin what the database itself keeps true, whatever code writes the rows: a line is never changed or
deleted (a ledger, ADR-0021); a shop has one line per number, and numbers start at 1; and `op` and `entity` hold only
what a device can read. The rows are written here with save(), not through recording_changes (apps/core/changes.py),
as the rules must hold even for code that goes around it. The shops come from backend/conftest.py, typed as plain
models: `core` may not name `Shop` (ADR-0035).
"""

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import Model

from apps.core.models import Change, ChangeOp, SequenceName
from apps.core.sequences import next_number
from apps.core.tenancy import shop_context

pytestmark = pytest.mark.django_db

# How to read the refusals below: each test runs inside one transaction, and in PostgreSQL a refused command breaks
# the whole transaction. The `transaction.atomic()` inside `pytest.raises` is a savepoint: it rolls back only the
# refused command, so the test can go on afterwards.


def _line(shop: Model, seq: int, entity: str = "side", op: str = ChangeOp.UPSERT) -> Change:
    # One line of the log, as recording_changes writes it. save() goes through Django's plain base manager, so it
    # needs no open shop (apps/core/models.py).
    row = Change(shop_id=shop.pk, seq=seq, entity=entity, record_id=uuid.uuid7(), op=op)
    row.save()
    return row


def test_change_log_refuses_update_and_delete_in_database(shop_a: Model) -> None:
    # A device that read line 41 as "upsert" must never find it rewritten later: the trigger in the table's migration
    # refuses every UPDATE and DELETE, even plain SQL that no Python code sees (AppendOnlyTrigger, ADR-0021).
    line = _line(shop_a, seq=41)
    with (
        pytest.raises(IntegrityError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f"UPDATE {Change._meta.db_table} SET op = %s WHERE id = %s", [ChangeOp.ARCHIVE, line.pk])
    with shop_context(shop_a), pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        Change.objects.filter(pk=line.pk).delete()
    line.refresh_from_db()
    assert line.op == ChangeOp.UPSERT


def test_change_op_must_be_known(shop_a: Model) -> None:
    # A device knows two things to do with a changed record: save it, or take it off its lists. A third word, such as
    # "delete" (nothing is deleted, rule 7), would reach a device that can't act on it.
    with pytest.raises(IntegrityError, match="core_change_op_known"), transaction.atomic():
        _line(shop_a, seq=1, op="delete")


@pytest.mark.parametrize("entity", ["", "Side", "side!", "1side"])
def test_change_entity_must_be_a_type_code(shop_a: Model, entity: str) -> None:
    # The table is named by its link type code (apps/core/links.py): small letters and underscores, starting with a
    # letter, as on an audit line or a flag. The list of codes lives in code, where the database can't see it; the
    # shape it can check.
    with pytest.raises(IntegrityError, match="core_change_entity_shape"), transaction.atomic():
        _line(shop_a, seq=1, entity=entity)


def test_one_change_per_number_in_a_shop(shop_a: Model, shop_b: Model) -> None:
    # Two lines numbered 42 in one shop: a device that read up to 42 would have read one of them, and could never
    # learn that it missed the other. The same number in two shops is fine: each shop counts alone.
    _line(shop_a, seq=42)
    _line(shop_b, seq=42)
    with pytest.raises(IntegrityError, match="core_change_one_per_seq"), transaction.atomic():
        _line(shop_a, seq=42)


def test_change_numbers_start_at_one(shop_a: Model) -> None:
    # A device's cursor is the last number it read, and 0 means "nothing read yet". A line numbered 0 would sit at or
    # below every cursor, so no device would ever pull it.
    with pytest.raises(IntegrityError, match="core_change_seq_from_one"), transaction.atomic():
        _line(shop_a, seq=0)


def test_change_log_has_a_counter_of_its_own(shop_a: Model) -> None:
    # The change log counts with the shop's "change" counter, apart from its device codes: MPC's third device and its
    # first change are numbered 3 and 1. The database's list of counter names knows the new one too.
    with shop_context(shop_a), transaction.atomic():
        for _ in range(3):
            next_number(shop_a, SequenceName.DEVICE)
        assert next_number(shop_a, SequenceName.CHANGE) == 1
