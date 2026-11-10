"""apps/shops/tests/test_change_lines.py — each side service writes its line in the shop's change log (SYNC-15).

A shop's devices keep a copy of its sides and its payment accounts (apps/sync/registry.py), and learn what changed only
from the lines of the shop's change log, after the last one they read (SYNC-3's pull). So each service that changes one
names it in the log: a new side and its cash drawer, which carries the sides it serves; a renamed side. A refused change
names nothing. The lines are read from where each step starts (backend/tests/change_log.py), as the fixture's side has
written lines of its own.
"""

import pytest

from apps.core.editing import VersionConflict
from apps.core.models import ChangeOp
from apps.core.tenancy import shop_context
from apps.shops.models import PaymentAccount, Shop, Side
from apps.shops.services import add_side, rename_side
from tests.change_log import lines_written

pytestmark = pytest.mark.django_db

UPSERT = ChangeOp.UPSERT


def test_each_service_records_its_change(shop_a: Shop, side_a: Side) -> None:
    # The owner adds Vyakula beside Dawa, then renames it. Each save lands its lines, and a laptop that pulls after it
    # reads each record as it is now: the new side and its new drawer, then the side again, with its new name.
    with shop_context(shop_a):
        with lines_written(shop_a) as added:
            vyakula = add_side(shop=shop_a, code="F", name="Vyakula", by=None)
        drawer = PaymentAccount.objects.get(sides=vyakula)
        with lines_written(shop_a) as renamed:
            rename_side(vyakula, version=vyakula.version, name="Vyakula Bora", by=None)
        # The copy in hand is still at version 1, read before the rename: an edit made on it is refused, and its block
        # ends before any line is named.
        with lines_written(shop_a) as refused, pytest.raises(VersionConflict):
            rename_side(vyakula, version=vyakula.version, name="Chakula", by=None)

    # The side, then its drawer: the drawer's line carries the sides it serves (PaymentAccountRecord). Its stock
    # location travels to no device, so it has no line.
    assert added == [("side", vyakula.pk, UPSERT), ("payment_account", drawer.pk, UPSERT)]
    assert renamed == [("side", vyakula.pk, UPSERT)]
    assert refused == []
