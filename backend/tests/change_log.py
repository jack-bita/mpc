"""backend/tests/change_log.py — reading a shop's change log in a test, from the line the test starts at (SYNC-15).

Every service that changes something a shop's devices keep a copy of writes its line in the shop's change log
(apps/core/changes.py), and so do the services that make the fixtures' rows (backend/conftest.py): a side made there has
already written two lines, the side and its drawer, before the test starts. So a test that asks "what did this save
write?" reads only the lines numbered after a mark taken when it starts:

    with lines_written(shop_a) as lines:
        rename_side(dawa, version=1, name="Dawa Kuu", by=None)
    assert lines == [("side", dawa.pk, "upsert")]

A test that checks the numbers themselves reads lines_after(shop, start), which numbers them from 1 again, as a test
that started at `start` counts them. Each read names its shop and opens it for that read alone, so it works with
another shop open, with none, or with every shop (system_context).
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from django.db.models import Model

from apps.core.models import Change
from apps.core.tenancy import shop_context

# One line as a device reads it: the table's link type code, the record's id, and what to do ("upsert", "archive").
type Line = tuple[str, uuid.UUID, str]


def _shop_id(shop: Model | uuid.UUID) -> uuid.UUID:
    # A Shop row or a shop's id, as recording_changes takes either. Typed as any model: tests of `core` may not name
    # Shop (ADR-0041).
    return shop if isinstance(shop, uuid.UUID) else shop.pk


def last_line(shop: Model | uuid.UUID) -> int:
    """The number of the shop's last line, 0 for a shop with none."""
    shop_id = _shop_id(shop)
    with shop_context(shop_id):
        last = Change.objects.filter(shop_id=shop_id).order_by("-seq").values_list("seq", flat=True).first()
    return last or 0


def lines_after(shop: Model | uuid.UUID, start: int) -> list[tuple[int, str, uuid.UUID, str]]:
    """The shop's lines numbered after `start`, in order, as (number, table, record, op), each number counted from
    `start`: the first line after it is 1, as on a shop's first day. A gap in the real numbers stays a gap here."""
    shop_id = _shop_id(shop)
    with shop_context(shop_id):
        rows = (
            Change.objects.filter(shop_id=shop_id, seq__gt=start)
            .order_by("seq")
            .values_list("seq", "entity", "record_id", "op")
        )
        return [(seq - start, entity, record_id, op) for seq, entity, record_id, op in rows]


@contextmanager
def lines_written(shop: Model | uuid.UUID) -> Iterator[list[Line]]:
    """The lines the code inside the block wrote in the shop's log, filled in as the block ends, in their numbers'
    order. Put pytest.raises inside it, not around it, to see what a refused save wrote: nothing."""
    start = last_line(shop)
    lines: list[Line] = []
    yield lines
    lines.extend((entity, record_id, op) for _number, entity, record_id, op in lines_after(shop, start))
