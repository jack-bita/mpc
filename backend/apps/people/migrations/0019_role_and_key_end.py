# A role or an extra key can end (PPL-7): taking one away is an edit of its row, never a delete (rule 7, 02 §5).
# Each table gets the end, three columns empty while the row counts, and a rule that it is whole or not there at all:
# open, with all three empty; ended, with a time and a reason, and who ended it, empty for the superuser. PostgreSQL adds
# a column that may be empty, or that has a default, without rewriting a row, so the edit history's trigger, which fires
# on UPDATE, writes no line for this; the end's three columns are then in every line it writes, before and after.
#
# The two once rules become partial: they count only the rows not ended, so a role taken away can be given again, as a
# new row. Each is dropped and made again under its own name, in this one transaction, so no moment comes between them
# when a role could be given twice. nulls_distinct=False stays: "every side" still counts once.
#
# Last, the no-delete trigger on both tables (NoDeleteTrigger, apps/core/operations.py): nothing links to these rows,
# so PROTECT can't stop a delete, and the history's trigger ignores DELETE. Updates go through, as an end needs.
#
# The dependency on shops' last migration is Django's own: the once rules name `side`, a link to shops' Side.

import django.db.models.deletion
from django.db import migrations, models

from apps.core.operations import NoDeleteTrigger


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0018_staffmember_editable"),
        ("shops", "0010_closure"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="permissiongrant",
            name="people_permissiongrant_once",
        ),
        migrations.RemoveConstraint(
            model_name="roleassignment",
            name="people_roleassignment_once",
        ),
        migrations.AddField(
            model_name="permissiongrant",
            name="end_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="permissiongrant",
            name="ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="permissiongrant",
            name="ended_by",
            field=models.ForeignKey(
                blank=True,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="people.staffmember",
            ),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="end_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="roleassignment",
            name="ended_by",
            field=models.ForeignKey(
                blank=True,
                db_index=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="people.staffmember",
            ),
        ),
        migrations.AddConstraint(
            model_name="permissiongrant",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ended_at__isnull", True)),
                fields=("shop", "staff", "permission", "side"),
                name="people_permissiongrant_once",
                nulls_distinct=False,
                violation_error_code="permission.already_given",
                violation_error_message="This person already has this permission on this side.",
            ),
        ),
        migrations.AddConstraint(
            model_name="permissiongrant",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("end_reason", ""),
                        ("ended_at__isnull", True),
                        ("ended_by__isnull", True),
                    ),
                    models.Q(("end_reason__regex", "\\S"), ("ended_at__isnull", False)),
                    _connector="OR",
                ),
                name="people_permissiongrant_end_whole",
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ended_at__isnull", True)),
                fields=("shop", "staff", "role", "side"),
                name="people_roleassignment_once",
                nulls_distinct=False,
                violation_error_code="role.already_given",
                violation_error_message="This person already has this role on this side.",
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("end_reason", ""),
                        ("ended_at__isnull", True),
                        ("ended_by__isnull", True),
                    ),
                    models.Q(("end_reason__regex", "\\S"), ("ended_at__isnull", False)),
                    _connector="OR",
                ),
                name="people_roleassignment_end_whole",
            ),
        ),
        NoDeleteTrigger("roleassignment"),
        NoDeleteTrigger("permissiongrant"),
    ]
