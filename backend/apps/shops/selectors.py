"""apps/shops/selectors.py — reads of the shops tables that other code builds on (03 §5.2).

Three so far. get_setting answers "what is this rule on this day?" for a shop, and for one of its sides
when one is given (D13, ADR-0013). Every later card reads its rules through it: the attendance day reads
the on-time cut-off and the late fine, a drawer count its tolerance, and so on. shop_today answers "which
day is it at this shop?", the day a rule's new value may start from at the earliest (SHOP-3). It lives
here, with the shop, so `shops` can ask it too: `shops` sits below `people` and may not import it (ADR-0043).
shop_rules lists every rule as the settings page shows it (SHOP-3): its value today, and its rows.

The answer comes from the shop's Setting rows (apps/shops/models.py), or, when there is no row, from the
list of rules in core (apps/core/settings_registry.py): a new shop works with every rule at its default.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.core.settings_registry import KEYS, Scope, SettingKey
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


def shop_today(shop: Shop) -> date:
    # Today in the shop's own time zone (02 §1), not the server's UTC: at 01:00 in Arusha, UTC is still on yesterday.
    return timezone.localdate(timezone=ZoneInfo(shop.timezone))


@dataclass(frozen=True)
class Rule:
    # One line of the settings page: a rule for the whole shop (`side` None), or a side's rule for one side. Its value
    # today and its default in the kind's one written form ("1000.00", "07:35", "true"), as the rows hold theirs.
    key: str
    kind: str
    scope: Scope
    side: Side | None
    default: str
    value: str
    # Every row that counts for it, newest first, as get_setting orders them: the rows of its side, and the shop's.
    rows: list[Setting]


def shop_rules(shop: Shop, *, rows: Iterable[Setting], sides: Sequence[Side], on: date) -> list[Rule]:
    """Every rule in the registry, in its order, for the settings page: a shop's rule once, a side's rule once for each
    of `sides`, each with its value on the day `on` and its rows. `rows` and `sides` are those the person may see (the
    route keeps to them, PPL-5); with no side at all, nothing, as such a person sees no row of the whole shop either."""
    if not sides:
        return []
    # Newest first, with get_setting's tie-break: on one day the row written last wins (T2).
    ordered = sorted(rows, key=lambda row: (row.effective_from, row.created_at, row.id), reverse=True)
    rules: list[Rule] = []
    for key in KEYS:
        # A side's rule is set one side at a time (SHOP-3), so it has a line per side. A shop row of one, which only
        # code that skips set_setting could write, still counts behind the side's own (get_setting), so it shows in
        # each side's rows too, marked as the shop's by its empty side: the page then never hides why a value is so.
        for side in [None] if key.scope is Scope.SHOP else sides:
            side_ids = {None} if side is None else {None, side.pk}
            rules.append(
                Rule(
                    key=key.key,
                    kind=key.kind.code,
                    scope=key.scope,
                    side=side,
                    default=key.kind.to_text(key.default),
                    # The value as every other reader finds it, through get_setting itself, so the page and the pay
                    # run can't disagree. A short list, so a few small reads.
                    value=key.kind.to_text(get_setting(key, shop, side, on=on)),
                    rows=[row for row in ordered if row.key == key.key and row.side_id in side_ids],
                )
            )
    return rules
