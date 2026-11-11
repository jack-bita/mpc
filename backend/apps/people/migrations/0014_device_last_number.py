# A device's last number (SYNC-5, 02 §17): the number its next record should follow, so a jump raises a device_gap
# flag. Two steps, as 0013's: the column, empty until the device's next record; then the device's edit history learns
# to skip it too, on the rule that names the device. Every record a laptop sends moves it, so without the second step
# each would write a history row. Undone: the history skips 0013's list again, then the column goes.

from django.db import migrations, models

from apps.control.operations import ChangeRecordEditsV2


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0013_device_sync_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="last_device_seq",
            field=models.PositiveBigIntegerField(blank=True, editable=False, null=True),
        ),
        ChangeRecordEditsV2(
            "device",
            type_code="device",
            skip=["key_hash", "last_seen_at", "last_synced_at", "unsent_count", "app_version", "last_device_seq"],
            was=["key_hash", "last_seen_at", "last_synced_at", "unsent_count", "app_version"],
        ),
    ]
