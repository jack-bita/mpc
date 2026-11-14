"""apps/people/tests/test_device_sync_report.py — what a laptop says about itself each time it pushes: the records it
still holds unsent, the app version it runs, when it last synced (SYNC-5; 02 §5, 03 §6.6), and how far its clock was
from the server's (SYNC-14).

    Laptop ya Dawa, 14:05     unsent 3, app 2026.11.1, clock 6 min slow
                              → its row: last synced 14:05, unsent 3, app 2026.11.1, clock error -6 min

Written by record_sync (apps/people/services.py), which the push calls at its end (apps/sync/push.py). Every push
moves these columns, an empty one too, so they move like `last_seen_at`: one UPDATE, never the row's version, which
a manager's rename screen holds (CORE-6), and never a row of the edit history (ADR-0036). Fake data only: the repo is
public (03 §10).
"""

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.control.models import EditEvent
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import confirm_pairing, record_sync, rename_device, start_pairing
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


# The Dawa laptop's clock, 6 minutes slow: its time minus the server's.
SLOW = timedelta(minutes=-6)
RIGHT = timedelta(0)


def report(device: Device) -> tuple[object, object, object, object]:
    held = stored(device)
    return held.last_synced_at, held.unsent_count, held.app_version, held.clock_error


def test_a_new_device_has_reported_nothing(laptop: Device) -> None:
    # Paired, never synced: nothing to show yet, rather than a made-up 0, which would say "nothing unsent", or a
    # clock error of 0, which would say "its clock is right".
    assert report(laptop) == (None, None, "", None)


def test_sync_report_is_kept_on_the_device(laptop: Device) -> None:
    at = timezone.now()
    with shop_context(laptop.shop_id):
        record_sync(laptop, at=at, unsent_count=3, app_version="2026.11.1", clock_error=SLOW)
    assert report(laptop) == (at, 3, "2026.11.1", SLOW)
    # The next push says the laptop has sent everything, and a manager has put its clock right.
    with shop_context(laptop.shop_id):
        record_sync(laptop, at=at + timedelta(seconds=30), unsent_count=0, app_version="2026.11.1", clock_error=RIGHT)
    assert report(laptop) == (at + timedelta(seconds=30), 0, "2026.11.1", RIGHT)


def test_an_older_report_never_overwrites_a_newer_one(laptop: Device) -> None:
    # Two pushes of one laptop at the same moment, the earlier one slower: its report, older, arrives last. The
    # database keeps the newer one, or the office would see "3 unsent" from a laptop that has sent them all, and a
    # clock 6 minutes slow on a laptop whose clock was just put right.
    at = timezone.now()
    with shop_context(laptop.shop_id):
        record_sync(laptop, at=at, unsent_count=0, app_version="2026.11.2", clock_error=RIGHT)
        record_sync(laptop, at=at - timedelta(seconds=5), unsent_count=3, app_version="2026.11.1", clock_error=SLOW)
    assert report(laptop) == (at, 0, "2026.11.2", RIGHT)


def test_sync_report_writes_no_history(laptop: Device) -> None:
    # A laptop pushes every 30 seconds or so (03 §6.6): a history row each time would bury the owner's real changes.
    with shop_context(laptop.shop_id):
        record_sync(laptop, at=timezone.now(), unsent_count=3, app_version="2026.11.1", clock_error=SLOW)
        assert not EditEvent.objects.filter(subject_type="device", subject_id=laptop.pk).exists()


def test_synced_device_keeps_its_version(laptop: Device, staff_a: StaffMember) -> None:
    # A manager opened the rename screen; the laptop syncs; the rename still goes through with the version the screen
    # read, as for last_seen_at (CORE-6).
    version = stored(laptop).version
    with shop_context(laptop.shop_id):
        record_sync(laptop, at=timezone.now(), unsent_count=3, app_version="2026.11.1", clock_error=SLOW)
        assert stored(laptop).version == version
        renamed = rename_device(laptop, name="Laptop ya Dawa 2", version=version, by=staff_a)
    assert renamed.name == "Laptop ya Dawa 2"
