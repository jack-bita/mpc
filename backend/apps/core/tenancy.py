"""apps/core/tenancy.py — the current shop: which shop the code may read right now (ADR-0022, 03 §5.4).

Many shops keep their rows side by side in the same tables. Each visit to the server (a request) works
for one shop, and this file holds that shop for the length of the visit: `shop_context(shop)` sets it,
`system_context()` opens every shop for a system job, and `current_shop()` reads it. Every ShopScoped
table's default manager (apps/core/models.py) calls `current_shop()`, so a read that names no shop stops
with NoShopSelected instead of returning every shop's rows. Code handed another shop, or another shop's
row, than the one open raises ShopMismatch. An Actor is whoever acts in a visit, and belongs to one shop.
"""

import enum
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from django.db import models


class NoShopSelected(Exception):
    # A bug, not a user's mistake: the code read a shop's table without saying which shop. It becomes a
    # server error and a log line, never a message on a screen, so it carries no error code (ADR-0032).
    pass


class ShopMismatch(Exception):
    # A bug too: the code was handed a shop, or a row of a shop, other than the one open, such as a side
    # of shop B while shop A is open. Its own class, not a ValueError: code that catches ValueError for
    # bad input (a setting kind's parse(), apps/core/settings_registry.py) must never swallow a tenancy
    # bug. Like NoShopSelected, it becomes a server error and a log line, with no error code (ADR-0032).
    pass


class AllShops(enum.Enum):
    # The one value that means "every shop", and only system_context() sets it. Its own value, not None:
    # None already means "no shop chosen", and those two must never be mixed up.
    ALL_SHOPS = "all_shops"


ALL_SHOPS = AllShops.ALL_SHOPS


class Actor(Protocol):
    # Whoever a visit's login names, as it leaves them in `request.auth` (apps/core/api/base.py): a staff
    # member (AUTH-3, AUTH-4), or later a paired device (AUTH-2). Described by what it has, not by its name:
    # `core` and `shops` may not import `people` (ADR-0035).
    # - `shop_id`: the one shop it belongs to, which the visit works for. The services check it against the
    #   shop they write to (T1).
    # - `staff_id`: the staff member acting, whom the services record as who made or changed a row
    #   (`created_by`, `updated_by`). None when no person acts: a device alone is a shop's machine, not
    #   someone, so office routes refuse it.
    @property
    def shop_id(self) -> uuid.UUID: ...

    @property
    def staff_id(self) -> uuid.UUID | None: ...


# The note itself. It holds a shop's id, ALL_SHOPS, or None: "no shop chosen", how every visit starts.
# - A context variable, not a plain variable: each visit gets its own note, even when one server worker
#   runs several visits at once, so two visits never see each other's shop.
# - The shop's id, not the Shop row: the filter needs only the id, and `core` may not name `Shop`, not
#   even for types (ADR-0035; decided in CORE-2, see backend/pyproject.toml).
# - Private (the _ in front): only shop_context() and system_context() below write it, and they always
#   put the old value back.
_current_shop: ContextVar[uuid.UUID | AllShops | None] = ContextVar("current_shop", default=None)


def current_shop() -> uuid.UUID | AllShops:
    # What every read asks first: which shop may I see? The guarded manager calls this each time a read
    # is built, so an empty note stops the read before it reaches the database.
    shop = _current_shop.get()
    if shop is None:
        # The message is for the programmer who forgot, and says how to fix it.
        raise NoShopSelected("No current shop: open shop_context(shop), or system_context() in a system job.")
    return shop


@contextmanager
def shop_context(shop: models.Model | uuid.UUID) -> Iterator[None]:
    # Opens a shop for the code inside the `with` block. `shop` is a Shop row, typed as any model
    # because `core` may not name `Shop` (ADR-0035), or a shop's id: a visit knows its shop only by the
    # id the person acting carries (apps/core/api/base.py), and loading the row would cost a query.
    token = _current_shop.set(shop if isinstance(shop, uuid.UUID) else shop.pk)
    try:
        yield
    finally:
        # However the block ends, even in an error, the note goes back to what it was before. So the
        # next visit on this worker never inherits this shop, and an inner block hands back the outer one.
        _current_shop.reset(token)


@contextmanager
def system_context() -> Iterator[None]:
    # Opens every shop, for system jobs only: a nightly check, a management command, the demo seed.
    # Never in code that answers a visit: a visit works for one shop (03 §5.4). The name is plain on
    # purpose, so `grep system_context` finds every place that reads across shops.
    token = _current_shop.set(ALL_SHOPS)
    try:
        yield
    finally:
        # The same promise as shop_context(): the note goes back however the block ends.
        _current_shop.reset(token)
