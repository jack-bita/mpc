"""apps/shops/tests/test_rename_side.py — rename_side: a side gets a new name, safely (02 §1, 02 §4).

The route's own tests (test_api_sides.py) cover the version check: an edit made on an old copy is refused.
These cover the shop rules every edit keeps (T1), which apps/core/editing.py checks for every Editable
row. The staff members come from backend/conftest.py and are typed Any: `shops` may not name `people`'s
StaffMember, not even in its tests (ADR-0035).
"""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from pytest_django import Settings

from apps.core.tenancy import ShopMismatch, shop_context
from apps.shops.models import Shop, Side
from apps.shops.services import rename_side

pytestmark = pytest.mark.django_db


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return Side.objects.create(shop=shop_a, code="D", name="Dawa")


def test_rename_side_refuses_a_shop_that_is_not_open(shop_a: Shop, shop_b: Shop, dawa: Side) -> None:
    # T1: shop B's visit can't change shop A's side. A bug in the calling code, so it raises, and the
    # name stays.
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        rename_side(dawa, version=1, name="Dawa za Mifugo", by=None)

    with shop_context(shop_a):
        assert Side.objects.get(pk=dawa.pk).name == "Dawa"


def test_rename_side_refuses_someone_of_another_shop(shop_a: Shop, dawa: Side, staff_b: Any) -> None:
    # T1 again: a staff member of shop B can't be recorded as the one who changed shop A's side.
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        rename_side(dawa, version=1, name="Dawa za Mifugo", by=staff_b)

    with shop_context(shop_a):
        assert Side.objects.get(pk=dawa.pk).name == "Dawa"


def test_side_name_fixed_on_the_demo(shop_a: Shop, dawa: Side, staff_a: Any, settings: Settings) -> None:
    # On the demo every visitor shares Meneja's login, and Meneja holds settings.manage for the rules (SHOP-5), the key
    # that renames a side too. A visitor's new name would greet everyone after them until the next morning's seed, so a
    # person's rename is refused there, before anything is written, as the switch is (demo.sides_fixed).
    settings.DEMO_SEED = True
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        rename_side(dawa, version=1, name="Jina Baya", by=staff_a)
    assert [error.code for error in refused.value.error_list] == ["demo.sides_fixed"]
    with shop_context(shop_a):
        assert Side.objects.get(pk=dawa.pk).name == "Dawa"


def test_the_system_renames_sides_on_the_demo(shop_a: Shop, dawa: Side, settings: Settings) -> None:
    # The system (`by` None), as the seed and the superuser act, still may.
    settings.DEMO_SEED = True
    with shop_context(shop_a):
        rename_side(dawa, version=1, name="Dawa za Mifugo", by=None)
        assert Side.objects.get(pk=dawa.pk).name == "Dawa za Mifugo"
