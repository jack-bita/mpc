"""apps/shops/services.py — every write to the shops tables, one function per action (ADR-0015).

For now one action: create_shop, which makes a new shop with all it needs before it can work: its sides
(ADR-0001), and for each side a default stock location (ADR-0002) and a cash drawer. It runs in one
transaction and refuses a broken rule with a ValidationError that carries a code (ADR-0032); CORE-6's
error handler will turn it into the API's error shape.

`shops` is layer 1 and may not import `people`, not even as a type (ADR-0035). create_shop needs nothing
from it: a new shop has no staff yet, so every row it makes has `created_by` empty, like any row the
system makes (02 §1). How a new shop gets its role templates, which live in `people`, is PPL-3's to
decide; one way is a `people` service that calls this one, then copies them in.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core.tenancy import shop_context
from apps.shops.models import (
    PaymentAccount,
    PaymentAccountKind,
    PaymentAccountSide,
    SaleFlow,
    Shop,
    Side,
    StockLocation,
)


@dataclass(frozen=True)
class NewSide:
    # One side as create_shop is asked for it: NewSide("D", "Dawa"). Frozen: a value handed in, which
    # nothing changes on the way.
    code: str
    name: str
    sale_flow: SaleFlow = SaleFlow.ONE_SCREEN


def create_shop(*, name: str, code: str, sides: Sequence[NewSide]) -> Shop:
    """Make a live shop with its sides, and for each side a default stock location and a cash drawer, all
    or nothing. For the superuser and system jobs. Always `kind=live` for now: the demo seed (DATA-1) and
    practice shops (ADR-0014) will need a `kind` argument, which the first of them adds."""
    # A shop does everything on a side (ADR-0001): with none it could neither sell nor count. Refused
    # before anything is written.
    if not sides:
        raise ValidationError("A shop needs at least one side.", code="shop.no_sides")
    # One transaction: if any row below is refused, the rows already written are taken back too, so
    # there is never a shop with half its sides set up.
    with transaction.atomic():
        # Two shops made with the same code at the very same moment can both pass full_clean; the unique
        # index on `code` then refuses the second.
        shop = _saved(Shop(name=name, code=code))
        # The new shop is opened for the rows below, because their full_clean reads through the guarded
        # `objects` (CORE-2). No caller could have opened it: it didn't exist yet. The block hands back
        # whatever shop was open before.
        with shop_context(shop):
            for new_side in sides:
                _add_side(shop, new_side)
    return shop


def _add_side(shop: Shop, new_side: NewSide) -> None:
    # T1 holds by construction: every row gets this shop, and links only to rows made here for it.
    side = _saved(Side(shop=shop, code=new_side.code, name=new_side.name, sale_flow=new_side.sale_flow))
    # The location and the drawer take the side's name ("Dawa"); the screens add the translated kind,
    # so the server makes up no words (ADR-0032).
    _saved(StockLocation(shop=shop, side=side, name=side.name, is_default=True))
    drawer = _saved(PaymentAccount(shop=shop, kind=PaymentAccountKind.CASH_DRAWER, name=side.name))
    _saved(PaymentAccountSide(shop=shop, account=drawer, side=side))


def _saved[M: models.Model](row: M) -> M:
    # Every field, clean() and the rules in Meta, before the row is written: " mfano " is stored as
    # MFANO, and a clash, such as a second side D, comes back as a code instead of a database error.
    row.full_clean()
    row.save()
    return row
