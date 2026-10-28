"""apps/shops/tests/test_rename_side.py — rename_side: a side gets a new name, safely (02 §1, 02 §4).

The route's own tests (test_api_sides.py) cover the version check: an edit made on an old copy is refused.
These cover the shop rules every edit keeps (T1), which apps/core/editing.py checks for every Editable
row. The staff members come from backend/conftest.py and are typed Any: `shops` may not name `people`'s
StaffMember, not even in its tests (ADR-0035).
"""

from typing import Any

import pytest

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
