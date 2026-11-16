"""apps/shops/tests/test_set_side_band.py — set_side_band: the owner picks the band under a side's top bar (SHOP-4).

A worker tells the sides apart at a glance by the band under the bar: blue for one, striped for the other. A side starts
blue (Side.band); the owner changes it on the settings page. A band change is an edit of the side, so it keeps the rules
every edit keeps (apps/core/editing.py): an old copy is refused, and so is someone of another shop (T1). On the demo a
person's change is refused, as a rename is (Jack, 16 Nov 2026): visitors share the manager's login, and one visitor's
colour would greet every visitor after them until the morning's seed. The staff members come from backend/conftest.py
and are typed Any: `shops` may not name `people`'s StaffMember (ADR-0043).
"""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from pytest_django import Settings

from apps.core.editing import VersionConflict
from apps.core.tenancy import ShopMismatch, shop_context
from apps.shops.models import Shop, Side, SideBand
from apps.shops.services import set_side_band

pytestmark = pytest.mark.django_db


def stored(shop: Shop, side: Side) -> Side:
    # The side as saved, read again from the database: a refusal must have written nothing.
    with shop_context(shop):
        return Side.objects.get(pk=side.pk)


def test_set_side_band_changes_the_band(shop_a: Shop, side_a: Side, staff_a: Any) -> None:
    # Dawa starts blue. The owner makes it striped, then blue again: each change is an edit, with the next version and
    # who made it, which the edit history keeps too (ADR-0036).
    assert side_a.band == SideBand.BLUE
    with shop_context(shop_a):
        striped = set_side_band(side_a, version=side_a.version, band=SideBand.STRIPED, by=staff_a)
        blue = set_side_band(striped, version=striped.version, band=SideBand.BLUE, by=staff_a)

    assert (striped.band, striped.version) == (SideBand.STRIPED, 2)
    saved = stored(shop_a, side_a)
    assert (saved.band, saved.version, saved.updated_by_id) == (SideBand.BLUE, blue.version, staff_a.pk)


def test_set_side_band_refuses_an_old_copy(shop_a: Shop, side_a: Side) -> None:
    # The owner and a manager both open the sides at version 1. The owner makes Dawa striped; the manager's change, made
    # on the old copy, is refused, instead of silently undoing the owner's (02 §1).
    with shop_context(shop_a):
        set_side_band(side_a, version=1, band=SideBand.STRIPED, by=None)
        with pytest.raises(VersionConflict):
            set_side_band(side_a, version=1, band=SideBand.BLUE, by=None)
    assert stored(shop_a, side_a).band == SideBand.STRIPED


def test_set_side_band_refuses_a_band_no_screen_draws(shop_a: Shop, side_a: Side) -> None:
    # A third word would reach every laptop as a band no screen can draw. editing() checks the side before it saves
    # (full_clean), so it is refused on its field, and nothing is written.
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        set_side_band(side_a, version=1, band="green", by=None)  # type: ignore[arg-type]
    assert [error.code for error in refused.value.error_dict["band"]] == ["invalid_choice"]
    assert stored(shop_a, side_a).band == SideBand.BLUE


def test_set_side_band_refuses_someone_of_another_shop(shop_a: Shop, side_a: Side, staff_b: Any) -> None:
    # T1: shop B's staff can't change shop A's side. A bug in the calling code, so it raises, and Dawa stays blue.
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        set_side_band(side_a, version=1, band=SideBand.STRIPED, by=staff_b)
    assert stored(shop_a, side_a).band == SideBand.BLUE


def test_side_band_fixed_on_demo(shop_a: Shop, side_a: Side, staff_a: Any, settings: Settings) -> None:
    # On the demo (DEMO_SEED, config/settings/base.py), a visitor who made Dawa striped would show every later visitor
    # two striped sides until the next morning's seed. So a person's change is refused there, before anything is
    # written, as a rename is (demo.sides_fixed).
    settings.DEMO_SEED = True
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        set_side_band(side_a, version=1, band=SideBand.STRIPED, by=staff_a)
    assert [error.code for error in refused.value.error_list] == ["demo.sides_fixed"]
    assert stored(shop_a, side_a).band == SideBand.BLUE


def test_the_system_sets_a_band_on_the_demo(shop_a: Shop, side_a: Side, settings: Settings) -> None:
    # The system (`by` None), which is how the seed sets the demo up, still may.
    settings.DEMO_SEED = True
    with shop_context(shop_a):
        set_side_band(side_a, version=1, band=SideBand.STRIPED, by=None)
    assert stored(shop_a, side_a).band == SideBand.STRIPED
