"""apps/core/links.py — generic links: a row of one of several tables, named by a short type code and its UUID
(02 §1, 03 §5.1).

Most links point at one table, and are foreign keys: a side's stock location points at a side. A few can
point at a row of many tables: a flag's subject (a drawer's day, a stock count, a sale...), an audit line's
subject (a staff member's job), and, later, a ledger row's source. Such a link is stored as two columns: a
short code that says which table ("sale"), and the row's UUID. A code is readable, and the same in every
database. Django's own content types number the tables instead, and the numbers differ from one database to
the next (the laptop, the demo, a restored backup), so a link stored in one would point elsewhere in another.

This file owns the list of codes: `link_type_of(row)` gives a row's code, `load_link(code, id)` loads the
row back, and `table_of(code)` names the table behind a code. It names each table by text ("sales.Sale"),
not by an import: `core` is layer 0 and may not import any app (ADR-0035), and a name is not an import
(03 §5.1).
"""

import uuid

from django.apps import apps

from apps.core.models import ShopScoped

# The shape of a code: small letters and underscores, starting with a letter ("drawer_session"), and its
# longest length, the size of the column that stores it. The tables that store a link use both: the column
# (control.Flag's subject_type) and a database rule on its shape. A code that broke either would be refused
# only when the first link to its table is written, perhaps while a device's records are posted, which must
# never fail; so a test checks every code in the list instead (apps/core/tests/test_links.py).
TYPE_CODE_SHAPE = r"^[a-z][a-z_]*$"
TYPE_CODE_MAX_LENGTH = 40

# Code → the table it names, as "app.Model". Only shop tables (ShopScoped): a link is a shop's, and it loads
# through the shop guard.
# A code, once stored in a row, never changes and never names another table: old rows would then point at
# the wrong table, or at none. A table that moves to another app keeps its code; only the text on the right
# changes. Each card adds the tables its links point at, as each card adds its setting keys
# (apps/core/settings_registry.py).
LINK_TYPES: dict[str, str] = {
    # A staff member's job: the audit trail's lines about suspending, bringing back and leaving, and the history of
    # its edits (CTRL-2).
    "staff": "people.StaffMember",
    # A side: the history of its edits, such as a new name (CTRL-2).
    "side": "shops.Side",
    # A payment account and a stock location: the history of their edits, such as a till's new number (CTRL-2).
    "payment_account": "shops.PaymentAccount",
    "stock_location": "shops.StockLocation",
}


class UnknownLinkType(Exception):
    # A bug, not a user's mistake: the code named a row of a table with no code here, or a code with no shop
    # table behind it. Like ShopMismatch (apps/core/tenancy.py), it becomes a server error and a log line,
    # never a message on a screen, so it carries no error code (ADR-0032).
    pass


def link_type_of(row: ShopScoped) -> str:
    """The code a link to `row` is stored with."""
    label = row._meta.label
    codes = [code for code, table in LINK_TYPES.items() if table == label]
    # Exactly one: with none, there is nothing to store; with two, the same row could be stored two ways, and
    # a search for the links to it would find only one of them.
    if not codes:
        raise UnknownLinkType(f"{label} has no type code: add one to LINK_TYPES (apps/core/links.py).")
    if len(codes) > 1:
        raise UnknownLinkType(f"{label} has two type codes in LINK_TYPES: {', '.join(codes)}.")
    return codes[0]


def load_link(type_code: str, row_id: uuid.UUID) -> ShopScoped:
    """The row a link names. Read through the table's guarded manager (ADR-0022), so it needs an open shop
    and finds only that shop's rows: a link to another shop's row raises the table's DoesNotExist, as an id no
    shop has does."""
    return table_of(type_code)._default_manager.get(pk=row_id)


def table_of(type_code: str) -> type[ShopScoped]:
    """The shop table a code names. UnknownLinkType for a code the list doesn't hold, or one that names no shop
    table."""
    label = LINK_TYPES.get(type_code)
    if label is None:
        raise UnknownLinkType(f"{type_code!r} is not a type code in LINK_TYPES (apps/core/links.py).")
    # Asked of Django by name, at run time: this is how `core` reaches a table of a higher layer without
    # importing it.
    try:
        table = apps.get_model(label)
    except LookupError:
        # No such app, or no such table in it: a typo, or a table a card renamed.
        raise UnknownLinkType(f"{type_code!r} names {label!r}, but no app has that table.") from None
    except ValueError:
        # Text that isn't "app.Model" at all.
        raise UnknownLinkType(f'{type_code!r} names {label!r}, which is not written as "app.Model".') from None
    # A table with no `shop` (a User, a Unit) has no guard, so loading through it could read any shop's row.
    if not issubclass(table, ShopScoped):
        raise UnknownLinkType(f"{type_code!r} names {label}, which is not a shop's table.")
    return table
