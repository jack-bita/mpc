"""apps/people/tests/test_open_shop.py — `manage.py open_shop`: the superuser opens a real shop (PPL-13).

The command asks the shop's name and code, then each side, shows it all once more, and after a yes calls set_up_shop,
which makes everything a shop needs to work, all or nothing:

    open_shop: Duka la Mfano, MFANO, D Dawa, F Vyakula, yes

    MFANO (live)
    ├── Dawa (D), Vyakula (F)    → each with its stock place and cash drawer, switched off (ADR-0033)
    └── Owner, Manager, Seller, Order writer, Cashier, Worker

Each test types its answers in through the `keyboard` fixture (conftest.py). Fake shops only: the repo is public.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest_django import Settings

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context, system_context
from apps.people.management.commands.open_shop import FLOW_SHOWN, FLOW_WORDS
from apps.people.models import Role
from apps.people.services import set_up_shop
from apps.shops.models import (
    PaymentAccount,
    PaymentAccountKind,
    PaymentAccountSide,
    SaleFlow,
    Shop,
    ShopKind,
    Side,
    SideBand,
    StockLocation,
)
from apps.shops.services import NewSide
from tests.keyboard import Keyboard

pytestmark = pytest.mark.django_db

# The answers for MFANO with two sides: Dawa takes the defaults (blue, one screen) with a blank answer each, as Enter
# alone does; Vyakula is striped and sells by writer, cashier and loader. Then no more sides, and yes.
DAWA = ("D", "Dawa", "", "")
VYAKULA = ("F", "Vyakula", "striped", "three")
TWO_SIDES = ("Duka la Mfano", "MFANO", *DAWA, "y", *VYAKULA, "n")


def open_shop() -> str:
    # The command as the superuser runs it; what it said, for the test to read.
    out = StringIO()
    call_command("open_shop", stdout=out)
    return out.getvalue()


def test_open_shop_makes_the_shop_its_sides_and_six_roles(keyboard: Keyboard) -> None:
    keyboard.type(*TWO_SIDES, "y")

    said = open_shop()

    shop = Shop.objects.get(code="MFANO")
    # A live shop: the demo's is the seed's, and a practice shop waits for its card (ADR-0014).
    assert (shop.name, shop.kind) == ("Duka la Mfano", ShopKind.LIVE)
    with shop_context(shop):
        sides = {side.code: side for side in Side.objects.all()}
        # Each side as typed, and switched off until the owner switches it on (ADR-0033).
        assert sorted((s.code, s.name, s.band, s.sale_flow, s.is_live) for s in sides.values()) == [
            ("D", "Dawa", SideBand.BLUE, SaleFlow.ONE_SCREEN, False),
            ("F", "Vyakula", SideBand.STRIPED, SaleFlow.WRITER_CASHIER_LOADER, False),
        ]
        # Each side with its own stock place and cash drawer (ADR-0001, ADR-0002), made by set_up_shop.
        side_ids = sorted(side.pk for side in sides.values())
        assert sorted(location.side_id for location in StockLocation.objects.all()) == side_ids
        drawers = PaymentAccount.objects.filter(kind=PaymentAccountKind.CASH_DRAWER).values("pk")
        drawer_sides = PaymentAccountSide.objects.filter(account__in=drawers).values_list("side_id", flat=True)
        assert sorted(drawer_sides) == side_ids
        # The six roles, so the owner made next has one to be given (owner add).
        assert {role.template for role in Role.objects.all()} == set(RoleTemplate)
    # The code and the id, and what to run next.
    assert f"Opened MFANO, id {shop.pk}." in said
    assert "python manage.py owner add --shop MFANO" in said


def test_open_shop_shows_everything_before_the_yes(keyboard: Keyboard) -> None:
    # Jack, PPL-13: 1A. A side's letter never changes, so a typo must be caught before the shop is made.
    keyboard.type(*TWO_SIDES, "y")

    said = open_shop()

    shown = said[: said.index("Opened")]
    assert "Shop: Duka la Mfano (MFANO)" in shown
    assert "D  Dawa: blue band, sells on one screen" in shown
    assert "F  Vyakula: striped band, sells by writer, cashier and loader" in shown
    assert "letter never changes" in shown
    assert keyboard.asked[-1] == "Open this shop? [y/N]: "


@pytest.mark.parametrize("answer", ["n", "", "ndio"])
def test_open_shop_writes_nothing_without_a_yes(keyboard: Keyboard, answer: str) -> None:
    # Only y or yes opens it: a blank Enter, or a word that isn't yes, is no.
    keyboard.type(*TWO_SIDES, answer)

    said = open_shop()

    assert "Nothing written." in said
    assert not Shop.objects.exists()


def test_a_code_typed_in_small_letters_is_stored_in_capitals(keyboard: Keyboard) -> None:
    # Spaces and small letters, as people type: the shop's code is stored, and shown before the yes, as MFANO.
    keyboard.type("Duka la Mfano", " mfano ", "d", "Dawa", "", "", "n", "y")

    said = open_shop()

    assert "Shop: Duka la Mfano (MFANO)" in said
    with shop_context(Shop.objects.get(code="MFANO")):
        assert list(Side.objects.values_list("code", flat=True)) == ["D"]


def test_a_blank_answer_or_a_word_off_the_list_is_asked_again(keyboard: Keyboard) -> None:
    # The shape of an answer is the command's to check: nothing was typed that a service could judge.
    keyboard.type("", "Duka la Mfano", "MFANO", "D", "Dawa", "green", "STRIPED", "two", "three", "n", "y")

    said = open_shop()

    assert said.count("An answer is needed.") == 1
    assert "Type one of: blue, striped." in said
    assert "Type one of: one, three." in said
    with shop_context(Shop.objects.get(code="MFANO")):
        side = Side.objects.get()
        # Capitals are taken as the word, as STRIPED is striped.
        assert (side.band, side.sale_flow) == (SideBand.STRIPED, SaleFlow.WRITER_CASHIER_LOADER)


def test_a_taken_code_is_refused_and_writes_nothing(keyboard: Keyboard) -> None:
    # Another shop holds MFANO. Refused by the shop's own rule (shop.code_taken), with its code and words, at the end,
    # as the command copies no rule; nothing of the second shop is written.
    taken = set_up_shop(name="Duka la Kwanza", code="MFANO", sides=[NewSide("D", "Dawa")])
    keyboard.type(*TWO_SIDES, "y")

    with pytest.raises(
        CommandError, match=r"Refused, nothing written:\n  shop\.code_taken: Another shop has this code\."
    ):
        open_shop()

    assert list(Shop.objects.all()) == [taken]
    with system_context():
        assert Side.objects.count() == 1
        assert Role.objects.count() == len(RoleTemplate)


def test_two_sides_with_one_letter_are_refused_and_write_nothing(keyboard: Keyboard) -> None:
    # The second side is refused after the shop and the first side are written: set_up_shop's one block takes them all
    # back (all or nothing), so there is never a shop with half its sides.
    keyboard.type("Duka la Mfano", "MFANO", *DAWA, "y", "D", "Vyakula", "", "", "n", "y")

    with pytest.raises(CommandError, match=r"side\.code_taken: Another side of this shop has this letter\."):
        open_shop()

    assert not Shop.objects.exists()
    with system_context():
        assert not Side.objects.exists()


def test_open_shop_is_refused_on_the_demo(keyboard: Keyboard, settings: Settings) -> None:
    # The demo's seed makes its own shop (DATA-1). Refused before the first question: nothing is typed here, and the
    # keyboard fails the test if anything is asked.
    settings.DEMO_SEED = True

    with pytest.raises(CommandError, match="Refused on the demo"):
        open_shop()

    assert not Shop.objects.exists()
    assert keyboard.asked == []


def test_every_way_of_selling_has_a_word_to_type_and_to_show() -> None:
    # A third way of selling, added to SaleFlow by a later card, can't be left out of the command's lists.
    assert set(FLOW_WORDS.values()) == set(SaleFlow)
    assert set(FLOW_SHOWN) == set(SaleFlow)
