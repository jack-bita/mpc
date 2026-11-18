# A new audit action (PPL-10): a worker's details fixed, their full name, phone, nickname, job title or first day, each
# before and after, with who and why. The database's rule names every action (control_auditevent_action_known), so it
# is taken off and put back with the new list, as 0008 did; the field's choices change only in Django, not in the
# database. Django names people's and shops' latest migrations by itself, as an audit line links to its shop and to who
# acted.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("control", "0009_attachments"),
        ("people", "0018_staffmember_editable"),
        ("shops", "0010_closure"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="auditevent",
            name="control_auditevent_action_known",
        ),
        migrations.AlterField(
            model_name="auditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("staff.suspend", "Staff member suspended"),
                    ("staff.unsuspend", "Staff member brought back"),
                    ("staff.leave", "Staff member left"),
                    ("staff.details_changed", "Staff member's details fixed"),
                    ("staff.temporary_password", "Temporary password set"),
                    ("device.block", "Device blocked"),
                    ("device.unblock", "Device unblocked"),
                    ("closure.cancel", "Closure cancelled"),
                    ("closure.last_day", "Closure's last day moved"),
                ],
                max_length=40,
            ),
        ),
        migrations.AddConstraint(
            model_name="auditevent",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "action__in",
                        [
                            "staff.suspend",
                            "staff.unsuspend",
                            "staff.leave",
                            "staff.details_changed",
                            "staff.temporary_password",
                            "device.block",
                            "device.unblock",
                            "closure.cancel",
                            "closure.last_day",
                        ],
                    )
                ),
                name="control_auditevent_action_known",
                violation_error_code="audit.action_unknown",
            ),
        ),
    ]
