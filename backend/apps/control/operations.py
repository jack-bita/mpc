"""apps/control/operations.py — the migration steps for control's two rules in PostgreSQL: a flag is kept as it was
raised and its status moves forward only (02 §13, ADR-0021); and every edit of an office table is written to the
edit history (03 §5.16, ADR-0036).

A flag says what was found when it was raised: its kind, its subject, its two numbers, its side, its shop and
who raised it. None of that ever changes, as a ledger row never does (T2). Only its status moves, and only
forward (Jack, 29 Oct 2026; 02 v1.8):

    open ──▶ explained ──▶ resolved | dismissed (final)
      └───────────────────▶

The services keep both rules (apps/control/services.py), but a bug, a bulk update() or SQL typed by hand
would go straight past them. So the flag table's migration puts a trigger on it, as each ledger's migration
does (apps/core/operations.py): the database is the last line of defence (03 §5.6). A flag is never deleted
either (T3): the trigger refuses that too, even where no note or person's link would stop it.

The SQL strings below are frozen once they are on main, as core's are (rule 9): a change, such as a fifth
status, is a new rule, with a new function name (control_flag_forward_only_v2), new strings and a new
migration. A test pins each string by its fingerprint (test_flag_trigger_sql_never_changes_once_on_main).

The edit history works the other way round: not a rule that refuses, but one that writes. After every UPDATE of
an office table, a trigger writes one row of control.EditEvent with what changed and who changed it, so no code
path can skip the history: a service, a bulk update(), the admin, or SQL typed by hand (ADR-0036). Who comes from
the visit, which tells PostgreSQL who acts and from which device (apps/core/acting.py). Its SQL is frozen once on main
in the same way (test_edit_trigger_sql_never_changes_once_on_main), so when the rule learned the device it became a new
function, control_record_edit_v2(), and every office table moved to it (AUTH-8). The old function stays, for the old
migrations that still write it on their way to the move.

The history table guards itself as well: only that trigger may write a row of it, so neither bulk_create nor SQL
typed by hand can add a change nobody made (EditsByTriggerOnly).

This file owns the SQL of these rules and the operations the migrations list to add them: FlagForwardOnlyTrigger on
the flag table, EditsByTriggerOnly on the history table; RecordEditsV2 on each new office table; and, for what old
migrations list, RecordEdits, ChangeRecordEdits (which changes the columns a table's history skips, AUTH-2) and
MoveRecordEditsToV2 (AUTH-8).
"""

import re
from collections.abc import Sequence

from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import ProjectState

from apps.core.links import TYPE_CODE_SHAPE
from apps.core.operations import AppendOnlyTrigger

# The rule, stored in PostgreSQL as a function, as core's are. A trigger runs it before each UPDATE or
# DELETE of a flag, and it checks in order:
# - A DELETE is refused. It is checked first because a DELETE has no NEW row to look at.
# - Everything but the status must stay equal. Each row becomes one JSON object (to_jsonb), the status
#   comes out (`- skipped`), and what is left is compared, as core's void rule compares everything but the
#   stamp. Generated columns are left out too: PostgreSQL computes a stored one (`difference`) only after
#   the BEFORE triggers have run, so NEW would show it empty. Leaving it out is safe, since it is computed
#   from `expected` and `actual`, which are compared.
# - A status that changes must move forward: from open to any other, from explained to a final one. The
#   values are FlagStatus's (apps/control/models.py). A status that stays the same passes, so an update
#   that changes nothing changes nothing.
# - RETURN NEW: every check passed, so the change is written.
# ERRCODE 'restrict_violation' is in PostgreSQL's class 23, so Django raises IntegrityError, as for every
# ledger's rule (apps/core/operations.py). '' is how SQL writes one ' inside a string ("flag's").
FLAG_FORWARD_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION control_flag_forward_only() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    skipped text[];
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'DELETE on % refused: flags are never deleted (T3)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    skipped := ARRAY['status'] || ARRAY(
        SELECT attname::text FROM pg_attribute
        WHERE attrelid = TG_RELID AND attgenerated <> ''
    );
    IF to_jsonb(NEW) - skipped IS DISTINCT FROM to_jsonb(OLD) - skipped THEN
        RAISE EXCEPTION 'UPDATE on % refused: only a flag''s status may change (02 §13)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
        (OLD.status = 'open' AND NEW.status IN ('explained', 'resolved', 'dismissed'))
        OR (OLD.status = 'explained' AND NEW.status IN ('resolved', 'dismissed'))
    ) THEN
        RAISE EXCEPTION 'UPDATE on % refused: a flag''s status moves forward only, not from % to % (02 §13)',
            TG_TABLE_NAME, OLD.status, NEW.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

# Puts the rule on the flag table. Its own name, `forward_only`, so it never clashes with a ledger's
# `append_only`. BEFORE, UPDATE OR DELETE and FOR EACH ROW as in core's (apps/core/operations.py).
CREATE_FLAG_FORWARD_ONLY_TRIGGER = """
CREATE TRIGGER forward_only
    BEFORE UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION control_flag_forward_only();
"""

# Takes the trigger off, when its migration is undone.
DROP_FLAG_FORWARD_ONLY_TRIGGER = "DROP TRIGGER forward_only ON {table};"


class FlagForwardOnlyTrigger(AppendOnlyTrigger):
    # The step the flag table's migration lists after the table is made: FlagForwardOnlyTrigger("flag").
    # Built on core's AppendOnlyTrigger for its plumbing (the table's real name, a step that adds no column),
    # with its own rule, and its own undo, since its trigger has its own name.

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # Write the rule, then put it on the table. params=None: the rule's messages hold % signs, which
        # Django would otherwise read as places for values (apps/core/operations.py).
        table = self._table(app_label, schema_editor, to_state)
        schema_editor.execute(FLAG_FORWARD_ONLY_FUNCTION, params=None)
        schema_editor.execute(CREATE_FLAG_FORWARD_ONLY_TRIGGER.format(table=table), params=None)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # Take the trigger off. The function stays, as core's do: the next migration that adds it again
        # only writes the same rule again.
        table = self._table(app_label, schema_editor, from_state)
        schema_editor.execute(DROP_FLAG_FORWARD_ONLY_TRIGGER.format(table=table), params=None)

    def describe(self) -> str:
        return f"Forward-only trigger on {self.model_name}"


# The edit history's rule (03 §5.16, ADR-0036), stored in PostgreSQL as a function. A trigger runs it after each
# UPDATE of a row of an office table, with OLD (the row before) and NEW (the row after), and two words of its own
# (TG_ARGV, set by RecordEdits below): the table's type code (apps/core/links.py) and the columns never to copy.
# - First, T1: an office visit told PostgreSQL its shop (`mpc.shop_id`, apps/core/acting.py), and the edited row must
#   belong to it. If a bug elsewhere let shop A's visit change shop B's row, the edit itself is refused, so shop B's
#   history never names shop A's person. Outside a visit the setting is empty ('' or never set: NULL), and a system
#   job may work across shops (03 §5.11): no check. Checked before anything else, even an edit that changes nothing.
# - `skipped`: those columns, plus the edit's own bookkeeping on an Editable row (`version`, `updated_at`,
#   `updated_by_id`): the history row keeps who and when itself, and a version that moved says nothing to the
#   owner. Missing columns are fine: `jsonb - text[]` takes out only the keys a row has.
# - Each row becomes one JSON object (to_jsonb), without the skipped columns. Only the columns whose values differ
#   are kept, each as text (`->>`), the way the API sends a number or a date, so an amount is never read back as a
#   float (ADR-0024): {"name": "Dawa"} before, {"name": "Dawa za Mifugo"} after.
# - Nothing visible changed (a save that changed nothing, or only a skipped column): nothing is written.
# - The row: a new UUIDv7 from PostgreSQL itself (ADR-0007; PostgreSQL 18), the edited row's shop, the edit's own
#   time, who acts as the visit told PostgreSQL ('' or never told: nobody, so NULL), the type code and the row's id.
#   The time is clock_timestamp(), the clock as the row is written, not now(), the transaction's start: two edits in
#   one transaction would share a time, and an edit that waited for another's lock would get an earlier time than
#   the edit it waited for, so the owner's trail would show them out of order.
#   Written in the edit's own transaction: an edit that is undone takes its history row with it.
# - RETURN NULL: an AFTER trigger's answer is not used; the edit has already happened.
# `before` and `after` are in double quotes in the column list: both are words of SQL's own (BEFORE and AFTER
# triggers), safe as names, but quoted to leave no doubt.
RECORD_EDIT_FUNCTION = """
CREATE OR REPLACE FUNCTION control_record_edit() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    acting_shop uuid := NULLIF(current_setting('mpc.shop_id', true), '')::uuid;
    skipped text[] := ARRAY['version', 'updated_at', 'updated_by_id'] || TG_ARGV[1]::text[];
    old_row jsonb := to_jsonb(OLD) - skipped;
    new_row jsonb := to_jsonb(NEW) - skipped;
    changed_from jsonb;
    changed_to jsonb;
BEGIN
    IF acting_shop IS NOT NULL AND acting_shop <> NEW.shop_id THEN
        RAISE EXCEPTION 'UPDATE on % refused: the row belongs to another shop than the visit (T1)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    SELECT jsonb_object_agg(field, old_row ->> field), jsonb_object_agg(field, new_row ->> field)
        INTO changed_from, changed_to
        FROM jsonb_object_keys(new_row) AS field
        WHERE old_row -> field IS DISTINCT FROM new_row -> field;
    IF changed_to IS NULL THEN
        RETURN NULL;
    END IF;
    INSERT INTO control_editevent
        (id, shop_id, created_at, created_by_id, subject_type, subject_id, "before", "after")
    VALUES (
        uuidv7(), NEW.shop_id, clock_timestamp(), NULLIF(current_setting('mpc.staff_id', true), '')::uuid,
        TG_ARGV[0], NEW.id, changed_from, changed_to
    );
    RETURN NULL;
END;
$$;
"""

# Puts the rule on one office table; RecordEdits fills in the table and the two words.
# - Its own name, `record_edits`, beside a table's other triggers.
# - AFTER UPDATE: only a change that really happened is written, with the values PostgreSQL stored. INSERT is not
#   listed: a new row already keeps who made it and when (`created_by`, `created_at`). DELETE is not either:
#   nothing is deleted (T3), and PROTECT on every link refuses most deletes already.
# - FOR EACH ROW: an update() of ten rows writes ten history rows, one per row.
CREATE_RECORD_EDITS_TRIGGER = """
CREATE TRIGGER record_edits
    AFTER UPDATE ON {table}
    FOR EACH ROW EXECUTE FUNCTION control_record_edit({type_code}, {skipped});
"""

# Takes the trigger off, when its migration is undone. The function stays: other tables still use it.
DROP_RECORD_EDITS_TRIGGER = "DROP TRIGGER record_edits ON {table};"

# The edit history's rule as every office table runs it since AUTH-8: control_record_edit() above, word for word, and
# one thing more. X3: the row also names the device the visit told PostgreSQL (`mpc.device_id`, apps/core/acting.py), so
# an edit made on Laptop ya Dawa says so; '' or never told: none, so NULL, as for who acts. A device of another shop
# can't reach this row: the check at the top refuses any row but the visit's shop's, and acting_as() refuses a device of
# any other shop than the visit's. Why a new function and not an edit of the old one: its SQL is frozen, as every old
# migration runs that very string (rule 9, ADR-0036).
RECORD_EDIT_V2_FUNCTION = """
CREATE OR REPLACE FUNCTION control_record_edit_v2() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    acting_shop uuid := NULLIF(current_setting('mpc.shop_id', true), '')::uuid;
    skipped text[] := ARRAY['version', 'updated_at', 'updated_by_id'] || TG_ARGV[1]::text[];
    old_row jsonb := to_jsonb(OLD) - skipped;
    new_row jsonb := to_jsonb(NEW) - skipped;
    changed_from jsonb;
    changed_to jsonb;
BEGIN
    IF acting_shop IS NOT NULL AND acting_shop <> NEW.shop_id THEN
        RAISE EXCEPTION 'UPDATE on % refused: the row belongs to another shop than the visit (T1)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    SELECT jsonb_object_agg(field, old_row ->> field), jsonb_object_agg(field, new_row ->> field)
        INTO changed_from, changed_to
        FROM jsonb_object_keys(new_row) AS field
        WHERE old_row -> field IS DISTINCT FROM new_row -> field;
    IF changed_to IS NULL THEN
        RETURN NULL;
    END IF;
    INSERT INTO control_editevent
        (id, shop_id, created_at, created_by_id, device_id, subject_type, subject_id, "before", "after")
    VALUES (
        uuidv7(), NEW.shop_id, clock_timestamp(), NULLIF(current_setting('mpc.staff_id', true), '')::uuid,
        NULLIF(current_setting('mpc.device_id', true), '')::uuid, TG_ARGV[0], NEW.id, changed_from, changed_to
    );
    RETURN NULL;
END;
$$;
"""

# Puts the rule on one office table, as CREATE_RECORD_EDITS_TRIGGER does, with the new function. The same trigger name,
# so DROP_RECORD_EDITS_TRIGGER takes either off.
CREATE_RECORD_EDITS_V2_TRIGGER = """
CREATE TRIGGER record_edits
    AFTER UPDATE ON {table}
    FOR EACH ROW EXECUTE FUNCTION control_record_edit_v2({type_code}, {skipped});
"""

# A column's name, as Django makes them: small letters, digits and underscores.
_COLUMN_NAME = r"^[a-z_][a-z0-9_]*$"


class RecordEdits(AppendOnlyTrigger):
    # The step an office table's migration listed to switch its history on, until AUTH-8:
    # RecordEdits("staffmember", type_code="staff", skip=["pin_hash"]). Built on core's AppendOnlyTrigger for its
    # plumbing (the table's real name, a step that adds no column), with its own rule and its own undo. It keeps the old
    # rule on purpose, as migrations already on main list it (rule 9); a new table lists RecordEditsV2 below.

    # The frozen SQL this step writes. A later version of the rule names its own.
    function_sql = RECORD_EDIT_FUNCTION
    trigger_sql = CREATE_RECORD_EDITS_TRIGGER

    def __init__(self, model_name: str, type_code: str, skip: Sequence[str] = ()) -> None:
        super().__init__(model_name)
        # Checked here, as the migration is read, not when the first edit is made. A code of the wrong shape would
        # break EditEvent's own rule on every edit of the table, so every edit would fail. The two words are also
        # written into the SQL with quotes put around them by hand, which is safe only for names of these shapes.
        # fullmatch, not match: `$` in a pattern also matches before a final line break, so match() would let
        # "staff\n" through.
        # One string is a sequence of letters to Python: skip="pin_hash" would skip eight one-letter columns that
        # don't exist, and copy the hash. So a list, always.
        if isinstance(skip, str):
            raise TypeError(f"skip is a list of column names, not one name: write skip=[{skip!r}].")
        if not re.fullmatch(TYPE_CODE_SHAPE, type_code):
            raise ValueError(f"{type_code!r} is not a type code: small letters and underscores (apps/core/links.py).")
        for column in skip:
            if not re.fullmatch(_COLUMN_NAME, column):
                raise ValueError(f"{column!r} is not a column's name.")
        self.type_code = type_code
        self.skip = list(skip)

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # The table as this migration leaves it (to_state, not today's models.py), checked before any SQL is sent.
        self._put_on(self._checked_table(app_label, schema_editor, to_state), schema_editor)

    def _checked_table(self, app_label: str, schema_editor: BaseDatabaseSchemaEditor, state: ProjectState) -> str:
        # The table's real name, once the table, as `state` sees it, passes two checks:
        # - every column to skip is one of its own. A typo ("pin_hsh") would skip nothing, and the real column, a
        #   PIN hash, would be copied into every history row, with nothing to say so;
        # - it has `id` and `shop_id`, which the rule writes into each history row: without them, every edit of the
        #   table would fail, perhaps months later.
        model = state.apps.get_model(app_label, self.model_name)
        columns = {field.column for field in model._meta.concrete_fields}
        for column in self.skip:
            if column not in columns:
                raise ValueError(f"{model._meta.label} has no column {column!r} to skip.")
        if not {"id", "shop_id"} <= columns:
            raise ValueError(f"{model._meta.label} has no `id` and `shop_id`: the history keeps a shop's rows only.")
        return self._table(app_label, schema_editor, state)

    def _put_on(self, table: str, schema_editor: BaseDatabaseSchemaEditor) -> None:
        # Write the rule, and put it on the table. The columns to skip go in as one PostgreSQL array, '{pin_hash}'
        # ('{}' for none), which the rule reads with TG_ARGV[1]::text[]. params=None, as in core's.
        sql = self.trigger_sql.format(
            table=table, type_code=f"'{self.type_code}'", skipped="'{" + ",".join(self.skip) + "}'"
        )
        schema_editor.execute(self.function_sql, params=None)
        schema_editor.execute(sql, params=None)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # Take the trigger off; the function stays, as core's do.
        table = self._table(app_label, schema_editor, from_state)
        schema_editor.execute(DROP_RECORD_EDITS_TRIGGER.format(table=table), params=None)

    def describe(self) -> str:
        return f"Edit history trigger on {self.model_name}"


class ChangeRecordEdits(RecordEdits):
    # The step a later migration listed to change which columns an office table's history skips, until AUTH-8. It writes
    # the old rule, which names no device, and keeps it on purpose, as migrations on main list it. So listed today, it
    # would put a table back on the old rule, and backend/tests/test_edit_history.py turns red: SYNC-5, the next card to
    # need one, adds a form of it that writes the new rule, as RecordEditsV2 does for RecordEdits.
    # ChangeRecordEdits("device", type_code="device", skip=["key_hash", "last_seen_at"], was=["key_hash"]), after the
    # step that adds `last_seen_at` (AUTH-2). A trigger's words are fixed when it is made, and the SQL that makes it is
    # frozen once on main (rule 9), so this takes the table's trigger off and puts it back with the new list, from the
    # very same strings: no new SQL. Undone, it puts the old list back. Both moves run in the migration's transaction,
    # so no edit is ever made between them, unrecorded; a migration that isn't atomic is refused.

    def __init__(self, model_name: str, type_code: str, skip: Sequence[str], was: Sequence[str]) -> None:
        super().__init__(model_name, type_code, skip)
        # The list as the table's trigger holds it now, checked the same way: a step built with it puts it back.
        self.was = RecordEdits(model_name, type_code, was)
        if sorted(self.skip) == sorted(self.was.skip):
            # A step that changes nothing is a mistake in the migration, most likely a column left out of `skip`.
            raise ValueError(f"skip and was are the same for {model_name}: this step would change nothing.")

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # The new list is checked against the table as this migration leaves it, before the old trigger comes off.
        self._check_atomic(schema_editor)
        table = self._checked_table(app_label, schema_editor, to_state)
        schema_editor.execute(DROP_RECORD_EDITS_TRIGGER.format(table=table), params=None)
        self._put_on(table, schema_editor)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # Going back, to_state is the table before this migration: the old list is checked against it, then put back.
        self._check_atomic(schema_editor)
        table = self.was._checked_table(app_label, schema_editor, to_state)
        schema_editor.execute(DROP_RECORD_EDITS_TRIGGER.format(table=table), params=None)
        self.was._put_on(table, schema_editor)

    def _check_atomic(self, schema_editor: BaseDatabaseSchemaEditor) -> None:
        # The trigger comes off and goes back on in two statements. Only a migration that runs in one transaction
        # (Django's default on PostgreSQL) undoes the first if the second fails; one marked `atomic = False` would
        # leave the table with no history at all, and nothing to say so (found in AUTH-2's review). So refused there.
        if not schema_editor.atomic_migration:
            raise ValueError(
                f"ChangeRecordEdits on {self.model_name} needs a migration that runs in one transaction (atomic)."
            )

    def describe(self) -> str:
        return f"Edit history of {self.model_name} skips {', '.join(self.skip) or 'nothing'}"


class RecordEditsV2(RecordEdits):
    # The step a new office table's migration lists to switch its history on, since AUTH-8:
    # RecordEditsV2("product", type_code="product"). All of RecordEdits, with the rule that names the device too.
    function_sql = RECORD_EDIT_V2_FUNCTION
    trigger_sql = CREATE_RECORD_EDITS_V2_TRIGGER

    def describe(self) -> str:
        return f"Edit history trigger (v2) on {self.model_name}"


class MoveRecordEditsToV2(RecordEditsV2, ChangeRecordEdits):
    # The step that moves a table from the old rule to the new one (AUTH-8), with the columns it skips as they are:
    # MoveRecordEditsToV2("staffmember", type_code="staff", skip=["pin_hash"]). A trigger's function is fixed when it is
    # made, so the trigger comes off and goes back on. That is what ChangeRecordEdits does, so its moves are used as
    # they are, each way, in one transaction, and a migration that isn't atomic is refused: no edit is ever unrecorded.
    # Two parents, each for one thing: the SQL it writes comes from RecordEditsV2, and the moves from ChangeRecordEdits.
    # Undone, `was` puts the old rule back, with the same list.
    # A typo in `skip` would copy a column the table's history kept out: a PIN's hash, or a device's last_seen_at, which
    # moves every few minutes. So backend/tests/test_edit_history.py checks each list after the move.

    def __init__(self, model_name: str, type_code: str, skip: Sequence[str] = ()) -> None:
        # Past ChangeRecordEdits's own __init__, which refuses `skip` and `was` being the same: here they always are.
        RecordEdits.__init__(self, model_name, type_code, skip)
        self.was = RecordEdits(model_name, type_code, skip)

    def describe(self) -> str:
        return f"Edit history of {self.model_name} moves to the rule that names the device"


# The history's own guard (ADR-0036): every row of control_editevent comes from control_record_edit_v2() above, and
# from nowhere else. EditEvent.save() refuses in Python, but bulk_create() skips save(), and SQL typed by hand skips
# Python altogether; a row they wrote would be a change nobody made, perhaps naming someone who never made it.
# - pg_trigger_depth() says how many triggers deep the current statement is running. This rule is itself a
#   trigger, so an INSERT sent by Python or by hand runs it at depth 1. The INSERT that rule sends, from inside the
#   office table's trigger, runs it at depth 2. So fewer than 2: refused.
# - Another table's trigger could still write a row at depth 2; only ours does, and review keeps it that way.
# - ERRCODE 'restrict_violation', as every rule here: Django raises IntegrityError (apps/core/operations.py).
EDITS_BY_TRIGGER_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION control_edits_by_trigger_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'INSERT on % refused: only the edit history''s trigger writes it (ADR-0036)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

# Puts the guard on the history table: BEFORE INSERT, so a refused row is never written; FOR EACH ROW, so a
# bulk_create of many rows is refused at its first.
CREATE_EDITS_BY_TRIGGER_ONLY_TRIGGER = """
CREATE TRIGGER by_trigger_only
    BEFORE INSERT ON {table}
    FOR EACH ROW EXECUTE FUNCTION control_edits_by_trigger_only();
"""

# Takes the guard off, when its migration is undone.
DROP_EDITS_BY_TRIGGER_ONLY_TRIGGER = "DROP TRIGGER by_trigger_only ON {table};"


class EditsByTriggerOnly(AppendOnlyTrigger):
    # The step the history table's migration lists right after its append-only trigger: EditsByTriggerOnly("editevent").
    # Built on core's AppendOnlyTrigger for its plumbing, with its own rule and its own undo.

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # Write the rule, then put it on the table. params=None: the rule's message holds a % sign.
        table = self._table(app_label, schema_editor, to_state)
        schema_editor.execute(EDITS_BY_TRIGGER_ONLY_FUNCTION, params=None)
        schema_editor.execute(CREATE_EDITS_BY_TRIGGER_ONLY_TRIGGER.format(table=table), params=None)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, schema_editor, from_state)
        schema_editor.execute(DROP_EDITS_BY_TRIGGER_ONLY_TRIGGER.format(table=table), params=None)

    def describe(self) -> str:
        return f"Written-by-trigger-only guard on {self.model_name}"
