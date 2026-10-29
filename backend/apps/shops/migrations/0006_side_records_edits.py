# A side keeps the history of its edits (03 §5.16, ADR-0036): after every UPDATE, the trigger writes one
# control.EditEvent with who changed what, such as the owner renaming "Dawa". Its code is "side"
# (apps/core/links.py).

from django.db import migrations

from apps.control.operations import RecordEdits


class Migration(migrations.Migration):
    dependencies = [
        ("shops", "0005_side_editable"),
        ("control", "0003_edit_events"),
    ]

    operations = [
        RecordEdits("side", type_code="side"),
    ]
