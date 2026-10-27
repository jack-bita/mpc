"""apps/core/tests/test_append_only_model.py — tests for AppendOnly, the base of every ledger table (03 §5.3).

PostgreSQL's trigger refuses every edit to a ledger, however it is sent (test_append_only.py). AppendOnly
refuses the most common one earlier, in Python: save() on a row that is already in the database, and
delete() on a row. The programmer gets a clear message at once, and the database is never asked. Bulk
update() and delete() calls skip a row's own save() and delete(), so those are left to the trigger.

The tables are test-only (backend/tests/probe/), and the shop comes from backend/conftest.py, typed as
a plain model: `core` may not name `Shop`, not even for types (ADR-0035).
"""

from decimal import Decimal

import pytest
from django.db.models import Model
from pytest_django import DjangoAssertNumQueries

from apps.core.models import AppendOnlyError
from apps.core.tenancy import NoShopSelected, shop_context
from tests.probe.models import Entry, VoidableEntry

pytestmark = pytest.mark.django_db

# Fake amounts only. Money is a Decimal, never a float (ADR-0024).
FIFTY_THOUSAND = Decimal("50000.00")
FIVE_THOUSAND = Decimal("5000.00")


def test_saved_row_cannot_be_saved_again(shop_a: Model, django_assert_num_queries: DjangoAssertNumQueries) -> None:
    # A new row is written: the one change a ledger allows.
    Entry(shop_id=shop_a.pk, amount=FIFTY_THOUSAND).save()

    # The usual way a ledger row would get rewritten by mistake: read it, change it, save it.
    with shop_context(shop_a):
        row = Entry.objects.get()
    row.amount = FIVE_THOUSAND
    # 0 queries: Python refuses before anything is sent, so the trigger is never needed here.
    with django_assert_num_queries(0), pytest.raises(AppendOnlyError, match="append-only"):
        row.save()

    row.refresh_from_db()
    assert row.amount == FIFTY_THOUSAND


def test_row_cannot_be_deleted_in_python(shop_a: Model, django_assert_num_queries: DjangoAssertNumQueries) -> None:
    # A voidable row too: it is voided, never deleted (T3).
    row = VoidableEntry(shop_id=shop_a.pk, amount=FIFTY_THOUSAND)
    row.save()

    with django_assert_num_queries(0), pytest.raises(AppendOnlyError, match="never deleted"):
        row.delete()

    # Still there: refresh_from_db() raises DoesNotExist for a row that is gone.
    row.refresh_from_db()


def test_append_only_keeps_the_shop_guard() -> None:
    # Why AppendOnly builds on ShopScoped, and not a loose mixin beside it: a ledger table must keep
    # the shop guard as its default manager (ADR-0022). A mixin with its own Meta, listed first, would
    # hand the table a Meta without `default_manager_name`, and the unguarded `all_shops` would take over.
    assert Entry._meta.default_manager is Entry.objects
    with pytest.raises(NoShopSelected):
        Entry.objects.all()
