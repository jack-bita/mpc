# A worker's job names the photo it shows now (PPL-9): one column, empty for every job kept before, as nobody has a photo
# yet. It adds an empty column, so no row is rewritten and the edit history's trigger, which fires on UPDATE, writes no
# line for this. From here the trigger copies `photo_id` as it does any column (people 0004's list skips the PIN's hash
# alone), so the history says who changed a worker's face. A link to the attachment: PROTECT, as nothing is deleted
# (rule 7), and no index of its own, as nothing looks a job up by its photo. The dependency on control's last migration
# is Django's own: the attachments' table must be there first.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0010_staff_details_audit_action"),
        ("people", "0020_role_and_key_staff_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffmember",
            name="photo",
            field=models.ForeignKey(
                blank=True,
                db_index=False,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="control.attachment",
            ),
        ),
    ]
