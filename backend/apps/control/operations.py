"""apps/control/operations.py — the migration step that makes PostgreSQL keep a flag as it was raised and let its
status move forward only (02 §13, ADR-0021).

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

This file owns the SQL of that rule and the operation the flag table's migration lists to add it.
"""

from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import ProjectState

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
