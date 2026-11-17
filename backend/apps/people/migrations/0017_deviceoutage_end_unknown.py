# An offline period whose end the laptop never saw (SYNC-14's review): the laptop went off, or its app was closed or
# asleep, before the cut ended, so its `ended_at` is only the last time the app saw it. One column, false for every
# period kept before, as each of those was taken for one seen to its end. Added to a ledger: PostgreSQL fills the new
# column from its default without rewriting a row, so the append-only trigger, which refuses an UPDATE, never fires.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0016_device_clock_error"),
    ]

    operations = [
        migrations.AddField(
            model_name="deviceoutage",
            name="end_unknown",
            field=models.BooleanField(default=False),
        ),
    ]
