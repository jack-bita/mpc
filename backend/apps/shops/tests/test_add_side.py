"""apps/shops/tests/test_add_side.py — add_side: a new side for a shop that already exists (02 §4, ADR-0001).

A side never comes alone: add_side also makes its default stock location (ADR-0002) and its cash drawer,
as create_shop does for each side it makes (test_create_shop.py covers what they make). These tests
cover who adds a side, and in which shop (T1).

The staff members come from backend/conftest.py and are typed Any: `shops` may not name `people`'s
StaffMember, not even in its tests (ADR-0035).
"""

from typing import Any

import pytest

from apps.core.tenancy import ShopMismatch, shop_context
from apps.shops.models import PaymentAccount, Shop, Side, StockLocation
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db


def test_add_side_records_who_added_it(shop_a: Shop, staff_a: Any) -> None:
    # Who made a row is its `created_by` (02 §1): the side, and what comes with it.
    with shop_context(shop_a):
        side = add_side(shop=shop_a, code="P", name="Pembejeo", by=staff_a)
        location = StockLocation.objects.get(side=side)
        drawer = PaymentAccount.objects.get(name="Pembejeo")

    assert side.created_by_id == location.created_by_id == drawer.created_by_id == staff_a.pk


def test_add_side_refuses_a_shop_that_is_not_open(shop_a: Shop, shop_b: Shop) -> None:
    # T1: a visit works inside one shop. Shop B's visit adding a side to shop A is a bug in the calling
    # code, so it raises before anything is written.
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        add_side(shop=shop_a, code="P", name="Pembejeo", by=None)

    with shop_context(shop_a):
        assert not Side.objects.exists()


def test_add_side_refuses_someone_of_another_shop(shop_a: Shop, staff_b: Any) -> None:
    # T1 again: a staff member of shop B can't be recorded as the one who added shop A's side.
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        add_side(shop=shop_a, code="P", name="Pembejeo", by=staff_b)

    with shop_context(shop_a):
        assert not Side.objects.exists()
