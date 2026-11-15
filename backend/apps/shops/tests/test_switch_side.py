"""apps/shops/tests/test_switch_side.py — switch_side: the owner turns a side on or off (SHOP-3, ADR-0033).

A new side starts off, so it never reaches the counters by surprise; the owner switches it on once he agrees to start
using it. A switch is an edit of the side, so it keeps the rules every edit keeps (apps/core/editing.py): an old copy is
refused, and so is someone of another shop (T1). On the demo a person's switch is fixed, as its logins are: visitors
share the manager's login, and one who switched Dawa off would stop every later visitor's one-tap demo. The system,
which sets the demo up, still switches its sides on (apps/demo/services.py). The staff members come from
backend/conftest.py and are typed Any: `shops` may not name `people`'s StaffMember (ADR-0043).
"""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from pytest_django import Settings

from apps.core.editing import VersionConflict
from apps.core.tenancy import ShopMismatch, shop_context
from apps.shops.models import Shop, Side
from apps.shops.services import switch_side

pytestmark = pytest.mark.django_db


def stored(shop: Shop, side: Side) -> Side:
    # The side as saved, read again from the database: a refusal must have written nothing.
    with shop_context(shop):
        return Side.objects.get(pk=side.pk)


def test_switch_side_turns_a_side_on_and_off(shop_a: Shop, side_a: Side, staff_a: Any) -> None:
    # Dawa starts off (SHOP-2). The owner switches it on, then off again: each switch is an edit, with the next version
    # and who made it, which the edit history keeps too (ADR-0036).
    assert side_a.is_live is False
    with shop_context(shop_a):
        on = switch_side(side_a, version=side_a.version, is_live=True, by=staff_a)
        off = switch_side(on, version=on.version, is_live=False, by=staff_a)

    assert (on.is_live, on.version) == (True, 2)
    saved = stored(shop_a, side_a)
    assert (saved.is_live, saved.version, saved.updated_by_id) == (False, off.version, staff_a.pk)


def test_switch_side_refuses_an_old_copy(shop_a: Shop, side_a: Side) -> None:
    # The owner and a manager both open the sides at version 1. The owner switches Dawa on; the manager's switch, made
    # on the old copy, is refused, instead of silently undoing the owner's (02 §1).
    with shop_context(shop_a):
        switch_side(side_a, version=1, is_live=True, by=None)
        with pytest.raises(VersionConflict):
            switch_side(side_a, version=1, is_live=False, by=None)
    assert stored(shop_a, side_a).is_live is True


def test_switch_side_refuses_someone_of_another_shop(shop_a: Shop, side_a: Side, staff_b: Any) -> None:
    # T1: shop B's staff can't switch shop A's side. A bug in the calling code, so it raises, and Dawa stays off.
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        switch_side(side_a, version=1, is_live=True, by=staff_b)
    assert stored(shop_a, side_a).is_live is False


def test_side_switch_fixed_on_demo(shop_a: Shop, side_a: Side, staff_a: Any, settings: Settings) -> None:
    # On the demo (DEMO_SEED, config/settings/base.py), a visitor who switched Dawa off would stop every later one-tap
    # demo, whose laptops are on Dawa, until the next morning's seed. So a person's switch is refused there, before
    # anything is written, as their passwords and PINs are (demo.logins_fixed).
    settings.DEMO_SEED = True
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        switch_side(side_a, version=1, is_live=True, by=staff_a)
    assert [error.code for error in refused.value.error_list] == ["demo.sides_fixed"]
    assert stored(shop_a, side_a).is_live is False


def test_the_system_switches_sides_on_the_demo(shop_a: Shop, side_a: Side, settings: Settings) -> None:
    # The seed sets the demo up as the system (`by` None), as it sets the PINs: it switches the sides on, so the demo
    # shows a shop at work.
    settings.DEMO_SEED = True
    with shop_context(shop_a):
        switch_side(side_a, version=1, is_live=True, by=None)
    assert stored(shop_a, side_a).is_live is True
