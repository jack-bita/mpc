# The shops tables' edit history moves to the rule that names the device (AUTH-8, X3): control_record_edit_v2(), as the
# old rule's SQL is frozen (ADR-0036). None of these tables skips a column. Undone: each goes back on the old rule. One
# transaction, so no edit is made unrecorded.

from django.db import migrations

from apps.control.operations import MoveRecordEditsToV2


class Migration(migrations.Migration):
    dependencies = [
        # The new rule writes the history table's `device` column, so that column must be there first.
        ("control", "0006_device_in_the_books"),
        ("shops", "0007_accounts_and_locations_record_edits"),
    ]

    operations = [
        MoveRecordEditsToV2("side", type_code="side"),
        MoveRecordEditsToV2("paymentaccount", type_code="payment_account"),
        MoveRecordEditsToV2("stocklocation", type_code="stock_location"),
    ]
