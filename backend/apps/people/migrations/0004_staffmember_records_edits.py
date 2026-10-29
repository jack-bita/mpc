# A staff member's job keeps the history of its edits (03 §5.16, ADR-0036): after every UPDATE, the trigger
# writes one control.EditEvent with who changed what. Its code is "staff" (apps/core/links.py). `pin_hash` is
# never copied: a PIN reset shows in the history as a new `pin_changed_at` only (03 §5.9).

from django.db import migrations

from apps.control.operations import RecordEdits


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0003_staffmember_created_by"),
        ("control", "0003_edit_events"),
    ]

    operations = [
        RecordEdits("staffmember", type_code="staff", skip=["pin_hash"]),
    ]
