# Payment accounts and stock locations keep the history of their edits too (03 §5.16, ADR-0036; Jack, at CTRL-2's
# review): after every UPDATE, the trigger writes one control.EditEvent with who changed what, so a till number
# changed to someone's own phone shows who changed it, and when. Their codes are "payment_account" and
# "stock_location" (apps/core/links.py). Neither holds a secret, so no column is skipped.

from django.db import migrations

from apps.control.operations import RecordEdits


class Migration(migrations.Migration):
    dependencies = [
        ("shops", "0006_side_records_edits"),
        ("control", "0003_edit_events"),
    ]

    operations = [
        RecordEdits("paymentaccount", type_code="payment_account"),
        RecordEdits("stocklocation", type_code="stock_location"),
    ]
