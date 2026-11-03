"""apps/people/tests/test_rename_device.py — renaming a paired device (AUTH-5; 02 §1, §5).

A manager renames a device from the device list: "Laptop ya Dawa" becomes "Laptop ya Kaunta". The rename keeps the
rules every office edit keeps (apps/core/editing.py): it is refused on an old copy, so a rename screen opened before
someone else's change never undoes it. It needs device.manage on the device's home side, as pairing and blocking it
do, and the shop's devices keep one name each. Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.core.editing import VersionConflict
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import confirm_pairing, rename_device, start_pairing
from apps.shops.models import Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def juma(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    # Shop A's manager on every side: the Manager role holds device.manage (apps/core/permissions.py).
    give_role(staff_a, RoleTemplate.MANAGER, None)
    return staff_a


def pair(by: StaffMember, side: Side, name: str) -> Device:
    # A device paired the way the app pairs one: it asks, and the manager confirms its code.
    code = start_pairing().request.code
    with shop_context(by.shop_id):
        return confirm_pairing(code, name=name, home_side=side, by=by)


@pytest.fixture
def laptop(juma: StaffMember, side_a: Side) -> Device:
    return pair(juma, side_a, "Laptop ya Dawa")


def test_rename_device_needs_device_manage_on_its_side(
    juma: StaffMember, laptop: Device, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # The Vyakula manager holds device.manage, but on Vyakula only: the Dawa laptop is not theirs to rename.
    with shop_context(staff_a2.shop_id):
        vyakula = add_side(shop=staff_a2.shop, code="F", name="Vyakula", by=None)
    give_role(staff_a2, RoleTemplate.MANAGER, vyakula)
    with shop_context(laptop.shop_id):
        with pytest.raises(PermissionDenied):
            rename_device(laptop, version=laptop.version, name="Laptop ya Kaunta", by=staff_a2)
        assert Device.objects.get(pk=laptop.pk).name == "Laptop ya Dawa"

        # Juma manages every side, so Dawa's laptop too. The rename moves the version on, and names who did it.
        renamed = rename_device(laptop, version=laptop.version, name="Laptop ya Kaunta", by=juma)
        stored = Device.objects.get(pk=laptop.pk)
    assert (stored.name, stored.version, stored.updated_by_id) == ("Laptop ya Kaunta", laptop.version + 1, juma.pk)
    assert renamed.name == stored.name


def test_rename_device_refuses_a_stale_version(juma: StaffMember, laptop: Device) -> None:
    # Two screens opened on the same device: the first rename wins, and the second, made on the copy read before it,
    # is refused instead of undoing it (409 version_conflict through the API).
    read_at = laptop.version
    with shop_context(laptop.shop_id):
        rename_device(laptop, version=read_at, name="Laptop ya Kaunta", by=juma)
        with pytest.raises(VersionConflict):
            rename_device(laptop, version=read_at, name="Laptop ya Stoo", by=juma)
        assert Device.objects.get(pk=laptop.pk).name == "Laptop ya Kaunta"


def test_rename_device_refuses_a_name_taken(juma: StaffMember, laptop: Device, side_a: Side) -> None:
    # The device list names each device, so no two of a shop's devices share a name, whatever the letter case, spaces
    # trimmed, as at pairing (test_pairing.py).
    phone = pair(juma, side_a, "Simu ya Dawa")
    with shop_context(phone.shop_id):
        with pytest.raises(ValidationError) as refused:
            rename_device(phone, version=phone.version, name=" laptop ya dawa ", by=juma)
        assert Device.objects.get(pk=phone.pk).name == "Simu ya Dawa"
    assert [error.code for error in refused.value.error_dict["__all__"]] == ["device.name_taken"]
