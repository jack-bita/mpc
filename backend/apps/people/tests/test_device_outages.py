"""apps/people/tests/test_device_outages.py — the offline periods a laptop reports at its next push (SYNC-5; 02 §5,
03 §6.11).

    Laptop ya Dawa, its push at 10:05     offline 09:10–09:40      → one DeviceOutage on the laptop: 09:10–09:40

The laptop writes down when its line went and came back, by its own clock, and sends the periods at its next push,
each with an id it made (ADR-0007), so a push sent again saves each period once. Kept as the laptop reported them,
never changed (AppendOnly): they feed the device health page (SYNC-14) and the owner's choice on a local hub (03 AD16).
Fake data only: the repo is public (03 §10).
"""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from django.db import IntegrityError, transaction

from apps.core.models import AppendOnlyError
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, DeviceOutage, StaffMember
from apps.people.services import Outage, confirm_pairing, record_outages, start_pairing
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# 09:10 to 09:40 in Usa River (UTC+3), as the laptop's clock said, in UTC (03 §6.6).
WENT = dt.datetime(2026, 11, 10, 6, 10, tzinfo=dt.UTC)
CAME_BACK = dt.datetime(2026, 11, 10, 6, 40, tzinfo=dt.UTC)


def _laptop(manager: StaffMember, side: Side, name: str) -> Device:
    with shop_context(manager.shop_id):
        return confirm_pairing(start_pairing().request.code, name=name, home_side=side, by=manager)


@pytest.fixture
def laptop(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> Device:
    give_role(staff_a, RoleTemplate.MANAGER, None)
    return _laptop(staff_a, side_a, "Laptop ya Dawa")


def _outages(device: Device) -> list[tuple[dt.datetime, dt.datetime]]:
    # The laptop's offline periods, oldest first, as the health page will read them.
    with shop_context(device.shop_id):
        rows = DeviceOutage.objects.filter(device=device).order_by("started_at")
        return [(row.started_at, row.ended_at) for row in rows]


def test_outages_are_kept_on_the_device(laptop: Device) -> None:
    later = Outage(
        id=uuid.uuid7(), started_at=CAME_BACK + dt.timedelta(hours=2), ended_at=CAME_BACK + dt.timedelta(hours=3)
    )
    with shop_context(laptop.shop_id):
        record_outages(laptop, [Outage(id=uuid.uuid7(), started_at=WENT, ended_at=CAME_BACK), later])
    assert _outages(laptop) == [(WENT, CAME_BACK), (later.started_at, later.ended_at)]


def test_an_outage_sent_again_is_kept_once(laptop: Device) -> None:
    # The push's answer was lost, so the laptop sends the same report again, or lists one period twice: its id, made
    # on the laptop, says it is the same period.
    outage = Outage(id=uuid.uuid7(), started_at=WENT, ended_at=CAME_BACK)
    with shop_context(laptop.shop_id):
        record_outages(laptop, [outage, outage])
        record_outages(laptop, [outage])
    assert _outages(laptop) == [(WENT, CAME_BACK)]


def test_an_outage_keeps_the_laptops_times_as_sent(laptop: Device) -> None:
    # A laptop's clock moved back while it was offline, so its period "ends" before it starts. Kept as reported, for
    # the health page to show: refusing it would refuse the laptop's whole push, again at every sync, records and all.
    backwards = Outage(id=uuid.uuid7(), started_at=CAME_BACK, ended_at=WENT)
    with shop_context(laptop.shop_id):
        record_outages(laptop, [backwards])
    assert _outages(laptop) == [(CAME_BACK, WENT)]


def test_an_id_another_shop_holds_is_left_out(
    laptop: Device, shop_b: Shop, staff_b: StaffMember, side_b: Side, give_role: GiveRole
) -> None:
    # Shop B's laptop reported a period; shop A's laptop sends a period with the same id. It is left out, with no
    # error: a report on the laptop's health must not stop its push, and nothing of B's period changes or shows.
    give_role(staff_b, RoleTemplate.MANAGER, None)
    laptop_b = _laptop(staff_b, side_b, "Laptop B")
    shared = uuid.uuid7()
    with shop_context(shop_b):
        record_outages(laptop_b, [Outage(id=shared, started_at=WENT, ended_at=CAME_BACK)])
    with shop_context(laptop.shop_id):
        record_outages(laptop, [Outage(id=shared, started_at=CAME_BACK, ended_at=CAME_BACK)])
    assert _outages(laptop) == []
    assert _outages(laptop_b) == [(WENT, CAME_BACK)]


def test_outages_are_never_changed(laptop: Device) -> None:
    # A ledger (ADR-0021): what the laptop reported stays as it reported it. Refused in Python, and by PostgreSQL
    # whatever sends the change.
    with shop_context(laptop.shop_id):
        record_outages(laptop, [Outage(id=uuid.uuid7(), started_at=WENT, ended_at=CAME_BACK)])
        row = DeviceOutage.objects.get()
        row.ended_at = WENT
        with pytest.raises(AppendOnlyError):
            row.save()
        with pytest.raises(IntegrityError), transaction.atomic():
            DeviceOutage.objects.filter(pk=row.pk).update(ended_at=WENT)
        with pytest.raises(IntegrityError), transaction.atomic():
            DeviceOutage.objects.filter(pk=row.pk).delete()
    assert _outages(laptop) == [(WENT, CAME_BACK)]
