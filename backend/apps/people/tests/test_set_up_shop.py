"""apps/people/tests/test_set_up_shop.py — set_up_shop: a whole new shop, with its own six roles, in one step (02 §5,
03 §5.8).

create_shop (apps/shops/services.py) makes the shop, its sides and what each side comes with; `shops` may not import
`people` (ADR-0035), so set_up_shop calls it and then copies the role templates in, in one transaction:

    set_up_shop(name="Duka la Mfano", code="MFANO", sides=[D Dawa, F Vyakula])

    MFANO
    ├── Dawa (D), Vyakula (F)    → each with its stock location and cash drawer (create_shop)
    └── Owner, Manager, Seller, Order writer, Cashier, Worker    → the shop's own roles

If any step fails, nothing is saved: never a shop where nobody may act.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.permissions import ROLE_TEMPLATES, Permission, RoleTemplate
from apps.core.tenancy import shop_context, system_context
from apps.people.models import Role
from apps.people.services import set_up_shop
from apps.shops.models import Shop, Side
from apps.shops.services import NewSide

pytestmark = pytest.mark.django_db

DAWA_NA_VYAKULA = [NewSide("D", "Dawa"), NewSide("F", "Vyakula")]


def test_new_shop_gets_the_six_roles() -> None:
    shop = set_up_shop(name="Duka la Mfano", code="MFANO", sides=DAWA_NA_VYAKULA)
    with shop_context(shop):
        assert sorted(Side.objects.values_list("code", flat=True)) == ["D", "F"]
        assert {role.template for role in Role.objects.all()} == set(RoleTemplate)


def test_set_up_shop_all_or_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    # A template broken by a typo: the sixth role, the Worker, is refused after the shop, its sides and five roles
    # are written. All of them are taken back, so no shop is left where nobody may act.
    monkeypatch.setitem(ROLE_TEMPLATES, RoleTemplate.WORKER, frozenset({"stock.cont"}))
    with pytest.raises(ValidationError):
        set_up_shop(name="Duka la Mfano", code="MFANO", sides=DAWA_NA_VYAKULA)
    assert not Shop.objects.exists()
    with system_context():
        assert not Side.objects.exists()
        assert not Role.objects.exists()


def test_shops_roles_are_copies() -> None:
    # Each shop holds its own copy. MFANO's owner takes bargaining off MFANO's Order writer; another shop's Order
    # writer keeps it, and so does the template the next new shop copies.
    mfano = set_up_shop(name="Duka la Mfano", code="MFANO", sides=DAWA_NA_VYAKULA)
    jingine = set_up_shop(name="Duka Jingine", code="JINGINE", sides=[NewSide("P", "Pembejeo")])
    with shop_context(mfano):
        writer = Role.objects.get(template=RoleTemplate.ORDER_WRITER)
        Role.objects.filter(pk=writer.pk).update(
            permissions=[code for code in writer.permissions if code != Permission.SALE_BARGAIN]
        )
        assert Permission.SALE_BARGAIN not in Role.objects.get(pk=writer.pk).permissions
    with shop_context(jingine):
        assert Permission.SALE_BARGAIN in Role.objects.get(template=RoleTemplate.ORDER_WRITER).permissions
    assert Permission.SALE_BARGAIN in ROLE_TEMPLATES[RoleTemplate.ORDER_WRITER]
