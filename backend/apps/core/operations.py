"""apps/core/operations.py — migration operations that make PostgreSQL refuse edits to ledgers (ADR-0021).

A ledger keeps history (T2): stock movements, balance entries, payments, attendance events, the change
log, dated prices and settings. Its rows are written once and never changed or deleted; a mistake is
fixed with a new row. The services only ever insert, but a bug, a bulk update() or SQL typed by hand
would go straight past them. So each ledger's migration puts a trigger on its table: a rule stored in
PostgreSQL that runs before every change, however it is sent, and refuses it. The database is the last
line of defence (03 §5.6).

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
# - ERRCODE 'restrict_violation' is PostgreSQL's code for a broken rule, as a unique index or a foreign
#   key reports one, so Django raises IntegrityError: the data broke a rule, the database is not broken.
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
#   whole table at once) is not refused either: tests and `manage.py flush` empty tables that way, and
#   only the table's owner can run it, never the app's queries.
# - FOR EACH ROW: the rule runs for every row a command touches, so a bulk update() is refused too.
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
