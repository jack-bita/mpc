# The void-stamp trigger on the test-only VoidableEntry table (03 §5.6): payments, money movements and attendance events will do the same. Test settings only.

from django.db import migrations

from apps.core.operations import VoidStampTrigger


class Migration(migrations.Migration):
    dependencies = [
        ("probe", "0004_entry_append_only"),
    ]

    operations = [
        VoidStampTrigger("voidableentry"),
    ]
