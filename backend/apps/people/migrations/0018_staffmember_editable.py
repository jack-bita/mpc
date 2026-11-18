# A worker's job becomes an Editable row (PPL-10): the three columns every editable office row has (CORE-6), so a fix
# of a worker's details is refused when someone else saved one since the screen read the worker (409
# version_conflict). `version` starts at 1 for every job kept before, as each is then at its first copy; `updated_at`
# and `updated_by` are empty, as nobody has fixed one yet. PostgreSQL fills a new column from its default without
# rewriting a row, so the edit history's trigger, which fires on UPDATE, writes no line for this. The trigger already
# skips these three columns on every table (control_record_edit_v2): a version that moved says nothing to the owner.
# `updated_by` links to the job of who fixed it: PROTECT, as nothing is deleted (rule 7), and no index of its own, as
# for `created_by`.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0017_deviceoutage_end_unknown"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffmember",
            name="updated_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="staffmember",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                db_index=False,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="people.staffmember",
            ),
        ),
        migrations.AddField(
            model_name="staffmember",
            name="version",
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
    ]
