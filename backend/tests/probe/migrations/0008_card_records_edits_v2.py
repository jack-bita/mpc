# The test-only Card moves to the rule that names the device (AUTH-8), as every office table does, so the history's own
# tests edit a card the way the real tables are edited now. Test settings only.

from django.db import migrations

from apps.control.operations import MoveRecordEditsToV2


class Migration(migrations.Migration):
    dependencies = [
        # The new rule writes the history table's `device` column, so that column must be there first.
        ("control", "0006_device_in_the_books"),
        ("probe", "0007_card"),
    ]

    operations = [
        MoveRecordEditsToV2("card", type_code="probe_card"),
    ]
