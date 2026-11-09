"""apps/sync/bootstrap.py — the bootstrap: a copy of the whole shop for a new or reset device, with the change number
it is valid at (SYNC-2; 03 §6.4).

A new Dawa laptop asks once and gets every table in the registry (apps/sync/registry.py), each rule's default, and the
cursor: the shop's last change number. Its pulls then ask for what came after that number (SYNC-3).

The one rule this file keeps is the order of its reads: the cursor first, then the rows.

    cursor first (this file)                  rows first (wrong)
    reads the cursor: 41                      reads the sides: "Dawa"
    the owner's rename commits, as 42         the owner's rename commits, as 42
    reads the sides: "Dawa Kuu"               reads the cursor: 42
    pulls after 41: the rename again          pulls after 42: never sees the rename
    (harmless: the same row twice)            (the laptop says "Dawa" for good)

Under PostgreSQL's default isolation each query sees what was committed when it starts, so a change can land between any
two of these reads. Numbers are taken in commit order (SYNC-1): every change up to the cursor had committed when the
cursor was read, so every read after it sees them. One REPEATABLE READ transaction would do too, but it must be the
transaction's first statement, which no test transaction allows, and a hand-written SET would join the sweep's RAW_SQL.
"""

from typing import Any

from apps.core.settings_registry import KEYS
from apps.shops.models import Shop
from apps.sync.registry import REGISTRY
from apps.sync.selectors import last_change_number


def snapshot(shop: Shop) -> dict[str, Any]:
    """The bootstrap's answer for a device of `shop`, which must be the shop open: the cursor, then each registry
    table's rows by its code, in the registry's order, then each rule's default (setting_keys)."""
    # First, before any row: see the file's header.
    answer: dict[str, Any] = {"cursor": last_change_number(shop)}
    for code, entry in REGISTRY.items():
        # `.data` reads the rows now, in this order, each table after the cursor: a lazy read left for later would
        # still come after it, but here the order is plain to see.
        answer[code] = entry.serializer(entry.rows(shop), many=True).data
    answer["setting_keys"] = setting_keys()
    return answer


def setting_keys() -> list[dict[str, str]]:
    """Every rule in the list in core (apps/core/settings_registry.py), with its kind's name, so a device knows how to
    read its stored text ("time": "07:35"), where it may be set, and its default, as the rule's kind writes it
    ("1000.00", "07:35"). A device works a rule out as get_setting does (apps/shops/selectors.py): the side's row, else
    the shop's, else this default; a new shop has no rows at all. Code, not a shop's data, so the same for every shop;
    a rule a later release adds reaches a device at its next bootstrap (SYNC-13's note)."""
    return [
        {"key": key.key, "kind": key.kind.code, "scope": key.scope.value, "default": key.kind.to_text(key.default)}
        for key in KEYS
    ]
