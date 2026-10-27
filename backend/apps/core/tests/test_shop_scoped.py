"""apps/core/tests/test_shop_scoped.py — tests for ShopScoped and its two managers (ADR-0022, 03 §5.4).

Two shops write into the same table, side by side:

    shop      text
    MFANO     Customer A
    JINGINE   Customer B
    MFANO     Customer C

A read inside `shop_context(MFANO)` gets A and C only. A read that names no shop stops with
NoShopSelected: a forgotten shop is a loud error, not a quiet leak of every shop's rows. Reading every
shop takes a name anyone can search for: `system_context()` for system jobs, `all_shops` for the
superuser's admin pages.

The table is `probe.Note`, a test-only table built on ShopScoped (backend/tests/probe/): no real shop
table exists yet, and the guard must be proven before the first one (PPL-2) builds on it.
"""

import pytest
from django.db.models import Model

from apps.core.models import ShopScopedManager
from apps.core.tenancy import NoShopSelected, shop_context, system_context
from tests.probe.models import Note

pytestmark = pytest.mark.django_db


@pytest.fixture
def notes(shop_a: Model, shop_b: Model) -> None:
    # The rows from the table above. save() goes through Django's plain base manager, not the guarded
    # `objects`, so writing needs no current shop: the guard is on reads, and services check every row
    # they write (T1). `shop_id`: these shops are typed as plain models, see test_shop_context.py.
    for shop, text in [(shop_a, "Customer A"), (shop_b, "Customer B"), (shop_a, "Customer C")]:
        Note(shop_id=shop.pk, text=text).save()


@pytest.mark.usefixtures("notes")
def test_query_without_shop_raises() -> None:
    # ADR-0022: the read stops as soon as it is built, before it reaches the database. Without the
    # guard ("remember to filter"), it would hand back all three rows, and nothing would look wrong.
    with pytest.raises(NoShopSelected):
        Note.objects.all()


@pytest.mark.usefixtures("notes")
def test_shop_context_filters_rows(shop_a: Model) -> None:
    with shop_context(shop_a):
        texts = sorted(Note.objects.values_list("text", flat=True))

    # MFANO's rows only: Customer B belongs to the other shop.
    assert texts == ["Customer A", "Customer C"]


@pytest.mark.usefixtures("notes")
def test_system_context_reads_all_shops() -> None:
    # A system job (a nightly check, the demo seed) reads every shop, and says so by name:
    # `grep system_context` finds every place that does it (03 §5.4).
    with system_context():
        texts = sorted(Note.objects.values_list("text", flat=True))

    assert texts == ["Customer A", "Customer B", "Customer C"]


@pytest.mark.usefixtures("notes")
def test_admin_manager_reads_all_shops() -> None:
    # The superuser's admin pages list every shop's rows. They can't use system_context(): it is for
    # system jobs only (03 §5.4), and the admin builds its list in one step but reads it later, while
    # drawing the page. So the admin has its own manager, with a name as easy to search for.
    texts = sorted(Note.all_shops.values_list("text", flat=True))

    assert texts == ["Customer A", "Customer B", "Customer C"]


def test_default_manager_is_the_guarded_one() -> None:
    # Django, the admin's forms and DRF read a table through its default manager, not through the name
    # `objects`. `all_shops` is declared first, so without Meta's default_manager_name it would be the
    # default, and all of them would read every shop's rows with no guard.
    assert isinstance(Note._default_manager, ShopScopedManager)
