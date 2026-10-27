"""apps/shops/tests/test_create_shop.py — create_shop: a whole new shop in one step (ADR-0001, ADR-0002).

create_shop makes the shop, its sides, and for each side one default stock location and one cash
drawer, in one transaction:

    create_shop(name="Duka la Mfano", code="MFANO", sides=[D Dawa, F Vyakula])

    MFANO
    ├── Dawa (D)     → stock location "Dawa" (default) + cash drawer "Dawa"
    └── Vyakula (F)  → stock location "Vyakula" (default) + cash drawer "Vyakula"

If any step fails, nothing is saved: never a shop with half its sides set up.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.tenancy import shop_context, system_context
from apps.shops.models import (
    PaymentAccount,
    PaymentAccountKind,
    PaymentAccountSide,
    SaleFlow,
    Shop,
    Side,
    StockLocation,
)
from apps.shops.services import NewSide, create_shop

pytestmark = pytest.mark.django_db

# Fake shop only: the repo is public (03 §10).
NAME = "Duka la Mfano"
CODE = "MFANO"
SIDES = [
    NewSide(code="D", name="Dawa"),
    NewSide(code="F", name="Vyakula", sale_flow=SaleFlow.WRITER_CASHIER_LOADER),
]


def test_create_shop_makes_location_and_drawer_per_side() -> None:
    # ADR-0001: each side has its own stock and its own drawer. ADR-0002: its stock sits in one default
    # location. create_shop sets both up with the side, so no side can exist without them.
    shop = create_shop(name=NAME, code=CODE, sides=SIDES)

    with shop_context(shop):
        sides = list(Side.objects.all())
        locations = list(StockLocation.objects.all())
        drawers = list(PaymentAccount.objects.filter(kind=PaymentAccountKind.CASH_DRAWER))
        links = list(PaymentAccountSide.objects.all())

    side_code = {side.id: side.code for side in sides}
    drawer_name = {drawer.id: drawer.name for drawer in drawers}
    assert sorted((side.code, side.name, side.sale_flow) for side in sides) == [
        ("D", "Dawa", SaleFlow.ONE_SCREEN),
        ("F", "Vyakula", SaleFlow.WRITER_CASHIER_LOADER),
    ]
    # One default location per side, named after it.
    assert sorted((side_code[loc.side_id], loc.name, loc.is_default) for loc in locations) == [
        ("D", "Dawa", True),
        ("F", "Vyakula", True),
    ]
    # One cash drawer per side, linked to that side only, named after it.
    assert len(drawers) == 2
    assert sorted((side_code[link.side_id], drawer_name[link.account_id]) for link in links) == [
        ("D", "Dawa"),
        ("F", "Vyakula"),
    ]
    # A new shop has no staff yet, so nobody made these rows: `created_by` stays empty, as for every row
    # the system makes (02 §1).
    assert all(row.created_by_id is None for row in [*sides, *locations, *drawers, *links])


def test_create_shop_all_or_nothing() -> None:
    # The second side asks for the letter D again. By then the shop, side D, its location, its drawer and
    # their link are already written; one transaction takes all of them back.
    sides = [NewSide(code="D", name="Dawa"), NewSide(code="D", name="Vyakula")]

    with pytest.raises(ValidationError) as refused:
        create_shop(name=NAME, code=CODE, sides=sides)

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["side.code_taken"]
    assert not Shop.objects.exists()
    # The shop that failed has no row to open with shop_context(), so the check reads every shop, as a
    # system check would (03 §5.4).
    with system_context():
        assert Side.objects.count() == 0
        assert StockLocation.objects.count() == 0
        assert PaymentAccount.objects.count() == 0
        assert PaymentAccountSide.objects.count() == 0


def test_create_shop_needs_a_side() -> None:
    # Everything a shop does happens on a side (ADR-0001): a sale, a stock count, a drawer. A shop with
    # no side couldn't do any of it, so an empty list is a mistake, refused before anything is written.
    with pytest.raises(ValidationError) as refused:
        create_shop(name=NAME, code=CODE, sides=[])

    assert refused.value.code == "shop.no_sides"
    assert not Shop.objects.exists()
