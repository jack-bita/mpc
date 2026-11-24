# The list of flags reads a shop's own, newest found first, a page at a time (CTRL-4): one index, leading with `shop`
# (03 §9). No row changes, and the flag's trigger is left as it is. Django names people's and shops' latest migrations
# by itself, as a flag links to its side and to who raised it.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0010_staff_details_audit_action"),
        ("people", "0021_staffmember_photo"),
        ("shops", "0010_closure"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="flag",
            index=models.Index(fields=["shop", "created_at", "id"], name="control_flag_by_time"),
        ),
    ]
