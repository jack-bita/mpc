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
from psycopg.pq import TransactionStatus

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
    staff_before, shop_before = _swap("" if actor.staff_id is None else str(actor.staff_id), str(actor.shop_id))
    try:
        yield
    finally:
        # Not after a query failed inside the transaction: PostgreSQL refuses every query until the rollback, so
        # writing would fail too, and its error would hide the real one. The rollback puts the old values back
        # itself: they were changed inside that same transaction, since a `with` block opened inside it ends first.
        if not _transaction_failed():
            _write(staff_before, shop_before)


def _transaction_failed() -> bool:
    # Django knows a transaction must roll back (needs_rollback) once an atomic block inside it has failed;
    # PostgreSQL knows from the first failed query (INERROR), even before any block has ended. Either one is enough.
    if connection.needs_rollback:
        return True
    # The psycopg connection under Django's; None until the first query opens it.
    raw = connection.connection
    return raw is not None and raw.info.transaction_status == TransactionStatus.INERROR


# Reads the two settings, then writes the new values, in one query: every office visit opens acting_as(), reads
# included, so it costs one query on the way in and one on the way out.
# - current_setting(…, true): `true` means "missing is fine", so a session that never set one answers NULL
#   (None in Python) instead of raising. Read as "": nobody, no shop.
# - The order matters: the old values must be read before the new ones are written. PostgreSQL promises no order
#   between the parts of one SELECT list, so the reading sits in its own step, a MATERIALIZED WITH, which PostgreSQL
#   works out first, as a table of its own, before the outer SELECT writes anything (set_config, as in _write below).
_SWAP_SQL = """
WITH before AS MATERIALIZED (
    SELECT current_setting(%s, true) AS staff, current_setting(%s, true) AS shop
)
SELECT before.staff, before.shop, set_config(%s, %s, false), set_config(%s, %s, false) FROM before
"""


def _swap(staff: str, shop: str) -> tuple[str, str]:
    # The new values in, the old ones back (see _SWAP_SQL).
    with connection.cursor() as cursor:
        cursor.execute(_SWAP_SQL, [STAFF_SETTING, SHOP_SETTING, STAFF_SETTING, staff, SHOP_SETTING, shop])
        row = cursor.fetchone()
    staff_before, shop_before = (row[0], row[1]) if row else (None, None)
    return staff_before or "", shop_before or ""


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
