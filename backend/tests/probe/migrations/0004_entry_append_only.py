# The append-only trigger on the test-only Entry table (ADR-0021): every ledger's migration will do the same. Test settings only.

from django.db import migrations

from apps.core.operations import AppendOnlyTrigger


class Migration(migrations.Migration):
    dependencies = [
        ("probe", "0003_entry_voidableentry"),
    ]

    operations = [
        AppendOnlyTrigger("entry"),
    ]
