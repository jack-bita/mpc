"""apps/people/tests/test_pairing.py — pairing a new device with a shop (AUTH-1; 02 §5, 03 §5.9).

A new device asks to join (start_pairing): it gets an 8-character code to show on its screen and its secret key,
and waits in a PairingRequest, which belongs to no shop. A manager with device.manage types the code on their own
phone, names the device and picks its home side (confirm_pairing): the Device is made in the manager's shop, with
the shop's next device code and the key's hash, and the key works from then on.

These tests pin the card's rules: a code works once and for 10 minutes, has no look-alike characters, and may be
typed in any case, with spaces or a dash; only device.manage confirms, asked before the code is even looked at; the
key is kept only as its hash; the device is made in the confirming manager's shop, under a name no other device of
that shop has. Blocking, and device codes never reused after one, are in test_blocking.py. Fake data only: the repo
is public (03 §10).
"""

import hashlib
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people import services
from apps.people.device_keys import PAIRING_CODE_ALPHABET, PAIRING_CODE_LENGTH
from apps.people.models import Device, DeviceStatus, PairingRequest, StaffMember
from apps.people.services import confirm_pairing, start_pairing
from apps.shops.models import Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def manager_a(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    # Shop A's manager on every side: the Manager role holds device.manage (apps/core/permissions.py).
    give_role(staff_a, RoleTemplate.MANAGER, None)
    return staff_a


def confirm(code: str, by: StaffMember, side: Side, name: str = "Laptop ya Dawa") -> Device:
    # The manager's phone confirms inside its own visit, so their shop is open, as an office route opens it.
    with shop_context(by.shop_id):
        return confirm_pairing(code, name=name, home_side=side, by=by)


def test_start_pairing_belongs_to_no_shop() -> None:
    # The new device has no login and no shop yet: asking needs no shop open, and the request names none (02 v1.11).
    asked = start_pairing()
    request = PairingRequest.objects.get(pk=asked.request.pk)
    assert not hasattr(request, "shop_id")
    assert request.device_id is None and request.confirmed_at is None


def test_pairing_code_has_no_look_alikes() -> None:
    # 8 characters, with none a person could misread from a screen: no 0 or O, no 1, I or L.
    assert set("0O1IL").isdisjoint(PAIRING_CODE_ALPHABET)
    codes = [start_pairing().request.code for _ in range(50)]
    assert all(len(code) == PAIRING_CODE_LENGTH and set(code) <= set(PAIRING_CODE_ALPHABET) for code in codes)
    # Drawn at random, not counted: 50 asks give 50 different codes.
    assert len(set(codes)) == len(codes)


def test_pairing_code_clash_draws_again(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every code ever given stays taken, so a manager's code can only ever mean one request. A new draw that hits a
    # code already given is drawn again, never refused: the device doesn't care which code it shows.
    first = start_pairing().request.code
    draws = iter([first, "ABCDEFGH"])
    monkeypatch.setattr(services, "make_pairing_code", lambda: next(draws))
    assert start_pairing().request.code == "ABCDEFGH"
    # Five clashes in a row would mean a bug, not bad luck: it stops loudly instead of drawing forever.
    monkeypatch.setattr(services, "make_pairing_code", lambda: first)
    with pytest.raises(RuntimeError, match="No free pairing code"):
        start_pairing()
    # Any other broken rule is a bug too, raised as it is, never drawn again: here a code of the wrong shape.
    monkeypatch.setattr(services, "make_pairing_code", lambda: "abcdefgh")
    with pytest.raises(IntegrityError, match="people_pairingrequest_code_shape"):
        start_pairing()


def test_device_key_stored_hashed(manager_a: StaffMember, side_a: Side) -> None:
    # The key is a secret the device keeps; the server keeps only its SHA-256 hash, on the request and then on the
    # device, so a stolen copy of the database can't pretend to be the device (03 §5.9).
    asked = start_pairing()
    key_hash = hashlib.sha256(asked.key.encode()).hexdigest()
    assert len(asked.key) >= 43  # 32 random bytes, written in 43 URL-safe characters
    device = confirm(asked.request.code, manager_a, side_a)
    for row in (PairingRequest.objects.get(pk=asked.request.pk), device):
        assert row.key_hash == key_hash
        assert asked.key not in [str(value) for value in row.__dict__.values()]


def test_device_made_in_the_confirmers_shop(manager_a: StaffMember, side_a: Side) -> None:
    # The device is born active in the manager's shop, with the shop's first device code; who confirmed it is its
    # `created_by` (02 v1.11). The request now names the device it became.
    asked = start_pairing()
    device = confirm(asked.request.code, manager_a, side_a)
    assert (device.shop_id, device.home_side_id, device.name, device.code) == (
        manager_a.shop_id,
        side_a.pk,
        "Laptop ya Dawa",
        1,
    )
    assert device.status == DeviceStatus.ACTIVE
    assert device.created_by_id == manager_a.pk
    request = PairingRequest.objects.get(pk=asked.request.pk)
    assert request.device_id == device.pk and request.confirmed_at is not None


def test_pairing_code_single_use(manager_a: StaffMember, side_a: Side) -> None:
    # A code read over a shoulder can't pair a second device.
    code = start_pairing().request.code
    confirm(code, manager_a, side_a)
    with pytest.raises(ValidationError) as refused:
        confirm(code, manager_a, side_a, name="Simu ya Vyakula")
    assert refused.value.code == "pairing.code_used"
    with shop_context(manager_a.shop_id):
        assert Device.objects.count() == 1


def test_pairing_code_expires(manager_a: StaffMember, side_a: Side) -> None:
    # Valid 10 minutes from the ask, then refused: the manager asks the device for a new one.
    before = timezone.now()
    asked = start_pairing()
    after = timezone.now()
    assert before + timedelta(minutes=10) <= asked.request.expires_at <= after + timedelta(minutes=10)
    # Ten minutes and a second pass: the request is made that much older, both its times at once, with no clock to fake.
    # (Its expiry alone can't move before its ask: the database refuses it, people_pairingrequest_expires_after_asked.)
    older = timedelta(minutes=10, seconds=1)
    PairingRequest.objects.filter(pk=asked.request.pk).update(
        created_at=F("created_at") - older, expires_at=F("expires_at") - older
    )
    with pytest.raises(ValidationError) as refused:
        confirm(asked.request.code, manager_a, side_a)
    assert refused.value.code == "pairing.code_expired"
    with shop_context(manager_a.shop_id):
        assert not Device.objects.exists()


def test_unknown_code_refused(manager_a: StaffMember, side_a: Side) -> None:
    with pytest.raises(ValidationError) as refused:
        confirm("ABCDEFGH", manager_a, side_a)
    assert refused.value.code == "pairing.code_unknown"


def test_typed_code_is_cleaned(manager_a: StaffMember, side_a: Side) -> None:
    # A manager types what the screen shows, perhaps in small letters, with the dash it is shown with, or a space.
    code = start_pairing().request.code
    typed = f" {code[:4].lower()}-{code[4:].lower()} "
    assert confirm(typed, manager_a, side_a).code == 1


def test_confirm_needs_device_manage(
    staff_a: StaffMember, staff_a2: StaffMember, side_a: Side, give_role: GiveRole
) -> None:
    # A seller holds no device.manage: refused, and the code still waits for someone who does.
    give_role(staff_a, RoleTemplate.SELLER, None)
    code = start_pairing().request.code
    with pytest.raises(PermissionDenied):
        confirm(code, staff_a, side_a)
    # device.manage on another side opens only that side (rule X1): a manager of Vyakula alone can't pair a device
    # whose home is Dawa.
    with shop_context(staff_a2.shop_id):
        vyakula = add_side(shop=staff_a2.shop, code="F", name="Vyakula", by=None)
    give_role(staff_a2, RoleTemplate.MANAGER, vyakula)
    with pytest.raises(PermissionDenied):
        confirm(code, staff_a2, side_a)
    # ...but can on their own side, with the same code, still unused.
    assert confirm(code, staff_a2, vyakula).home_side_id == vyakula.pk


def test_confirm_checks_permission_before_the_code(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> None:
    # Someone without device.manage learns nothing about codes: a made-up code is refused for the permission, not as
    # "unknown", so trying codes tells them nothing.
    give_role(staff_a, RoleTemplate.SELLER, None)
    with pytest.raises(PermissionDenied):
        confirm("ABCDEFGH", staff_a, side_a)


def test_home_side_of_another_shop_refused(manager_a: StaffMember, side_b: Side) -> None:
    # T1: a device of shop A can't live on shop B's side.
    code = start_pairing().request.code
    with pytest.raises(ValidationError) as refused:
        confirm(code, manager_a, side_b)
    assert refused.value.code == "staff.other_shop"
    assert PairingRequest.objects.get(code=code).device_id is None


def test_device_names_unique_in_a_shop(manager_a: StaffMember, side_a: Side) -> None:
    # The manager's device list must tell devices apart: one name per shop, whatever the letter case, spaces trimmed.
    confirm(start_pairing().request.code, manager_a, side_a, name="Laptop ya Dawa")
    code = start_pairing().request.code
    with pytest.raises(ValidationError) as refused:
        confirm(code, manager_a, side_a, name=" laptop ya dawa ")
    assert [error.code for error in refused.value.error_dict["__all__"]] == ["device.name_taken"]
    # Refused whole: the code still waits, and the device code taken for it went back, so the next device is 2.
    assert PairingRequest.objects.get(code=code).device_id is None
    assert confirm(code, manager_a, side_a, name="Simu ya Vyakula").code == 2
