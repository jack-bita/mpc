"""apps/core/acting.py — tells PostgreSQL who acts in a visit, so that a trigger can name them (03 §5.16,
ADR-0036).

A trigger runs inside PostgreSQL, after Python has sent its UPDATE, and can't see the visit that sent it. The
trigger that records every office edit (apps/control/operations.py) must still say who made it. So each office
visit tells PostgreSQL the staff member acting, and the shop the visit works for, in two settings of the database
session, `mpc.staff_id` and `mpc.shop_id`, the way it already opens the visit's shop in Python
(apps/core/tenancy.py). The trigger reads them: it names the staff member, and refuses an edit of another shop's
row (T1), so a bug elsewhere can never put shop A's person into shop B's history.

    office visit (staff A, shop A)   PostgreSQL session
    acting_as(staff A)       ──▶     mpc.staff_id = A's id, mpc.shop_id = shop A's id
    rename_side(...)         ──▶     UPDATE shops_side … ──▶ trigger: a row of shop A? who = A's id
    the visit ends           ──▶     both = what they were before ("" = nobody, no shop)

Outside a visit (a nightly job, the seed, a test that opens no visit) both settings are empty: the trigger names
nobody, since the system acted, as an empty `created_by` means on every shop row (02 §1), and checks no shop, since
a system job may work across shops (03 §5.11).

This file owns the settings' names and the one way to change them. It is the one file outside migrations, system
jobs and tests that runs SQL by hand, and CORE-7's sweep lists it, with its reason (backend/tests/sweep_lists.py,
RAW_SQL): its SQL reads and writes those two settings, never a table, so no shop's row is read past the guard.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection

from apps.core.tenancy import Actor

# The settings' names. PostgreSQL takes settings of its own invention only with a dot in the name, and "mpc."
# keeps ours apart from any a library makes. The trigger's SQL names them too, and that SQL is frozen once on
# main (apps/control/operations.py), so these names never change either.
STAFF_SETTING = "mpc.staff_id"
SHOP_SETTING = "mpc.shop_id"


@contextmanager
def acting_as(actor: Actor) -> Iterator[None]:
    """Tell PostgreSQL that `actor` acts, for the code inside the `with` block: every row a trigger records
    there names `actor`'s staff member, or nobody for a device alone (03 §5.4), and must belong to `actor`'s
    shop. What was there before is put back however the block ends, as shop_context() puts back the shop."""
    staff_before, shop_before = _read()
    _write("" if actor.staff_id is None else str(actor.staff_id), str(actor.shop_id))
    try:
        yield
    finally:
        _write(staff_before, shop_before)


def _read() -> tuple[str, str]:
    # current_setting(…, true): `true` means "missing is fine", so a session that never set one answers NULL
    # (None here) instead of raising. Read as "": nobody, no shop.
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true), current_setting(%s, true)", [STAFF_SETTING, SHOP_SETTING])
        row = cursor.fetchone()
    staff, shop = row if row else (None, None)
    return staff or "", shop or ""


def _write(staff: str, shop: str) -> None:
    # set_config(name, value, false): `false` means for the session, not only for the current transaction. A
    # visit runs most of its queries outside any transaction (autocommit), so a setting for one transaction
    # would be gone before the visit's edit. For the session, it stays on this database connection until it is
    # changed: so acting_as() always puts the old values back, and a connection the server keeps open for the
    # next visit (CONN_MAX_AGE) never carries this person into it. Both in one query; a value is a parameter,
    # never pasted into the SQL.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, false), set_config(%s, %s, false)", [STAFF_SETTING, staff, SHOP_SETTING, shop]
        )
