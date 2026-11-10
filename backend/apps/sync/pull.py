"""apps/sync/pull.py — the pull: what changed in a shop after the last change its device read, each record as it is
now (SYNC-3; 03 §6.4).

A Dawa laptop keeps a copy of the shop's lists and the number of the last change it read, its cursor. It asks for what
came after, and gets one page:

    the change log                       the page for a laptop at 41
    42  staff  Juma suspended            {"seq": 42, "entity": "staff", "id": …, "op": "upsert", "data": Juma's row}
    43  staff  Asha left                 {"seq": 43, "entity": "staff", "id": …, "op": "archive", "data": null}
                                         "cursor": 43, the number to ask from next
                                         "has_more": false, so nothing waits after 43

A line names a record and holds none of its data, so each record is read as it is now, through the registry
(apps/sync/registry.py): its rows and its fields, the bootstrap's own, so a pull and a bootstrap can't disagree. A
record no longer among its table's rows has left the device's lists (a person who left or was switched off), so it goes
as `archive`, whatever its line said; one still among them goes as `upsert`, with its row. The record decides, not the
line: Neema switched off and on again is back on the PIN screen at both of her lines.

The one rule this file keeps is the order of its reads: the lines first, then the records. Each query sees what had
committed when it started (PostgreSQL's default), and numbers are taken in commit order (SYNC-1), so every change up to
the page's last line had committed before the records were read: each record is at least as new as its last line here.
A change that commits between the two reads may show in a record already, under an earlier line, and comes again with
its own line on a later page, which does no harm. Read the other way round, a page could hold a line whose change its
record doesn't show yet, and the laptop, moving its cursor past that line, would keep the old row for good. The ids come
from the lines, so the records can't be read first.

Every line is sent once, in order, a record changed twice twice, each time as it is now: the laptop applies a page in
order, so the last one wins. A line of a table no device keeps (one a later card records before it joins the registry)
is passed over, but counted: the cursor moves past it, so a laptop never stops on it. So a page may hold fewer than
1,000 changes while more wait, and says itself whether they do (`has_more`): a laptop that asked again only after a
page of 1,000 would stop early, and wait for its next sync for the rest.
"""

import uuid
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.core.models import ChangeOp
from apps.shops.models import Shop
from apps.sync.registry import REGISTRY
from apps.sync.selectors import changes_after

# The most lines one page holds (03 §6.4): an answer a slow line can carry, and a device can save in one go. A laptop
# away for a week asks again at once while a page says more wait, from each page's cursor.
PAGE_SIZE = 1000


def page(shop: Shop, cursor: int) -> dict[str, Any]:
    """One page of the pull for a device of `shop`, which must be the shop open, at `cursor`: the changes after it, in
    order; the number to ask from next (`cursor` again when nothing came); whether more wait after it; the server's
    time; and the oldest app version that may still sync."""
    # First, before any record: see the file's header. One line more than a page holds: if it is there, more wait. It
    # is left for the next page, which reads it again.
    lines = changes_after(shop, cursor, PAGE_SIZE + 1)
    has_more = len(lines) > PAGE_SIZE
    lines = lines[:PAGE_SIZE]
    now = _records_now(shop, lines)
    changes = []
    for seq, entity, record_id in lines:
        if entity not in REGISTRY:
            continue  # a table no device keeps: nothing to send, but the cursor still passes it
        data = now[entity].get(record_id)
        op = ChangeOp.UPSERT if data is not None else ChangeOp.ARCHIVE
        changes.append({"seq": seq, "entity": entity, "id": record_id, "op": op.value, "data": data})
    return {
        "changes": changes,
        # The last line read, sent or passed over: the next page starts after it.
        "cursor": lines[-1][0] if lines else cursor,
        # Ask again at once, from that cursor. The count of changes can't say it: lines passed over aren't sent.
        "has_more": has_more,
        # For the device's clock: it keeps how far its own is off, and stamps its documents by it (03 §6.6). Every
        # page, an empty one too, so a quiet shop still checks its clock at every sync.
        "server_time": timezone.now(),
        # The oldest app that may still sync (03 §6.8): an older one sends its outbox, then updates. None: any app may.
        "min_app_version": settings.MIN_APP_VERSION,
    }


def _records_now(shop: Shop, lines: list[tuple[int, str, uuid.UUID]]) -> dict[str, dict[uuid.UUID, Any]]:
    # Each record the lines name, by table and id, as a device of the shop may see it now: one read per table, for all
    # its records at once, however many lines name them, in the registry's order. A record missing from its table's
    # rows has left the device's lists, and the page sends it as `archive`.
    wanted: dict[str, set[uuid.UUID]] = {}
    for _seq, entity, record_id in lines:
        wanted.setdefault(entity, set()).add(record_id)
    found: dict[str, dict[uuid.UUID, Any]] = {}
    for code, entry in REGISTRY.items():
        if code in wanted:
            # The rows the bootstrap would send, narrowed to these ids, through the same fields.
            rows = entry.rows(shop).filter(pk__in=wanted[code])
            found[code] = {row.pk: entry.serializer(row).data for row in rows}
    return found
