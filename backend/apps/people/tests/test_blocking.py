"""apps/people/tests/test_blocking.py — blocking and unblocking a paired device (AUTH-1; 02 §5, 03 §5.9).

A device that is stolen or lost is blocked from a manager's phone: its key opens nothing from its next request
(AUTH-2). When it comes back, it is unblocked with the same key, so the records it holds can still arrive. Both need
device.manage on the device's home side and a reason, and each writes one line in the audit trail, with who and why
(rule 7, T3), and one in the device's edit history:

    who    action           device            reason                     before            after
    Juma   device.block     Laptop ya Dawa    Imeibiwa kaunta            status: active    status: blocked
    Juma   device.unblock   Laptop ya Dawa    Polisi wameirudisha        status: blocked   status: active

And device codes are never given twice, a blocked device's included (D7). Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.control.models import AuditAction, AuditEvent, EditEvent
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, DeviceStatus, StaffMember
from apps.people.services import block, confirm_pairing, mark_left, start_pairing, suspend, unblock
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


def lines_about(device: Device) -> list[AuditEvent]:
    # Oldest first: ids are UUIDv7, which follow the order they were made in (ADR-0007).
    return list(AuditEvent.objects.filter(subject_type="device", subject_id=device.pk).order_by("id"))


def test_block_writes_audit_with_reason(juma: StaffMember, laptop: Device) -> None:
    with shop_context(juma.shop_id):
        blocked = block(laptop, by=juma, reason=" Imeibiwa kaunta ")
        assert blocked.status == DeviceStatus.BLOCKED
        unblocked = unblock(blocked, by=juma, reason="Polisi wameirudisha")
        assert unblocked.status == DeviceStatus.ACTIVE
        [blocking, unblocking] = lines_about(laptop)
        # Who, what and why, the reason trimmed: the words, not the spaces around them.
        assert (blocking.action, blocking.created_by_id, blocking.reason) == (
            AuditAction.DEVICE_BLOCK,
            juma.pk,
            "Imeibiwa kaunta",
        )
        assert (blocking.before, blocking.after) == ({"status": "active"}, {"status": "blocked"})
        assert (unblocking.action, unblocking.reason) == (AuditAction.DEVICE_UNBLOCK, "Polisi wameirudisha")
        assert (unblocking.before, unblocking.after) == ({"status": "blocked"}, {"status": "active"})
        # The edit history names the same person (02 v1.7: one fact, one answer), and the version moved on twice, so a
        # rename screen opened before the block must load the device again (409 version_conflict).
        history = EditEvent.objects.filter(subject_type="device", subject_id=laptop.pk).order_by("id")
        assert [(line.created_by_id, line.after) for line in history] == [
            (juma.pk, {"status": "blocked"}),
            (juma.pk, {"status": "active"}),
        ]
        assert Device.objects.get(pk=laptop.pk).version == laptop.version + 2


@pytest.mark.parametrize("action", ["block", "unblock"])
def test_block_needs_a_reason(juma: StaffMember, laptop: Device, action: str) -> None:
    # Rule 7: stopped, and let work again, always with who, when and why. Refused with the device's own code, before
    # audit() would refuse it with its own (audit.reason_required), so the screen can say what is missing.
    with shop_context(juma.shop_id):
        if action == "unblock":
            block(laptop, by=juma, reason="Imeibiwa kaunta")
        status = Device.objects.get(pk=laptop.pk).status
        lines = len(lines_about(laptop))
        with pytest.raises(ValidationError) as refused:
            (block if action == "block" else unblock)(laptop, by=juma, reason="   ")
        assert refused.value.code == "device.reason_required"
        assert Device.objects.get(pk=laptop.pk).status == status
        assert len(lines_about(laptop)) == lines


def test_only_an_active_device_is_blocked(juma: StaffMember, laptop: Device) -> None:
    # A status moves only the way it can: a second block, or an unblock of an active device, is refused, and writes
    # no line that would tell of a change that never happened.
    with shop_context(juma.shop_id):
        with pytest.raises(ValidationError) as unblocking_active:
            unblock(laptop, by=juma, reason="Haikuwa imezuiwa")
        block(laptop, by=juma, reason="Imeibiwa kaunta")
        # The copy handed in still says "active": the service reads the device as stored, locked.
        with pytest.raises(ValidationError) as blocking_again:
            block(laptop, by=juma, reason="Tena")
        assert unblocking_active.value.code == "device.not_blocked"
        assert blocking_again.value.code == "device.not_active"
        assert [line.action for line in lines_about(laptop)] == [AuditAction.DEVICE_BLOCK]


def test_unblock_keeps_the_key(juma: StaffMember, laptop: Device) -> None:
    # Blocking stops the key without forgetting it: a device that comes back still holds its unsent sales, and its
    # same key delivers them (03 §5.9; Jack, AUTH-1).
    with shop_context(juma.shop_id):
        block(laptop, by=juma, reason="Imeibiwa kaunta")
        assert Device.objects.get(pk=laptop.pk).key_hash == laptop.key_hash
        back = unblock(laptop, by=juma, reason="Polisi wameirudisha")
    assert back.key_hash == laptop.key_hash


def test_block_needs_device_manage(
    juma: StaffMember, laptop: Device, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Only device.manage on the device's home side (Jack, AUTH-1). A manager of Vyakula alone can't block a Dawa
    # device; nothing is changed or written.
    with shop_context(juma.shop_id):
        vyakula = add_side(shop=staff_a2.shop, code="F", name="Vyakula", by=None)
    give_role(staff_a2, RoleTemplate.MANAGER, vyakula)
    with shop_context(juma.shop_id):
        with pytest.raises(PermissionDenied):
            block(laptop, by=staff_a2, reason="Imeibiwa kaunta")
        assert Device.objects.get(pk=laptop.pk).status == DeviceStatus.ACTIVE
        assert not AuditEvent.objects.exists()
        # Nor unblock one: Juma blocks, and the Vyakula manager can't undo it.
        block(laptop, by=juma, reason="Imeibiwa kaunta")
        with pytest.raises(PermissionDenied):
            unblock(laptop, by=staff_a2, reason="Nimeipata")
        assert Device.objects.get(pk=laptop.pk).status == DeviceStatus.BLOCKED


@pytest.mark.parametrize("gone", ["suspended", "left"])
def test_manager_who_cannot_act_cannot_block(juma: StaffMember, laptop: Device, side_a: Side, gone: str) -> None:
    # A suspended manager, or one who has left, holds nothing (02 §5, X2): Juma can neither block the laptop nor let a
    # blocked phone work again, and nothing is written.
    phone = pair(juma, side_a, "Simu ya Dawa")
    with shop_context(juma.shop_id):
        block(phone, by=juma, reason="Imepotea")
        if gone == "suspended":
            suspend(juma, by=None, reason="Uchunguzi")
        else:
            mark_left(juma, left_on=juma.started_on, by=None, reason="Amehamia Moshi")
        with pytest.raises(PermissionDenied):
            block(laptop, by=juma, reason="Imeibiwa kaunta")
        with pytest.raises(PermissionDenied):
            unblock(phone, by=juma, reason="Imepatikana")
        assert Device.objects.get(pk=laptop.pk).status == DeviceStatus.ACTIVE
        assert Device.objects.get(pk=phone.pk).status == DeviceStatus.BLOCKED
        assert AuditEvent.objects.filter(subject_type="device").count() == 1  # the phone's block, from before


def test_manager_of_another_shop_cannot_block(
    juma: StaffMember, laptop: Device, staff_b: StaffMember, side_b: Side, give_role: GiveRole
) -> None:
    # T1: shop B's manager, in their own shop's visit, can't touch shop A's device, whatever they hold in B.
    give_role(staff_b, RoleTemplate.MANAGER, None)
    with shop_context(staff_b.shop_id):
        with pytest.raises(ValidationError) as blocking:
            block(laptop, by=staff_b, reason="Imeibiwa kaunta")
        with pytest.raises(ValidationError) as unblocking:
            unblock(laptop, by=staff_b, reason="Imepatikana")
    assert blocking.value.code == unblocking.value.code == "staff.other_shop"
    with shop_context(juma.shop_id):
        assert Device.objects.get(pk=laptop.pk).status == DeviceStatus.ACTIVE
        assert not AuditEvent.objects.exists()


def test_device_code_never_reused(juma: StaffMember, laptop: Device, side_a: Side) -> None:
    # D7: a device code is in every receipt number the device prints, so it is never given twice. A blocked device
    # keeps its code, and the next pairing, perhaps the stolen laptop's replacement, gets a new one.
    with shop_context(juma.shop_id):
        block(laptop, by=juma, reason="Imeibiwa kaunta")
    replacement = pair(juma, side_a, "Laptop mpya ya Dawa")
    phone = pair(juma, side_a, "Simu ya Dawa")
    assert [laptop.code, replacement.code, phone.code] == [1, 2, 3]
