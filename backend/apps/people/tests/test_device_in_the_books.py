"""apps/people/tests/test_device_in_the_books.py — X3: both books name the person and the device, through real logins
and real routes (AUTH-8; 03 §5.16).

A manager blocks a stolen phone. One action writes a line in each book, the edit history's by the trigger and the audit
book's by the service, and both read one note the visit leaves for PostgreSQL (apps/core/acting.py):

    how the manager logged in            both books say
    a PIN on Laptop ya Dawa              the manager, Laptop ya Dawa
    a password on their own phone        the manager, no device
    a password on Laptop ya Dawa         the manager, no device: a password shows no device (the card's choice)

The block goes through editing() (apps/core/editing.py), which opens an inner block of its own for `by`: so the first
row also proves that it keeps the device. The trigger's and audit()'s own tests are in apps/control/tests/, on the
test-only probe tables.

Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable

import pytest
from django.db import connection, transaction
from rest_framework.test import APIClient

from apps.control.models import AuditAction, AuditEvent, EditEvent
from apps.core.acting import DEVICE_SETTING, SHOP_SETTING, acting_as, current_device_id
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import block, confirm_pairing, set_pin, start_pairing, suspend
from apps.shops.models import Side
from tests.concurrency import in_another_transaction

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes and the cookie's name, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
PIN_LOGIN = "/api/auth/pin-login/"
SESSION = "/_allauth/browser/v1/auth/session"
PASSWORD_LOGIN = "/_allauth/browser/v1/auth/login"
DEVICES = "/api/v1/people/devices/"
KEY_COOKIE = "device_key"

PIN = "4829"
PASSWORD = "a-long-test-password"
PHONE = "+255712345678"
REASON = "Imeibiwa kaunta"


def pair(manager: StaffMember, side: Side, name: str) -> tuple[Device, str]:
    # A device paired the way the app pairs one: it asks and keeps its key, and a manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        return confirm_pairing(asked.request.code, name=name, home_side=side, by=manager), asked.key


def by_pin(staff: StaffMember, key: str) -> APIClient:
    # A browser that holds this device's key, after this person typed their PIN there.
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    assert client.post(PIN_LOGIN, {"staff": str(staff.pk), "pin": PIN}, format="json").status_code == 204
    return client


def by_password(staff: StaffMember) -> APIClient:
    # A browser logged in with a password through allauth's route, holding no device's key.
    user = User.objects.get(pk=staff.user_id)
    user.phone = PHONE
    user.set_password(PASSWORD)
    user.save()
    client = APIClient()
    client.get(SESSION)
    login = client.post(
        PASSWORD_LOGIN,
        {"phone": PHONE, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert login.status_code == 200
    return client


def blocks(client: APIClient, device: Device) -> None:
    answer = client.post(f"{DEVICES}{device.pk}/block/", {"reason": REASON}, format="json")
    assert answer.status_code == 200


def both_books(device: Device) -> tuple[EditEvent, AuditEvent]:
    # The one line each book holds about this device. Its pairing wrote none: the history records edits, not a new row.
    with shop_context(device.shop_id):
        edit = EditEvent.objects.get(subject_type="device", subject_id=device.pk)
        line = AuditEvent.objects.get(subject_type="device", subject_id=device.pk, action=AuditAction.DEVICE_BLOCK)
    return edit, line


@pytest.fixture
def manager(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    with shop_context(staff_a2.shop_id):
        return set_pin(staff_a2, PIN, by=None)


@pytest.fixture
def paired(manager: StaffMember, side_a: Side) -> tuple[Device, str]:
    return pair(manager, side_a, "Laptop ya Dawa")


@pytest.fixture
def stolen_phone(manager: StaffMember, side_a: Side) -> Device:
    return pair(manager, side_a, "Simu ya Dawa")[0]


def test_pin_session_names_the_person_and_the_device_in_both_books(
    manager: StaffMember, paired: tuple[Device, str], stolen_phone: Device
) -> None:
    # Done when #1. Both lines name the same person and the same laptop, the one that made the change, not the phone
    # the change was made to.
    laptop, key = paired
    blocks(by_pin(manager, key), stolen_phone)
    edit, line = both_books(stolen_phone)
    assert (edit.created_by_id, edit.device_id) == (manager.pk, laptop.pk)
    assert (line.created_by_id, line.device_id) == (manager.pk, laptop.pk)


def test_visit_without_a_device_names_none(manager: StaffMember, stolen_phone: Device) -> None:
    # Done when #2. A password on a person's own phone: the person is named, and the link stays empty, in both books.
    blocks(by_password(manager), stolen_phone)
    edit, line = both_books(stolen_phone)
    assert (edit.created_by_id, edit.device_id) == (manager.pk, None)
    assert (line.created_by_id, line.device_id) == (manager.pk, None)


def test_password_on_a_paired_laptop_names_no_device(
    manager: StaffMember, paired: tuple[Device, str], stolen_phone: Device
) -> None:
    # A limit chosen on the card: a password's session never reads the device's key, though the cookie is there, so it
    # names no device. Pinned here so that changing it is a decision, not an accident.
    client = by_password(manager)
    client.cookies[KEY_COOKIE] = paired[1]
    blocks(client, stolen_phone)
    edit, line = both_books(stolen_phone)
    assert (edit.device_id, line.device_id) == (None, None)


def test_visit_with_no_device_clears_one_left_on_the_connection(
    manager: StaffMember, paired: tuple[Device, str], stolen_phone: Device
) -> None:
    # A visit always says which device it has, even "none", and never trusts what the connection holds: both books are
    # append-only, so a stale laptop on a password's line would stay there for good. acting_as() puts its values back as
    # a visit ends, so this can't happen today; planted here by hand, the way a bug would leave it.
    client = by_password(manager)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, false), set_config(%s, %s, false)",
            [SHOP_SETTING, str(manager.shop_id), DEVICE_SETTING, str(paired[0].pk)],
        )
    blocks(client, stolen_phone)
    edit, line = both_books(stolen_phone)
    assert (edit.device_id, line.device_id) == (None, None)


def test_visit_leaves_no_device_on_the_connection(
    manager: StaffMember, paired: tuple[Device, str], stolen_phone: Device
) -> None:
    # The server may keep a database connection open for the next visit (CONN_MAX_AGE; not set today, so it closes each
    # one), and the settings live on it. The next person on it, on their own phone, must not be recorded as standing at
    # this laptop. Test clients share this test's one connection, so it stands in for that.
    blocks(by_pin(manager, paired[1]), stolen_phone)
    assert current_device_id(manager.shop_id) is None

    unblocked = by_password(manager).post(
        f"{DEVICES}{stolen_phone.pk}/unblock/", {"reason": "Imepatikana"}, format="json"
    )
    assert unblocked.status_code == 200
    with shop_context(manager.shop_id):
        block_edit, unblock_edit = EditEvent.objects.filter(subject_id=stolen_phone.pk).order_by("id")
    assert (block_edit.device_id, unblock_edit.device_id) == (paired[0].pk, None)


@pytest.mark.django_db(transaction=True)
def test_two_managers_blocking_each_others_devices_both_go_through(
    manager: StaffMember,
    staff_a: StaffMember,
    paired: tuple[Device, str],
    stolen_phone: Device,
    give_role: GiveRole,
) -> None:
    # A block is urgent. One manager, at the laptop, blocks the phone, while another, at the phone, blocks the laptop.
    # Each book line links to the device it was made on, and at its commit PostgreSQL checks that link, which needs a
    # light lock on that device's row. If each block held the row it changes with a full lock, each would wait for the
    # other's: PostgreSQL would cancel one after a second, and that manager would get a server error. So the second must
    # finish while the first is still open.
    laptop = paired[0]
    give_role(staff_a, RoleTemplate.MANAGER, None)

    def second_manager_blocks_the_laptop() -> Device:
        with shop_context(staff_a.shop_id), acting_as(staff_a, device=stolen_phone):
            return block(laptop, by=staff_a, reason=REASON)

    with shop_context(manager.shop_id), acting_as(manager, device=laptop), transaction.atomic():
        block(stolen_phone, by=manager, reason=REASON)
        second, ended = in_another_transaction(second_manager_blocks_the_laptop)
        second.join(timeout=5)
        assert not second.is_alive(), "The second block is waiting for the first: at its commit, they would deadlock."

    assert isinstance(ended[0], Device)
    assert both_books(stolen_phone)[0].device_id == laptop.pk
    assert both_books(laptop)[0].device_id == stolen_phone.pk


def test_staff_action_names_the_device(manager: StaffMember, staff_a: StaffMember, paired: tuple[Device, str]) -> None:
    # The other inner block: the staff actions save through _save (apps/people/services.py), not editing(), and their
    # route comes with PPL-4. The manager suspends Asha at the laptop, as a visit opens it, and both books say so.
    laptop = paired[0]
    with shop_context(manager.shop_id), acting_as(manager, device=laptop):
        suspend(staff_a, by=manager, reason="Hakuja kazini siku 3")
        edit = EditEvent.objects.get(subject_type="staff", subject_id=staff_a.pk)
        line = AuditEvent.objects.get(subject_type="staff", subject_id=staff_a.pk)
    assert (edit.created_by_id, edit.device_id) == (manager.pk, laptop.pk)
    assert (line.created_by_id, line.device_id) == (manager.pk, laptop.pk)
