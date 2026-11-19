# A person's roles and extra keys get an index of their own, (shop, staff), on both tables (PPL-7's review). The once
# rules index only the rows that still count (people 0019), while a record pushed from offline reads every row of its
# maker's, ended ones too, to know what they held when it was made: without this, that read, once per record, would
# search the whole table, every shop's rows. Leads with `shop`, as every index here does. An index changes no row, so
# the edit history's trigger writes nothing. The dependency on shops' last migration is Django's own, as in 0019.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0019_role_and_key_end"),
        ("shops", "0010_closure"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="permissiongrant",
            index=models.Index(fields=["shop", "staff"], name="people_permissiongrant_staff"),
        ),
        migrations.AddIndex(
            model_name="roleassignment",
            index=models.Index(fields=["shop", "staff"], name="people_roleassignment_staff"),
        ),
    ]
