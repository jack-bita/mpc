"""apps/people/management/commands/open_shop.py — `manage.py open_shop`: the superuser opens a real shop (PPL-13).

Asks the shop's name and code, then each side: its letter, its name, its band and how it sells. It shows all of it
once more, and opens the shop only after a yes, as a side's letter never changes (Jack, PPL-13: 1A). Then set_up_shop
makes the live shop, its sides, each side's stock place and cash drawer, and its six roles, all or nothing. It prints
the shop's code and id, and the command to run next: `owner add`, which makes its owner.

Thin, like a view (ADR-0043): what a shop gets is set_up_shop's (apps/people/services.py), and what is refused is
its rules' (a taken code, two sides with one letter). This file asks, shows, and passes the answers on. It replaces the
admin's Add shop, which saved the shop's row alone, with no sides, and so made a shop that couldn't work (parking lot
item 16, SHOP-2). In `people`, not `shops`: set_up_shop is a `people` service, as it copies the roles in, and `shops`
may not import `people` (ADR-0035).

    python manage.py open_shop                     on a laptop, to try it
    docker compose exec backend python manage.py open_shop     on the server (docs/runbooks/open-a-shop.md)
"""

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from apps.people.management.asking import Asker, refuse_on_demo, refused
from apps.people.services import set_up_shop
from apps.shops.models import SaleFlow, SideBand
from apps.shops.services import NewSide

# How a side sells, by a short word to type: its value ("writer_cashier_loader") is long to type and easy to get wrong.
# A test checks every SaleFlow has a word, so a third way of selling can't be left out of this list.
FLOW_WORDS = {"one": SaleFlow.ONE_SCREEN, "three": SaleFlow.WRITER_CASHIER_LOADER}
FLOW_SHOWN = {
    SaleFlow.ONE_SCREEN: "sells on one screen",
    SaleFlow.WRITER_CASHIER_LOADER: "sells by writer, cashier and loader",
}
# A band is typed as its own value, "blue" or "striped", so a new look the app draws (SHOP-4) shows here by itself.
BAND_WORDS = {band.value: band for band in SideBand}


class Command(BaseCommand):
    help = (
        "Open a real shop: its name, code and sides, each side with its stock place and cash drawer, and the six "
        "roles. Asks each answer in turn; writes nothing until you say yes. Refused on the demo."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        refuse_on_demo()
        ask = Asker(self.stdout)
        name = ask.text("Shop name")
        # Shown as it will be stored: Shop.clean makes the code capitals too, so this changes nothing it would refuse.
        code = ask.text("Shop code, 2 to 10 capital letters").upper()
        sides = self._ask_sides(ask)
        self._show(ask, name, code, sides)
        if not ask.yes("Open this shop?"):
            ask.say("Nothing written.")
            return
        try:
            # A live shop, set_up_shop's default: the demo's own is made by its seed (DATA-1), and a practice shop
            # waits for its card (ADR-0014). One block, which set_up_shop opens itself: if any side is refused, the shop
            # and every side before it are taken back too.
            shop = set_up_shop(name=name, code=code, sides=sides)
        except ValidationError as error:
            raise refused(error) from None
        # The id too: the server's logs name a shop by its id, never its name (backend rule: privacy).
        ask.say(f"Opened {shop.code}, id {shop.pk}.")
        ask.say(f"Next, its owner: python manage.py owner add --shop {shop.code}")

    def _ask_sides(self, ask: Asker) -> list[NewSide]:
        # At least one: a shop does everything on a side (ADR-0001). More until the answer is no.
        sides: list[NewSide] = []
        while True:
            number = len(sides) + 1
            # Capitals, as Side.clean stores them. One letter or not is the side's own rule (side.code_invalid).
            letter = ask.text(f"Side {number}, its letter, as D").upper()
            side_name = ask.text(f"Side {number}, its name")
            band = ask.choice(f"Side {number}, its band", BAND_WORDS, default=SideBand.BLUE.value)
            flow = ask.choice(
                f"Side {number}, how it sells: one = one screen; three = writer, cashier, loader",
                FLOW_WORDS,
                default="one",
            )
            sides.append(NewSide(letter, side_name, sale_flow=flow, band=band))
            if not ask.yes("Another side?"):
                return sides

    def _show(self, ask: Asker, name: str, code: str, sides: list[NewSide]) -> None:
        # Everything once more before the yes (Jack, PPL-13: 1A). A typo in a name can be fixed later, but a side's
        # letter never changes (rename_side): it starts every number printed on the side's receipts (D7).
        ask.say(f"Shop: {name} ({code})")
        for side in sides:
            ask.say(f"  {side.code}  {side.name}: {side.band} band, {FLOW_SHOWN[side.sale_flow]}")
        ask.say("Each side starts switched off, until the owner switches it on in Mipangilio ya duka (ADR-0033).")
        ask.say("A side's letter never changes: it starts every number printed on its receipts.")
