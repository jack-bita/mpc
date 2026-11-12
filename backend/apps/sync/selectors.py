"""apps/sync/selectors.py — the rows a shop's devices keep a copy of, table by table, and the last change number their
copy is valid at (SYNC-2; 03 §6.1, §6.4).

One function per table the registry sends (apps/sync/registry.py), each answering "which of this shop's rows does a
device hold?": every side; the payment accounts in use; the people at work there; each rule's row in force today and
every later one. The bootstrap sends all of them (SYNC-2); the pull finds a changed record among them, or learns that
it left the lists (SYNC-3). What each row may show is the registry's fields, not this file's. And the change log's two
reads: last_change_number, the cursor a copy is valid at, and changes_after, the lines a pull sends. And where a
laptop's own count stands, last_device_number, which the bootstrap sends so a laptop filled again counts on (SYNC-8).

Each reads inside the shop it is given, which must be the one open (T1), and names it in its query too: under
system_context() the guard shows every shop's rows (03 §5.11).
"""

import uuid
from datetime import date

from django.db.models import Max, Prefetch, QuerySet

from apps.core import settings_registry
from apps.core.models import Change
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import Device, StaffMember, StaffStatus
from apps.people.selectors import shop_today
from apps.shops.models import PaymentAccount, PaymentAccountStatus, Setting, Shop, Side
from apps.sync.models import PushedDocument


def _check_open(shop: Shop) -> None:
    # T1: another shop open would show its own rows through the guard, and the shop filter below would leave none: a
    # device would get an empty shop without a word. A bug in the calling code, so a server error, as get_setting does.
    opened = current_shop()  # raises NoShopSelected when no shop is open
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("A device's rows were asked for a shop that is not the one open.")


def last_change_number(shop: Shop) -> int:
    """The number of the shop's last change, or 0 for a shop with none: a cursor of 0 means nothing read yet, as numbers
    start at 1 (SYNC-1). A copy of the shop read after this holds every change up to it."""
    _check_open(shop)
    # The newest line, found from the end of the log's own index (core_change_one_per_seq: shop, then number), so the
    # read costs the same on a shop's first day and after years of changes.
    last = Change.objects.filter(shop=shop).order_by("-seq").values_list("seq", flat=True).first()
    return last or 0


def changes_after(shop: Shop, cursor: int, limit: int) -> list[tuple[int, str, uuid.UUID]]:
    """The shop's change log after `cursor`, oldest first, `limit` lines at most: each line's number, its table's code
    and its record's id (SYNC-3). Not its `op`: the pull sends each record as it is now, which says that by itself."""
    _check_open(shop)
    # The log's own index (core_change_one_per_seq: shop, then number) holds the lines in this very order, so the read
    # starts at the cursor and stops after `limit` lines: the same cost on a shop's first day and after years of sales.
    lines = (
        Change.objects.filter(shop=shop, seq__gt=cursor)
        .order_by("seq")
        .values_list("seq", "entity", "record_id")[:limit]
    )
    return list(lines)


def side_rows(shop: Shop) -> QuerySet[Side]:
    """Every side of the shop, by its letter. A Dawa laptop may sell on Vyakula too when the person's keys say so
    (02 §5), so a device holds them all; one not yet live is sent too, and the device leaves it off its screens."""
    _check_open(shop)
    return Side.objects.filter(shop=shop).order_by("code")


def payment_account_rows(shop: Shop) -> QuerySet[PaymentAccount]:
    """The accounts money can land in today, each with the sides it serves, by its letter: a side's drawer, a Lipa
    Namba. An archived one is never offered at a counter, so it isn't sent."""
    _check_open(shop)
    # The sides of every account in one more query, however many accounts, read through their links (PaymentAccountSide)
    # and the guard. Ordered by kind and name, so the list reads the same on every device.
    return (
        PaymentAccount.objects.filter(shop=shop, status=PaymentAccountStatus.ACTIVE)
        .prefetch_related(Prefetch("sides", queryset=Side.objects.order_by("code")))
        .order_by("kind", "name", "pk")
    )


def staff_rows(shop: Shop) -> QuerySet[StaffMember]:
    """The people at work at the shop, A to Z by full name: active and suspended. A suspended person is sent, marked so,
    so an offline laptop refuses their PIN as the server does (X2, SYNC-10). Someone who left can never log in here
    again, and someone the superuser switched off (User.is_active) can't while they stay so; neither is sent, as the
    PIN screen shows neither (pin_screen_staff, apps/people/selectors.py)."""
    _check_open(shop)
    # The person in the same query, for the full name, language and font each row shows. Nickname next, then id, so
    # two people of one name keep one order, as on the PIN screen.
    return (
        StaffMember.objects.filter(shop=shop, user__is_active=True)
        .exclude(status=StaffStatus.LEFT)
        .select_related("user")
        .order_by("user__full_name", "display_name", "pk")
    )


def setting_rows(shop: Shop) -> QuerySet[Setting]:
    """Each rule's row in force today, for the whole shop and for each side, and every row that starts later, by rule,
    then by day: an offline laptop then switches to next week's fine on its day (03 §5.8), and gets nothing a newer row
    has replaced. A rule with no row in force works at its default, which the bootstrap sends beside these."""
    _check_open(shop)
    return Setting.objects.filter(pk__in=_rows_in_force_or_later(shop, shop_today(shop))).order_by(
        "key", "effective_from", "created_at", "id"
    )


def _rows_in_force_or_later(shop: Shop, today: date) -> list[uuid.UUID]:
    # The ids of the rows a device needs, worked out as get_setting would answer on each day from today on
    # (apps/shops/selectors.py), so the two can't disagree.
    rules = settings_registry.REGISTRY
    # One row per rule, side and day: the one written last, as a fix is one more row for the same day (T2). DISTINCT ON
    # keeps the first row of each group in this order, so the newest is first; the same tie-break as get_setting's.
    # Oldest day first within each rule and side, for the loop below.
    newest_each_day = (
        Setting.objects.filter(shop=shop, key__in=list(rules))
        .order_by("key", "side_id", "effective_from", "-created_at", "-id")
        .distinct("key", "side_id", "effective_from")
        .values_list("id", "key", "side_id", "effective_from")
    )
    in_force: dict[tuple[str, uuid.UUID | None], uuid.UUID] = {}
    later: list[uuid.UUID] = []
    for row_id, key, side_id, day in newest_each_day:
        # A side's row of a rule kept for the whole shop: get_setting never reads it (Setting.clean() refuses it, but
        # code that saves without full_clean could write one), so no device should either.
        if side_id is not None and rules[key].scope is not settings_registry.Scope.SIDE:
            continue
        if day <= today:
            # Days come oldest first, so the last one seen by today is the one in force.
            in_force[(key, side_id)] = row_id
        else:
            later.append(row_id)
    return [*in_force.values(), *later]


def highest_pushed_number(device: Device) -> int:
    """The highest number among this laptop's records in the answer log, 0 for a laptop that sent none."""
    highest = PushedDocument.objects.filter(device=device).aggregate(highest=Max("device_seq"))["highest"]
    return highest or 0


def last_device_number(device: Device) -> int:
    """Where the laptop's count stands, the number its next record follows (SYNC-8): the one the server kept (SYNC-5),
    else the highest in the answer log, for a laptop that pushed before the server kept one, else 0.

    The bootstrap sends it. A browser that frees its storage wipes the laptop's database, its count with it, but keeps
    the key's cookie: the server's number is the one that survives, so a laptop filled again carries on from it and
    never numbers from 1 again, which would flag its records and take a sale's number twice (SYNC-5's note).

    Read without the lock the push takes (lock_device_numbers): a laptop being filled sends nothing meanwhile, as it
    saves nothing before its bootstrap."""
    kept = Device.objects.filter(pk=device.pk).values_list("last_device_seq", flat=True).get()
    return kept if kept is not None else highest_pushed_number(device)
