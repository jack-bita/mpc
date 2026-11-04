"""apps/people/login_doors.py — the login doors: the few reads that run before any shop is open (AUTH-2; 03 §5.4).

Every read of a shop's table goes through the guard, which shows only the shop the visit has opened, and refuses
while none is (ADR-0022). A login can't wait for that: from what a request brings, it must first find which shop the
visit works for. So each login gets one door here, which reads the one thing it needs, a shop's id, and nothing else;
everything after it is read through the guard, inside that shop. Doors are few and named, as system_context() and
the admin's `all_shops` are, so `grep` finds them all. A door starts from no manager, since the guarded one would
refuse, so this file is on the sweep's HAND_BUILT_QUERIES (backend/tests/sweep_lists.py), with its reason; a test
pins that each door reads a shop's id alone (apps/people/tests/test_device_authentication.py,
apps/people/tests/test_staff_session.py).

Two doors: a device's key (AUTH-2), and a person logged in with a password (AUTH-3), who is known by their session
but belongs to no shop until their job is found.
"""

import uuid

from django.db import models

from apps.people.models import Device, StaffMember, StaffStatus


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


def shops_of_person(user_id: uuid.UUID) -> list[uuid.UUID]:
    """The shops where this person has a current job, one that isn't `left`: suspended ones too, since the login must
    say why it refuses them. Only the shops' ids: the login then reads the job itself through the guard, inside that
    shop. Two at most, as a login needs to tell only none, one and more than one (AUTH-7 lets a person choose)."""
    # A query of its own, built on no manager, as above. Found by Django's own index on `user`, which stays for this
    # very read: a person's jobs start from the person, not from a shop (apps/people/models.py).
    rows: models.QuerySet[StaffMember] = models.QuerySet(StaffMember)
    current = rows.filter(user_id=user_id).exclude(status=StaffStatus.LEFT)
    return list(current.values_list("shop_id", flat=True)[:2])
