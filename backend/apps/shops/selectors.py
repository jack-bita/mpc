"""apps/shops/selectors.py — reads of the shops tables that other code builds on (03 §5.2).

For now one: get_setting, which answers "what is this rule on this day?" for a shop, and for one of its
sides when one is given (D13, ADR-0013). Every later card reads its rules through it: the attendance day
reads the on-time cut-off and the late fine, a drawer count its tolerance, and so on.

The answer comes from the shop's Setting rows (apps/shops/models.py), or, when there is no row, from the
list of rules in core (apps/core/settings_registry.py): a new shop works with every rule at its default.
"""

from datetime import date, datetime

from apps.core.settings_registry import Scope, SettingKey
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.shops.models import Setting, Shop, Side


def get_setting[T](key: SettingKey[T], shop: Shop, side: Side | None = None, *, on: date) -> T:
    """The value of `key` in force at `shop` on the day `on`: the side's own row if it has one, else the
    shop's row, else the key's default. A row counts from its own day (`effective_from`) on."""
    # `on` comes after the *, so every call names it: get_setting(LATE_FINE, shop, on=day). It has no
    # default of "today", because whose today? The server's clock runs in UTC, and the shop's day is in
    # its own timezone (02 §1): the caller knows which day it means.

    # Three bugs in the calling code, each of which would quietly give a wrong rule, so each raises.
    # A shop must be open, and be this one: current_shop() raises NoShopSelected when none is. Another
    # shop's rows would be hidden by the guard (CORE-2), and the default would come back without a word,
    # so fail closed instead (ADR-0022). A system job, in system_context(), may read any shop.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("get_setting was given a shop that is not the one open.")
    # T1: a side of another shop would mix two shops' rules.
    if side is not None and side.shop_id != shop.pk:
        raise ShopMismatch("get_setting was given a side of another shop.")
    # In Python a datetime is a kind of date, so mypy lets one through; but it is a moment, not the
    # shop's day. In UTC, 22:00 on 31 Oct is already 1 Nov in Tanzania.
    if isinstance(on, datetime):
        raise TypeError("get_setting needs the shop's business date, not a datetime.")

    # This shop's rows of this key that have started by `on`, newest first. `shop=` although the guard
    # filters too: in system_context() the guard shows every shop's rows. On one day the row written last
    # wins, because a fix is a new row (T2). `created_at` is the server's clock when the row was saved;
    # the id is made by the client (CORE-6), so its order follows the client's clock, and it only settles
    # two rows saved at the very same moment.
    rows = Setting.objects.filter(shop=shop, key=key.key, effective_from__lte=on).order_by(
        "-effective_from", "-created_at", "-id"
    )
    # A side's own row beats the shop's row, even an older one (02 §4). Only for a key whose scope allows
    # side rows: Setting.clean() refuses them for a shop-wide key, but code that saves without full_clean
    # skips that check, and the database can't hold it. So a shop-wide key goes straight to the shop's row.
    row = rows.filter(side=side).first() if side is not None and key.scope is Scope.SIDE else None
    if row is None:
        row = rows.filter(side__isnull=True).first()
    if row is None:
        return key.default
    # The row holds text in its kind's one form; the kind turns it back into a Decimal, a time, and so on.
    return key.kind.parse(row.value)
