"""apps/core/acting.py — tells PostgreSQL who acts in a visit, so that a trigger can name them (03 §5.16,
ADR-0036).

A trigger runs inside PostgreSQL, after Python has sent its UPDATE, and can't see the visit that sent it. The
trigger that records every office edit (apps/control/operations.py) must still say who made it. So each office
visit tells PostgreSQL the staff member acting, in a setting of the database session, `mpc.staff_id`, the way
it already opens the visit's shop in Python (apps/core/tenancy.py). The trigger reads it:

    office visit (staff A)          PostgreSQL session
    acting_as(staff A)       ──▶    mpc.staff_id = A's id
    rename_side(...)         ──▶    UPDATE shops_side … ──▶ trigger: who = A's id
    the visit ends           ──▶    mpc.staff_id = what it was before ("" = nobody)

Outside a visit (a nightly job, the seed, a test that opens no visit) the setting is empty, and the trigger
names nobody: the system acted, as an empty `created_by` means on every shop row (02 §1).

This file owns the setting's name and the one way to change it. It is the one file outside migrations, system
jobs and tests that runs SQL by hand, and CORE-7's sweep lists it, with its reason (backend/tests/sweep_lists.py,
RAW_SQL): its SQL reads and writes that one setting, never a table, so no shop's row is read past the guard.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection

from apps.core.tenancy import Actor

# The setting's name. PostgreSQL takes settings of its own invention only with a dot in the name, and "mpc."
# keeps ours apart from any a library makes. The trigger's SQL names it too, and that SQL is frozen once on
# main (apps/control/operations.py), so this name never changes either.
STAFF_SETTING = "mpc.staff_id"


@contextmanager
def acting_as(actor: Actor) -> Iterator[None]:
    """Tell PostgreSQL that `actor` acts, for the code inside the `with` block: every row a trigger records
    there names `actor`'s staff member, or nobody for a device alone (03 §5.4). What was there before is put
    back however the block ends, as shop_context() puts back the shop."""
    before = _read()
    _write("" if actor.staff_id is None else str(actor.staff_id))
    try:
        yield
    finally:
        _write(before)


def _read() -> str:
    # current_setting(…, true): `true` means "missing is fine", so a session that never set it answers NULL
    # (None here) instead of raising. Read as "": nobody.
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [STAFF_SETTING])
        row = cursor.fetchone()
    return (row[0] if row else None) or ""


def _write(value: str) -> None:
    # set_config(name, value, false): `false` means for the session, not only for the current transaction. A
    # visit runs most of its queries outside any transaction (autocommit), so a setting for one transaction
    # would be gone before the visit's edit. For the session, it stays on this database connection until it is
    # changed: so acting_as() always puts the old value back, and a connection the server keeps open for the
    # next visit (CONN_MAX_AGE) never carries this person into it. A value is a parameter, never pasted into
    # the SQL.
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [STAFF_SETTING, value])
