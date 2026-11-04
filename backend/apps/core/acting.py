"""apps/core/acting.py — tells PostgreSQL who acts in a visit, so that a trigger can name them (03 §5.16,
ADR-0036).

A trigger runs inside PostgreSQL, after Python has sent its UPDATE, and can't see the visit that sent it. The
trigger that records every office edit (apps/control/operations.py) must still say who made it, and from which
device (X3). So each visit tells PostgreSQL the staff member acting, the shop the visit works for and its device, in
three settings of the database session, `mpc.staff_id`, `mpc.shop_id` and `mpc.device_id`, the way it already opens
the visit's shop in Python (apps/core/tenancy.py). The trigger reads them: it names the staff member and the device,
and refuses an edit of another shop's row (T1), so a bug elsewhere can never put shop A's person into shop B's history.

    office visit (staff A, shop A, laptop L)   PostgreSQL session
    acting_as(staff A, device=L)        ──▶    mpc.staff_id = A's id, mpc.shop_id = shop A's id, mpc.device_id = L's id
    rename_side(...)                    ──▶    UPDATE shops_side … ──▶ trigger: a row of shop A? who = A, device = L
    the visit ends                      ──▶    all three = what they were before ("" = nobody, no shop, no device)

Outside a visit (a nightly job, the seed, a test that opens no visit) all three are empty: the trigger names
nobody, since the system acted, as an empty `created_by` means on every shop row (02 §1), and checks no shop, since
a system job may work across shops (03 §5.11).

The audit book reads the same note (current_device_id, read by audit() in apps/control/services.py), so the two books
can't name different devices for one action (Jack, AUTH-8; 02 v1.7: one fact, one answer).

This file owns the settings' names and the one way to change them. It is the one file outside migrations, system
jobs and tests that runs SQL by hand, and CORE-7's sweep lists it, with its reason (backend/tests/sweep_lists.py,
RAW_SQL): its SQL reads and writes those three settings, never a table, so no shop's row is read past the guard.
"""

import enum
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection
from psycopg.pq import TransactionStatus

from apps.core.models import ShopScoped
from apps.core.tenancy import Actor, ShopMismatch

# The settings' names. PostgreSQL takes settings of its own invention only with a dot in the name, and "mpc."
# keeps ours apart from any a library makes. The trigger's SQL names them too, and that SQL is frozen once on
# main (apps/control/operations.py), so these names never change either.
STAFF_SETTING = "mpc.staff_id"
SHOP_SETTING = "mpc.shop_id"
DEVICE_SETTING = "mpc.device_id"


class _Device(enum.Enum):
    # What acting_as() does with the device when it is given none: its own value, not None. None means "this visit has
    # no device", and those two must never be mixed up (as with SEES_THE_SIDE, apps/core/api/base.py).
    KEEP = "keep"


KEEP_DEVICE = _Device.KEEP


@contextmanager
def acting_as(actor: Actor, *, device: ShopScoped | None | _Device = KEEP_DEVICE) -> Iterator[None]:
    """Tell PostgreSQL that `actor` acts, for the code inside the `with` block: every row a trigger records
    there names `actor`'s staff member, or nobody for a device alone (03 §5.4), and must belong to `actor`'s
    shop. What was there before is put back however the block ends, as shop_context() puts back the shop.

    `device`: the device the visit came from, or None for a visit with none. A visit says which, once, as it opens.
    Left out, the device stays as the visit told it: editing() and the staff services open an inner block of their own
    for `by`, mid-visit, and it must not wipe the device, or every edit made through them would lose it (X3). It stays
    only inside its own shop: a block for another shop's actor has no device, as no device belongs to two shops (T1)."""
    # T1: a bug in the calling code, as in editing(), so a server error, before PostgreSQL is told anything. The check
    # costs no query, and it holds for the trigger too: the trigger refuses a row of any shop but `actor`'s, and this is
    # a device of `actor`'s shop, so a history row never names a device of another shop.
    if isinstance(device, ShopScoped) and device.shop_id != actor.shop_id:
        raise ShopMismatch("The device belongs to another shop than the one acting.")
    staff_before, shop_before, device_before = _swap(
        "" if actor.staff_id is None else str(actor.staff_id), str(actor.shop_id), device
    )
    try:
        yield
    finally:
        # Not after a query failed inside the transaction: PostgreSQL refuses every query until the rollback, so
        # writing would fail too, and its error would hide the real one. The rollback puts the old values back
        # itself: they were changed inside that same transaction, since a `with` block opened inside it ends first.
        if not _transaction_failed():
            _write(staff_before, shop_before, device_before)


def current_device_id(shop_id: uuid.UUID) -> uuid.UUID | None:
    """The device this visit told PostgreSQL, for a row of `shop_id` to name, or None for none: what the trigger reads
    for the edit history, so that an audit line names the same one. Outside a visit, always None: the system has no
    device. T1: a row of another shop than the visit's is a bug in the calling code, refused as the trigger refuses it,
    so that shop's row never names this shop's device. With no device, there is nothing to name or to check."""
    # Both in one query: the device, and the shop it was told for.
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true), current_setting(%s, true)", [DEVICE_SETTING, SHOP_SETTING])
        row = cursor.fetchone()
    device_id, told_shop = (row[0], row[1]) if row else (None, None)
    # "" or never told (NULL): none. Nothing but acting_as() writes the setting, so what is there is an id.
    if not device_id:
        return None
    if told_shop != str(shop_id):
        raise ShopMismatch("The row belongs to another shop than the visit and its device.")
    return uuid.UUID(device_id)


def _transaction_failed() -> bool:
    # Django knows a transaction must roll back (needs_rollback) once an atomic block inside it has failed;
    # PostgreSQL knows from the first failed query (INERROR), even before any block has ended. Either one is enough.
    if connection.needs_rollback:
        return True
    # The psycopg connection under Django's; None until the first query opens it.
    raw = connection.connection
    return raw is not None and raw.info.transaction_status == TransactionStatus.INERROR


# Reads the three settings, then writes the new values, in one query: every office visit opens acting_as(), reads
# included, so it costs one query on the way in and one on the way out.
# - current_setting(…, true): `true` means "missing is fine", so a session that never set one answers NULL
#   (None in Python) instead of raising. Read as "": nobody, no shop, no device.
# - The order matters: the old values must be read before the new ones are written. PostgreSQL promises no order
#   between the parts of one SELECT list, so the reading sits in its own step, a MATERIALIZED WITH, which PostgreSQL
#   works out first, as a table of its own, before the outer SELECT writes anything (set_config, as in _write below).
# - The new device, in order of what is known. COALESCE takes the first value that isn't NULL: the one this block
#   names (a device's id, or "" for none); else, with KEEP_DEVICE (NULL), the one before, if the shop stays the same;
#   else "", as a CASE with no ELSE answers NULL when the shop changes.
_SWAP_SQL = """
WITH before AS MATERIALIZED (
    SELECT current_setting(%s, true) AS staff, current_setting(%s, true) AS shop, current_setting(%s, true) AS device
)
SELECT before.staff, before.shop, before.device, set_config(%s, %s, false), set_config(%s, %s, false),
    set_config(%s, COALESCE(%s, CASE WHEN before.shop = %s THEN before.device END, ''), false)
FROM before
"""


def _swap(staff: str, shop: str, device: ShopScoped | None | _Device) -> tuple[str, str, str]:
    # The new values in, the old ones back (see _SWAP_SQL).
    new_device = None if device is KEEP_DEVICE else "" if device is None else str(device.pk)
    with connection.cursor() as cursor:
        cursor.execute(
            _SWAP_SQL,
            [
                STAFF_SETTING,
                SHOP_SETTING,
                DEVICE_SETTING,
                STAFF_SETTING,
                staff,
                SHOP_SETTING,
                shop,
                DEVICE_SETTING,
                new_device,
                shop,
            ],
        )
        row = cursor.fetchone()
    staff_before, shop_before, device_before = (row[0], row[1], row[2]) if row else (None, None, None)
    return staff_before or "", shop_before or "", device_before or ""


def _write(staff: str, shop: str, device: str) -> None:
    # set_config(name, value, false): `false` means for the session, not only for the current transaction. A
    # visit runs most of its queries outside any transaction (autocommit), so a setting for one transaction
    # would be gone before the visit's edit. For the session, it stays on this database connection until it is
    # changed: so acting_as() always puts the old values back, and a connection the server keeps open for the
    # next visit (CONN_MAX_AGE) never carries this person or this device into it. All in one query; a value is a
    # parameter, never pasted into the SQL.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, false), set_config(%s, %s, false), set_config(%s, %s, false)",
            [STAFF_SETTING, staff, SHOP_SETTING, shop, DEVICE_SETTING, device],
        )
