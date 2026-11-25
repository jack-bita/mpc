# Written by hand, the first migration that writes rows (WAGE-7, 03 §5.8): the Owner role of every shop that already has
# its roles gets the new code, meals.record. Each shop keeps its own copy of the role templates (02 §5), made when the
# shop was set up, so a new code reaches a new shop by itself and an old one only here: without it an old shop's owner
# wouldn't hold the code, and as whoever gives a key must hold it, nobody there could ever be given it. The Owner's
# alone: the code is one of the owner's own, which the owner gives to whoever he chooses (Jack, 15 Nov 2026).
# Every shop at once, as a migration is a system job with no shop open: the tables here are the migration's own copies,
# whose managers have no guard (apps/core/models.py).

from typing import Any

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.utils import timezone

# The code and the template as text, never imported: a migration says what it did the day it ran, whatever the list
# becomes later (rule 9).
CODE = "meals.record"
OWNER = "owner"


def give_the_owners_the_key(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Role = apps.get_model("people", "Role")
    roles = Role.objects.using(schema_editor.connection.alias)
    # A shop set up after the code was added has it already, so nothing is written there; run again, nothing anywhere.
    for role in roles.filter(template=OWNER).exclude(permissions__contains=[CODE]).order_by("pk"):
        # Sorted, as a new shop's roles are written (copy_role_templates), so an old shop's Owner and a new one's read
        # the same in the history and on the screens.
        _write(role, sorted([*role.permissions, CODE]))


def take_the_key_back(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    # Undone: from every role that holds it, whichever gave it, a shop's set up after the code included, as 0022's old
    # rule of known codes refuses any that still does.
    Role = apps.get_model("people", "Role")
    roles = Role.objects.using(schema_editor.connection.alias)
    for role in roles.filter(permissions__contains=[CODE]).order_by("pk"):
        _write(role, [code for code in role.permissions if code != CODE])


def _write(role: Any, permissions: list[str]) -> None:
    # `role`: a row of the migration's own copy of the table, not today's Role, so the type checker can't know it.
    role.permissions = permissions
    # As any edit of an office record (apps/core/editing.py): its version moves, so a page that read the role before
    # can't save over this, and who and when are kept, nobody, the system. The trigger writes the same in the role's
    # history, with nobody named, as no visit told PostgreSQL who acts (ADR-0036).
    role.version += 1
    role.updated_at = timezone.now()
    role.updated_by = None
    role.save(update_fields=["permissions", "version", "updated_at", "updated_by"])


class Migration(migrations.Migration):
    # The edit history's table and the trigger's rule, which write a line for each role changed here, are there already:
    # people's 0011 waits for them.
    dependencies = [("people", "0022_meals_record_code")]

    operations = [migrations.RunPython(give_the_owners_the_key, take_the_key_back)]
