"""apps/sync/registry.py — the registry: every table a shop's devices keep a copy of, with the rows a device gets and
the fields it may see (SYNC-2; 03 §6.1, §6.4).

A shared laptop works offline from its own copy of the shop's lists. This file is the one list of what that copy holds:

    code              rows (apps/sync/selectors.py)    fields (apps/sync/api/serializers.py)
    side              side_rows                        SideRecord
    payment_account   payment_account_rows             PaymentAccountRecord
    staff             staff_rows                       StaffRecord
    setting           setting_rows                     SettingRecord

The bootstrap sends every entry at once (SYNC-2). The pull sends the records that changed (SYNC-3): a line of the
change log names its table by the same code (apps/core/links.py), so the pull finds the line's rows and fields here, and
a record no longer among an entry's rows has left the device's lists. A table missing here never reaches a device, and a
field missing from its serializer never leaves the server.

The order is the bootstrap's: sides first, as the other tables name them. A later card that sends a new table adds its
entry here, with a code in LINK_TYPES, and the services that change it record each change (SYNC-15).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db.models import Model, QuerySet
from rest_framework import serializers

from apps.shops.models import Shop
from apps.sync.api.serializers import PaymentAccountRecord, SettingRecord, SideRecord, StaffRecord
from apps.sync.selectors import payment_account_rows, setting_rows, side_rows, staff_rows


@dataclass(frozen=True)
class Syncable[M: Model]:
    # One table devices keep a copy of. Generic in its model, so mypy checks that the rows and the fields name the same
    # table.
    # The table's link type code, as a line of the change log names it ("side").
    code: str
    # The rows a device of the shop holds. The shop must be the one open (T1).
    rows: Callable[[Shop], QuerySet[M]]
    # The fields a device may see of each row, and nothing more.
    serializer: type[serializers.ModelSerializer[M]]


# Code → entry. Any: the entries name different tables, so the dict can't name one.
REGISTRY: dict[str, Syncable[Any]] = {
    entry.code: entry
    for entry in (
        Syncable("side", side_rows, SideRecord),
        Syncable("payment_account", payment_account_rows, PaymentAccountRecord),
        Syncable("staff", staff_rows, StaffRecord),
        Syncable("setting", setting_rows, SettingRecord),
    )
}
