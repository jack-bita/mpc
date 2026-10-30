"""backend/tests/conftest.py — the two filled shops the tenancy sweep sends its visitor between
(backend/tests/test_tenancy_sweep.py).

The sweep calls every office route as a staff member of shop B and looks for any row of shop A in the
answers. It can only find a leak of rows that exist, so both shops get rows of every table a route shows,
made the way the app makes them, through the services. The checks never change; this file grows instead:
a card that adds a route over a new table gives both shops a row of it here, and the sweep fails, saying
so, while shop A has none; and a card that adds a route needing query parameters gives them here too
(sweep_queries). The device routes are called by a paired device of each shop (sweep_device_clients, AUTH-2). The
demo seed (DATA-1) could fill the shops later.

The sweep knows shop A's rows by their ids, and by the texts and amounts only shop A holds, so that a leak
with no ids, like a report of names and totals, is found too. So give shop A values of its own: names and
amounts no row of shop B holds (B's side is Pembejeo, not a second Dawa), and none that an answer could hold
by itself, like "name", a word every answer has as a key. Words from a field's fixed choices and zero amounts
never count: they are the same in every shop.

The shops and their staff come from backend/conftest.py. Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api.authentication import DEVICE_KEY_COOKIE
from apps.people.models import StaffMember
from apps.people.services import confirm_pairing, start_pairing
from apps.shops.models import Shop, Side
from apps.shops.services import add_side

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def sweep_shops(shop_a: Shop, shop_b: Shop, staff_a: StaffMember, staff_b: StaffMember) -> tuple[Shop, Shop]:
    # Shop A, whose rows must never show, and shop B, the visitor's own. add_side makes each side with its
    # stock location, its cash drawer and the drawer's link to the side, so four tables at once; the staff
    # members are rows of a fifth. Each write runs inside its own shop, as a service needs (T1).
    with shop_context(shop_a):
        add_side(shop=shop_a, code="D", name="Dawa", by=staff_a)
        add_side(shop=shop_a, code="F", name="Vyakula", by=staff_a)
    with shop_context(shop_b):
        add_side(shop=shop_b, code="P", name="Pembejeo", by=staff_b)
    return shop_a, shop_b


@pytest.fixture
def sweep_device_clients(
    sweep_shops: tuple[Shop, Shop], staff_a: StaffMember, staff_b: StaffMember, give_role: GiveRole
) -> tuple[APIClient, APIClient]:
    # One paired device in each sweep shop, as the browsers that hold their keys: the visitors the sweep sends to every
    # device route (AUTH-2). Paired the way the app pairs one: the device asks (start_pairing), and the shop's owner
    # confirms its code on a side of the shop. Each device's name is its shop's alone, so a route that showed shop A's
    # device to shop B's would be caught by the name too, beside its id.
    shop_a, shop_b = sweep_shops
    clients = []
    for owner, shop, side_code, name in (
        (staff_a, shop_a, "D", "Laptop ya Mfano"),
        (staff_b, shop_b, "P", "Simu ya Jingine"),
    ):
        give_role(owner, RoleTemplate.OWNER, None)
        asked = start_pairing()
        with shop_context(shop):
            confirm_pairing(asked.request.code, name=name, home_side=Side.objects.get(code=side_code), by=owner)
        client = APIClient()
        client.cookies[DEVICE_KEY_COOKIE] = asked.key
        clients.append(client)
    return clients[0], clients[1]


@pytest.fixture
def sweep_queries() -> dict[str, dict[str, str]]:
    # The query parameters a GET route can't answer without, by the route's name. They must be ones under which
    # shop A's rows show: a day's report asks for the day the rows above are made on, the test's today, as in
    # {"daily-report-list": {"date": str(timezone.localdate())}}, never a fixed date, which would show nothing to
    # either shop. Without them such a route answers 400; with ones that show nothing, even shop A's own staff
    # sees nothing; either way the sweep fails and points here. No route needs any yet.
    return {}
