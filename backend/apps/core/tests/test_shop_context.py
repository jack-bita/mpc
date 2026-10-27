"""apps/core/tests/test_shop_context.py — tests for the current shop, in apps/core/tenancy.py (ADR-0022).

Each visit to the server (a request) works for one shop. The code that knows the shop (later: a paired
device's key, or a staff login) opens `shop_context(shop)`, and every read inside the block sees that
shop only. These tests pin down what the block promises: the shop is gone when the block ends, even
when it ends in an error, and an inner block wins only while it lasts. How a table's reads use the
current shop is tested in test_shop_scoped.py.

The shops come from backend/conftest.py and are typed as plain models: `core` may not name `Shop`,
not even for types (ADR-0035; decided in CORE-2, see backend/pyproject.toml).
"""

import pytest
from django.db.models import Model

from apps.core.tenancy import NoShopSelected, current_shop, shop_context

# The shops are rows in the test database.
pytestmark = pytest.mark.django_db


def test_shop_context_is_cleared_after_the_block(shop_a: Model) -> None:
    with shop_context(shop_a):
        assert current_shop() == shop_a.pk

    # The visit is over. A server worker serves one visit after another, so the next visit must start
    # with no shop, never with this one: it might come from another shop.
    with pytest.raises(NoShopSelected):
        current_shop()


def test_shop_context_is_cleared_even_after_an_error(shop_a: Model) -> None:
    # A visit that crashes halfway (a bug, a lost database connection) must not leave its shop behind
    # either: the block clears the shop however it ends.
    with pytest.raises(ValueError, match="the visit failed"), shop_context(shop_a):
        raise ValueError("the visit failed")

    with pytest.raises(NoShopSelected):
        current_shop()


def test_inner_context_wins_and_the_outer_comes_back(shop_a: Model, shop_b: Model) -> None:
    # A system job that works through the shops one at a time, inside a wider block, names each shop with
    # its own block. When that block ends, the shop from before is back: not "no shop", and not the inner
    # one. (A visit never does this: it works for one shop only, 03 §5.4.)
    with shop_context(shop_a):
        with shop_context(shop_b):
            assert current_shop() == shop_b.pk

        assert current_shop() == shop_a.pk
