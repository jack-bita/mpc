# The people tables' edit history moves to the rule that names the device (AUTH-8, X3): control_record_edit_v2(), as the
# old rule's SQL is frozen (ADR-0036). Each table keeps the columns it skips, copied from its last migration: the PIN's
# hash (0004), and the device's key hash and last_seen_at (0008). Undone: each goes back on the old rule. One transaction,
# so no edit is made unrecorded. shops' tables move in their own migration, as a step can only name its own app's tables.

from django.db import migrations

from apps.control.operations import MoveRecordEditsToV2


class Migration(migrations.Migration):
    dependencies = [
        # The new rule writes the history table's `device` column, so that column must be there first.
        ("control", "0006_device_in_the_books"),
        ("people", "0010_pin_lock"),
    ]

    operations = [
        MoveRecordEditsToV2("staffmember", type_code="staff", skip=["pin_hash"]),
        MoveRecordEditsToV2("role", type_code="role"),
        MoveRecordEditsToV2("roleassignment", type_code="role_assignment"),
        MoveRecordEditsToV2("permissiongrant", type_code="permission_grant"),
        MoveRecordEditsToV2("device", type_code="device", skip=["key_hash", "last_seen_at"]),
    ]
