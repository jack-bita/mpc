"""apps/people/login_doors.py — the login doors: the few reads that run before any shop is open (AUTH-2; 03 §5.4).

Every read of a shop's table goes through the guard, which shows only the shop the visit has opened, and refuses
while none is (ADR-0022). A login can't wait for that: from what a request brings, it must first find which shop the
visit works for. So each login gets one door here, which reads the one thing it needs, a shop's id, and nothing else;
everything after it is read through the guard, inside that shop. Doors are few and named, as system_context() and
the admin's `all_shops` are, so `grep` finds them all. A door starts from no manager, since the guarded one would
refuse, so this file is on the sweep's HAND_BUILT_QUERIES (backend/tests/sweep_lists.py), with its reason; a test
pins that each door reads a shop's id alone (apps/people/tests/test_device_authentication.py).

Today one door, for a device's key (AUTH-2). AUTH-3's password login, which knows a person but not yet which of
their shops they work at now, is the next to need one.
"""

import uuid

from django.db import models

from apps.people.models import Device


def shop_of_device_key(key_hash: str) -> uuid.UUID | None:
    """The shop of the device that holds the key with this hash, or None when no device holds it: a key made up, one
    still waiting for a manager's yes (its hash is on its pairing request, not on a device), or one from a database
    that was reset. Only the shop's id: the login then reads the device itself through the guard, inside that shop."""
    # A query of its own, built on no manager: the guarded `objects` refuses while no shop is open, and that is the
    # very moment a login runs. One column of at most one row, since a key's hash is unique, found in the hash's own
    # index (people_device_key_once, apps/people/models.py), which is not led by `shop` for this reason.
    rows: models.QuerySet[Device] = models.QuerySet(Device)
    shop_id: uuid.UUID | None = rows.filter(key_hash=key_hash).values_list("shop_id", flat=True).first()
    return shop_id
