"""backend/tests/conftest.py — the two filled shops the tenancy sweep sends its visitor between
(backend/tests/test_tenancy_sweep.py).

The sweep calls every office route as a staff member of shop B and looks for any row of shop A in the
answers. It can only find a leak of rows that exist, so both shops get rows of every table a route shows,
made the way the app makes them, through the services. The checks never change; this file grows instead:
a card that adds a route over a new table gives both shops a row of it here, and the sweep fails, saying
so, while shop A has none. The demo seed (DATA-1) could fill the shops later.

The shops and their staff come from backend/conftest.py. Fake data only: the repo is public (03 §10).
"""

import pytest

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.shops.services import add_side


@pytest.fixture
def sweep_shops(shop_a: Shop, shop_b: Shop, staff_a: StaffMember, staff_b: StaffMember) -> tuple[Shop, Shop]:
    # Shop A, whose rows must never show, and shop B, the visitor's own. add_side makes each side with its
    # stock location, its cash drawer and the drawer's link to the side, so four tables at once; the staff
    # members are rows of a fifth. Each write runs inside its own shop, as a service needs (T1).
    with shop_context(shop_a):
        add_side(shop=shop_a, code="D", name="Dawa", by=staff_a)
        add_side(shop=shop_a, code="F", name="Vyakula", by=staff_a)
    with shop_context(shop_b):
        add_side(shop=shop_b, code="D", name="Dawa", by=staff_b)
    return shop_a, shop_b
