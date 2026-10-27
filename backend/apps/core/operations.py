"""apps/core/operations.py — migration operations that make PostgreSQL refuse edits to ledgers (ADR-0021).

A ledger keeps history (T2). The ledgers are listed in 03 §5.6: stock movements, balance entries,
allocations, payments, money movements, attendance events, audit events, the change log, and the dated
rules (prices, product costs, settings, pay rates). Their rows are written once and never changed or
deleted; a mistake is fixed with a new row. The services only ever insert, but a bug, a bulk update()
or SQL typed by hand would go straight past them. So each ledger's migration puts a trigger on its
table: a rule stored in PostgreSQL that runs before every change, however it is sent, and refuses it.
The database is the last line of defence (03 §5.6).

Two rules, one operation each. AppendOnlyTrigger refuses every UPDATE and DELETE. VoidStampTrigger is
for payments, money movements and attendance events: it allows one change, filling the void stamp
once, and then refuses everything, as the other does.

Later migrations meet the trigger too. Django fills a column that becomes NOT NULL with an UPDATE, and
a RunPython fix updates rows: on a ledger with rows, both are refused. A migration that truly needs
one lifts the trigger on purpose, in a reviewed step (ALTER TABLE … DISABLE TRIGGER append_only, the
change, then ENABLE TRIGGER), never quietly.

The SQL strings below are frozen once they are on main. Every ledger's migration calls them, so an
edit would change those migrations from the outside (rule 9): a fresh database would get the new rule,
a live one would keep the old, and the next ledger's migration would swap it on every table at once. A
change is a new rule: a new function name (core_append_only_v2), new strings, new migrations. A test
pins each string by its fingerprint (test_trigger_sql_never_changes_once_on_main).

This file owns the SQL of those rules and the operations a migration lists to add them.
"""

from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation, OperationCategory
from django.db.migrations.state import ProjectState

# The rule, stored in PostgreSQL as a function (PL/pgSQL, its own small language). A trigger runs it
# before each UPDATE or DELETE of a row, and it always refuses: there is nothing to check, because the
# trigger only calls it for the changes a ledger never allows.
# - CREATE OR REPLACE: every ledger's migration runs this line, so one function serves every table, and
#   running it again only writes the same rule again.
# - Each % in the message is filled with the next value: TG_OP is the command (UPDATE or DELETE) and
#   TG_TABLE_NAME the table, so the message says what was refused, and where.
# - ERRCODE 'restrict_violation' (23001) is in PostgreSQL's class 23, "integrity constraint violation",
#   with a unique index's code (23505) and a foreign key's (23503). Django turns the whole class into
#   IntegrityError: the data broke a rule, the database is not broken. So code that catches
#   IntegrityError for one of them (an id already taken, CORE-6) must check the code, or it would
#   hide this refusal too.
APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION core_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% on % refused: rows are append-only (ADR-0021)', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;
"""

# Puts the rule on one table; {table} is filled in by the operation below.
# - The name `append_only` only has to be unique per table, so every ledger's trigger can share it.
# - BEFORE: it runs before the change is written, so a refused change never touches the table.
# - UPDATE OR DELETE: INSERT is not listed, so new rows are still written. TRUNCATE (emptying the
#   whole table at once) is not refused either: tests and `manage.py flush` empty tables that way.
#   Today only care stops it: the app connects as the database user that owns the tables, the same
#   one that runs the migrations. Before shop #2 the app gets a database user of its own (03 §5.4);
#   that user won't own the tables, so it can't TRUNCATE them unless it is given the right.
# - FOR EACH ROW: the rule runs once for each row the command touches, with that row's OLD and NEW.
#   The void rule needs them; the plain one is built the same way. A command that touches no row runs
#   no rule, so an update() that matches nothing passes, harmlessly.
CREATE_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER append_only
    BEFORE UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION core_append_only();
"""

# Takes the trigger off one table, when its migration is undone. The function stays: other tables
# still use it.
DROP_APPEND_ONLY_TRIGGER = "DROP TRIGGER append_only ON {table};"


class AppendOnlyTrigger(Operation):
    # A migration step, built on Django's Operation like CreateModel and AddField. A ledger's migration
    # lists it after the table is made: AppendOnlyTrigger("stockmovement") (the model's name in lower
    # case, as Django writes it in migrations).

    # How Django labels the step when it lists a migration's steps: "s", plain SQL.
    category = OperationCategory.SQL

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        # Django keeps a picture of every table's columns (the "state") to work out what the next
        # migration must change. A trigger adds no column, so the picture stays as it is.
        pass

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # Runs when the migration is applied: write the rule, then put it on the table.
        # params=None: "no values to fill in". Without it, Django's PostgreSQL code reads each % in
        # the SQL as a place for a value, and the rule's message has two.
        table = self._table(app_label, schema_editor, to_state)
        schema_editor.execute(APPEND_ONLY_FUNCTION, params=None)
        schema_editor.execute(CREATE_APPEND_ONLY_TRIGGER.format(table=table), params=None)

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # Runs when the migration is undone: take the trigger off. `from_state` is the picture with
        # this migration applied, the one in which the table is known (CreateModel does the same).
        table = self._table(app_label, schema_editor, from_state)
        schema_editor.execute(DROP_APPEND_ONLY_TRIGGER.format(table=table), params=None)

    def describe(self) -> str:
        # The line Django prints when it runs this step.
        return f"Append-only trigger on {self.model_name}"

    def _table(self, app_label: str, schema_editor: BaseDatabaseSchemaEditor, state: ProjectState) -> str:
        # The table's real name ("entry" → probe_entry), from the migration's own picture of the
        # models, not from today's models.py: an old migration must still run after a later card
        # changes the model. quote_name puts it in double quotes, so it is always a safe SQL name.
        model = state.apps.get_model(app_label, self.model_name)
        return schema_editor.quote_name(model._meta.db_table)


# The void rule, for payments, money movements and attendance events (T2, 03 §5.6). They may change
# once: the void stamp (`voided_at`, `voided_by`, `void_reason`, `void_approval`) is filled, and the row
# is then frozen. A trigger runs it before each UPDATE or DELETE of a row, and it checks in order:
# - A DELETE is refused, with the plain rule's message: a voidable row is voided, never deleted (T3).
#   It is checked first because a DELETE has no NEW row to look at.
# - OLD is the row as it is in the table, NEW the row as the UPDATE wants it. A row whose stamp is
#   already filled refuses every change: who voided it, when and why stay as they were written.
# - Everything outside the stamp must stay equal. Each row becomes one JSON object (to_jsonb), the
#   stamp's keys come out (`- skipped`), and what is left is compared. The stamp names the database's
#   columns: a link gets `_id` (voided_by → voided_by_id). A key a table lacks is skipped, as
#   `void_approval_id` is on the probe table, until the Approval table comes (R1). Both sides are
#   whole JSON objects, never empty, so <> would answer the same; IS DISTINCT FROM is the safe habit
#   in SQL, because it still gives a plain yes or no when a value is empty (NULL), where <> gives
#   "unknown". This check comes before the next one, so a change to another column alone gets this
#   message, the clearer one.
# - Generated columns are left out of the comparison too (`skipped`). PostgreSQL computes a stored one,
#   such as a payment's applied total (02 §10), only after the BEFORE triggers have run, so NEW would
#   show it empty and every void would look like a change. Leaving it out is safe: it is computed from
#   other columns, and those are compared. `pg_attribute` is PostgreSQL's own list of every table's
#   columns; TG_RELID is the table this trigger runs on; `attgenerated` is empty for a normal column.
# - The change must fill `voided_at`. Half a stamp (a reason with no time) would leave the row open,
#   and a later update could then count as the first void.
# - RETURN NEW: every check passed, so the change is written. (The plain rule never says yes, so it
#   has no RETURN.)
# Whether a filled stamp is complete (a reason, who), and whether `voided_by` and `void_approval`
# belong to the row's shop, is not this rule's job: each void table adds those rules itself. CORE-3's
# *Watch out* in the build plan (04) lists them, and MONEY-1, CASH-2 and ATT-1 point to it.
VOID_STAMP_FUNCTION = """
CREATE OR REPLACE FUNCTION core_void_stamp_only() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    stamp text[] := ARRAY['voided_at', 'voided_by_id', 'void_reason', 'void_approval_id'];
    skipped text[];
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION '% on % refused: rows are append-only (ADR-0021)', TG_OP, TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.voided_at IS NOT NULL THEN
        RAISE EXCEPTION 'UPDATE on % refused: the row is already voided (ADR-0021)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    skipped := stamp || ARRAY(
        SELECT attname::text FROM pg_attribute
        WHERE attrelid = TG_RELID AND attgenerated <> ''
    );
    IF to_jsonb(NEW) - skipped IS DISTINCT FROM to_jsonb(OLD) - skipped THEN
        RAISE EXCEPTION 'UPDATE on % refused: only the void stamp may change (ADR-0021)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.voided_at IS NULL THEN
        RAISE EXCEPTION 'UPDATE on % refused: a void must fill voided_at (ADR-0021)', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
"""

# Puts the void rule on one table. The same name as the plain rule's trigger: every ledger has one
# trigger called `append_only`, and only the rule it calls differs. So DROP_APPEND_ONLY_TRIGGER takes
# this one off too.
CREATE_VOID_STAMP_TRIGGER = """
CREATE TRIGGER append_only
    BEFORE UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION core_void_stamp_only();
"""


class VoidStampTrigger(AppendOnlyTrigger):
    # The step for payments, money movements and attendance events: VoidStampTrigger("payment"). The
    # same as AppendOnlyTrigger, except for the rule it writes. Undoing it is the parent's
    # database_backwards: the trigger has the same name, so the same DROP takes it off.

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        # The parent's steps with the void rule: write it, then put it on the table. params=None for
        # the same reason as above: the rule's messages hold % signs.
        table = self._table(app_label, schema_editor, to_state)
        schema_editor.execute(VOID_STAMP_FUNCTION, params=None)
        schema_editor.execute(CREATE_VOID_STAMP_TRIGGER.format(table=table), params=None)

    def describe(self) -> str:
        return f"Void-stamp trigger on {self.model_name}"
