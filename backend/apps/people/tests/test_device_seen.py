"""apps/people/tests/test_device_seen.py — a device's `last_seen_at`, the last time its key reached the server (AUTH-2;
02 v1.12).

The login notes each device it finds as seen (note_device_seen, apps/people/services.py), a blocked one too, so the
device list shows when each one last called, and a stolen phone that keeps calling shows when. A counter laptop calls
many times a minute, so the time moves at most every 5 minutes, and only that one column moves: never the row's
version, which a manager's rename screen holds (CORE-6), and never a row of the edit history (ADR-0036).

    the device's last_seen_at     a request at 10:00     written?
    empty (never seen)            10:00                  yes
    09:58                         09:58                  no: 2 minutes ago
    09:55                         10:00                  yes: 5 minutes ago

Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.control.models import EditEvent
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import LAST_SEEN_EVERY, confirm_pairing, note_device_seen, start_pairing
from apps.shops.models import Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def laptop(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> Device:
    give_role(staff_a, RoleTemplate.MANAGER, None)
    with shop_context(staff_a.shop_id):
        return confirm_pairing(start_pairing().request.code, name="Laptop ya Dawa", home_side=side_a, by=staff_a)


def stored(device: Device) -> Device:
    # The device as the database holds it now, not the copy a test has in hand.
    with shop_context(device.shop_id):
        return Device.objects.get(pk=device.pk)


def test_last_seen_written_at_most_every_five_minutes(laptop: Device) -> None:
    assert timedelta(minutes=5) == LAST_SEEN_EVERY
    first = timezone.now()
    with shop_context(laptop.shop_id):
        # Never seen: written.
        assert note_device_seen(laptop, at=first)
        # A minute later, as the copy in hand says: nothing written, and no query needed to know it.
        assert not note_device_seen(laptop, at=first + timedelta(minutes=1))
        # A copy that says the device was never seen, as a second request that read it at the same moment as the
        # first holds: the database's own time decides, so the second writes nothing.
        old_copy = Device.objects.get(pk=laptop.pk)
        old_copy.last_seen_at = None
        assert not note_device_seen(old_copy, at=first + timedelta(minutes=2))
        # Five minutes after the first: written again.
        assert note_device_seen(laptop, at=first + LAST_SEEN_EVERY)

    assert stored(laptop).last_seen_at == first + LAST_SEEN_EVERY


def test_last_seen_writes_no_history(laptop: Device) -> None:
    # The device's history skips the column (migration 0008), as it skips the key's hash: otherwise every device
    # would fill the owner's trail with a row every few minutes, telling nothing.
    with shop_context(laptop.shop_id):
        assert note_device_seen(laptop, at=timezone.now())
        assert not EditEvent.objects.filter(subject_type="device", subject_id=laptop.pk).exists()


def test_seen_device_keeps_its_version(laptop: Device) -> None:
    # A manager's rename screen holds the version it read (CORE-6): a device calling in the meantime must not make
    # that rename look stale and get it refused (409). So only the one column moves.
    before = stored(laptop)
    with shop_context(laptop.shop_id):
        note_device_seen(laptop, at=timezone.now())
    after = stored(laptop)

    assert (after.version, after.updated_at) == (before.version, before.updated_at)
    assert after.last_seen_at is not None
