# The edit history's trigger on the test-only Note (03 §5.16, ADR-0036), as each office table's migration will
# have, so the trigger is tested on a table of its own (apps/control/tests/test_edit_history.py). Test settings only.

from django.db import migrations

from apps.control.operations import RecordEdits


class Migration(migrations.Migration):
    dependencies = [
        ("probe", "0006_voidableentry_applied_total"),
        ("control", "0003_edit_events"),
    ]

    operations = [
        RecordEdits("note", type_code="probe_note"),
    ]
