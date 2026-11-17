# A device's clock error (SYNC-14, 03 §6.6): how far its clock was from the server's at its last push, for the device
# health page. Two steps, as 0013's and 0014's: the column, empty until the device's next push; then the device's edit
# history learns to skip it too, on the rule that names the device. Every push moves it, so without the second step
# each would write a history row. Undone: the history skips 0014's list again, then the column goes.

from django.db import migrations, models

from apps.control.operations import ChangeRecordEditsV2


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0015_device_outages"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="clock_error",
            field=models.DurationField(blank=True, editable=False, null=True),
        ),
        ChangeRecordEditsV2(
            "device",
            type_code="device",
            skip=[
                "key_hash",
                "last_seen_at",
                "last_synced_at",
                "unsent_count",
                "app_version",
                "last_device_seq",
                "clock_error",
            ],
            was=["key_hash", "last_seen_at", "last_synced_at", "unsent_count", "app_version", "last_device_seq"],
        ),
    ]
