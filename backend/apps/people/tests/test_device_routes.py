"""apps/people/tests/test_device_routes.py — the office routes for a shop's devices, /api/v1/people/devices/ (AUTH-5;
03 §5.9, §5.10).

A manager says yes to a waiting device from their own phone: they type the code it shows, name it and pick its home
side, and the phone sends the new device's id with them (ADR-0007), so a double tap, or a send again after a lost
answer, makes one device and gets the first answer back. The device list shows a shop's devices, with when each was
last seen. From the list, a manager renames a device, blocks it when it is stolen, and unblocks it when it is back,
each block and unblock with a reason (03 §5.9, step 4).

Who may do what (Jack, 2 Nov 2026):

    shop MFANO, sides Dawa (D) and Vyakula (F)
    who                          sees the list of     confirms, renames, blocks and unblocks a device on
    Baba, the owner              Dawa, Vyakula        Dawa, Vyakula
    Neema, manager of Vyakula    Vyakula              Vyakula
    Asha, seller on Dawa         Dawa                 none: she has no device.manage

A side a person doesn't see is "not found", as another shop's is (PPL-5). Fake data only: the repo is public (03 §10).
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.control.models import AuditAction, AuditEvent
from apps.core.api import base
from apps.core.api.base import CreateOnceMixin
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.api.authentication import DEVICE_KEY_COOKIE
from apps.people.api.views import DeviceViewSet
from apps.people.models import Device, PairingRequest, StaffMember, User
from apps.people.services import add_staff, confirm_pairing, start_pairing
from apps.shops.models import Shop, Side
from apps.shops.services import add_side

pytestmark = pytest.mark.django_db

DEVICES = "/api/v1/people/devices/"
ME = "/api/devices/v1/me/"

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def vyakula(shop_a: Shop, side_a: Side) -> Side:
    # Shop A's second side, beside Dawa (side_a).
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


@pytest.fixture
def baba(staff_a: StaffMember, give_role: GiveRole) -> StaffMember:
    # The owner: every key, on every side.
    give_role(staff_a, RoleTemplate.OWNER, None)
    return staff_a


def person(shop: Shop, name: str, role: RoleTemplate, side: Side | None, give_role: GiveRole) -> StaffMember:
    # A staff member of the shop with one role, on one side or on every side.
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        staff = add_staff(shop=shop, user=user, display_name=name, by=None)
    give_role(staff, role, side)
    return staff


@pytest.fixture
def neema(shop_a: Shop, vyakula: Side, give_role: GiveRole) -> StaffMember:
    # The Vyakula manager: device.manage, on Vyakula only.
    return person(shop_a, "Neema", RoleTemplate.MANAGER, vyakula, give_role)


@pytest.fixture
def asha(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    # A seller on Dawa: she sees Dawa, and holds no device.manage.
    return person(shop_a, "Asha", RoleTemplate.SELLER, side_a, give_role)


@pytest.fixture
def zawadi(shop_a: Shop, side_a: Side, vyakula: Side, give_role: GiveRole) -> StaffMember:
    # The manager of Vyakula, who also sells on Dawa: she sees both sides, and holds device.manage on Vyakula only.
    staff = person(shop_a, "Zawadi", RoleTemplate.MANAGER, vyakula, give_role)
    give_role(staff, RoleTemplate.SELLER, side_a)
    return staff


def client_of(staff: StaffMember) -> APIClient:
    # Logged in as this staff member, as backend/conftest.py's staff clients are: the logins come later (AUTH-3,
    # AUTH-4) and will leave the staff member in `request.auth`.
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def confirm_form(code: str, side: Side, name: str = "Laptop ya Dawa") -> dict[str, str]:
    # What the manager's phone sends: the new device's id it made itself (ADR-0007), the code the device shows, as a
    # person types it, the name and the home side.
    return {"id": str(uuid.uuid7()), "pairing_code": code, "name": name, "home_side": str(side.pk)}


def pair(by: StaffMember, side: Side, name: str) -> Device:
    # A device paired straight through the services, for the tests about the list.
    code = start_pairing().request.code
    with shop_context(by.shop_id):
        return confirm_pairing(code, name=name, home_side=side, by=by)


def still_waiting(code: str) -> bool:
    return PairingRequest.objects.get(code=code).device_id is None


def test_manager_confirms_a_waiting_device(baba: StaffMember, side_a: Side) -> None:
    # 03 §5.9, steps 1 to 3, end to end: the laptop asks, the owner says yes from their phone, and the laptop's key
    # then opens its shop.
    asked = start_pairing()
    sent = confirm_form(asked.request.code.lower(), side_a)

    response = client_of(baba).post(DEVICES, sent)

    assert response.status_code == 201
    row = response.json()
    assert (row["id"], row["name"], row["code"], row["home_side"], row["status"], row["last_seen_at"]) == (
        sent["id"],
        "Laptop ya Dawa",
        1,
        str(side_a.pk),
        "active",
        None,
    )
    laptop = APIClient()
    laptop.cookies[DEVICE_KEY_COOKIE] = asked.key
    me = laptop.get(ME)
    assert me.status_code == 200
    assert me.json()["device"]["id"] == sent["id"]


def test_confirm_sent_twice_makes_one_device(baba: StaffMember, side_a: Side, shop_a: Shop) -> None:
    # A double tap, or the phone sending again after a lost answer: the same id names the same confirm. The second
    # answer is the first's, with the same 201, and not pairing.code_used (AUTH-2's note).
    sent = confirm_form(start_pairing().request.code, side_a)
    client = client_of(baba)

    first = client.post(DEVICES, sent)
    again = client.post(DEVICES, sent)

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    with shop_context(shop_a):
        assert Device.objects.count() == 1


def test_confirm_sent_twice_at_once_makes_one_device(
    baba: StaffMember, side_a: Side, shop_a: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The two copies arrive together: the second looks for its id before the first has made the device, so it goes on
    # to confirm the code itself, and is refused, the code being used by then (pairing.code_used). That is the first
    # copy's own work: the second looks again, finds the device by its id, and answers with it. Played one after the
    # other: the second copy's first look is made to find nothing, as it would have, had it run before the first
    # finished (as in apps/shops/tests/test_api_sides.py).
    sent = confirm_form(start_pairing().request.code, side_a)
    client = client_of(baba)
    first = client.post(DEVICES, sent)
    real_stored = CreateOnceMixin._stored
    looks: list[object] = []

    def first_look_too_early(view: CreateOnceMixin[Device], row_id: object) -> Any:
        looks.append(row_id)
        return None if len(looks) == 1 else real_stored(view, row_id)

    monkeypatch.setattr(CreateOnceMixin, "_stored", first_look_too_early)

    again = client.post(DEVICES, sent)

    assert len(looks) == 2
    assert again.status_code == 201
    assert again.json() == first.json()
    with shop_context(shop_a):
        assert Device.objects.count() == 1


def test_confirm_needs_device_manage_on_the_home_side(asha: StaffMember, side_a: Side) -> None:
    # Asha sees Dawa, but holds no device.manage: refused (403), and the code still waits for a manager.
    code = start_pairing().request.code

    response = client_of(asha).post(DEVICES, confirm_form(code, side_a))

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert still_waiting(code)


def test_confirm_on_a_side_not_seen_finds_no_side(neema: StaffMember, side_a: Side) -> None:
    # Neema manages Vyakula only, so Dawa is hidden from her: "not found", as another shop's side is (PPL-5), never a
    # 403 that would tell her it exists.
    code = start_pairing().request.code

    response = client_of(neema).post(DEVICES, confirm_form(code, side_a))

    assert response.status_code == 400
    assert response.json()["fields"] == {"home_side": ["does_not_exist"]}
    assert still_waiting(code)


def test_confirm_refuses_another_shops_side(baba: StaffMember, side_b: Side) -> None:
    # T1: a device of shop A lives on a side of shop A. Shop B's side is not found.
    code = start_pairing().request.code

    response = client_of(baba).post(DEVICES, confirm_form(code, side_b))

    assert response.status_code == 400
    assert response.json()["fields"] == {"home_side": ["does_not_exist"]}
    assert still_waiting(code)


@pytest.mark.parametrize(
    ("name", "answer"),
    [
        # A name no device of the shop has: the id is all that is wrong.
        ("Simu ya Vyakula", {"code": "invalid", "fields": {"id": ["id.taken"]}}),
        # The Dawa laptop's own name too: the name is what is wrong, as for any id no shop has.
        ("Laptop ya Dawa", {"code": "device.name_taken", "fields": {}}),
    ],
)
def test_a_taken_id_is_refused_alike_wherever_it_is_taken(
    baba: StaffMember,
    neema: StaffMember,
    side_a: Side,
    vyakula: Side,
    staff_b: StaffMember,
    side_b: Side,
    give_role: GiveRole,
    name: str,
    answer: dict[str, object],
) -> None:
    # Neema's phone sends an id already taken: by Dawa's laptop, on a side hidden from her, or by a device of another
    # shop. Both answers are the same, whatever else is wrong, and say nothing about that device, not even that it is
    # in her shop (03 §5.4; CreateOnceMixin, apps/core/api/base.py).
    dawa_laptop = pair(baba, side_a, "Laptop ya Dawa")
    give_role(staff_b, RoleTemplate.OWNER, None)
    other_shops = pair(staff_b, side_b, "Simu ya Jingine")
    neema_client = client_of(neema)

    answers = [
        neema_client.post(
            DEVICES, {**confirm_form(start_pairing().request.code, vyakula, name=name), "id": str(taken.pk)}
        )
        for taken in (dawa_laptop, other_shops)
    ]

    shown = [{"code": sent.json()["code"], "fields": sent.json()["fields"]} for sent in answers]
    assert [sent.status_code for sent in answers] == [400, 400]
    assert shown == [answer, answer]


def test_device_list_keeps_to_the_persons_sides(
    baba: StaffMember,
    neema: StaffMember,
    side_a: Side,
    vyakula: Side,
    staff_b: StaffMember,
    side_b: Side,
    give_role: GiveRole,
) -> None:
    # The owner sees both sides' devices; Neema sees Vyakula's only. Shop B's device, paired by shop B's owner, shows
    # to nobody here.
    laptop = pair(baba, side_a, "Laptop ya Dawa")
    phone = pair(baba, vyakula, "Simu ya Vyakula")
    give_role(staff_b, RoleTemplate.OWNER, None)
    pair(staff_b, side_b, "Simu ya Jingine")

    def listed(staff: StaffMember) -> set[str]:
        response = client_of(staff).get(DEVICES)
        assert response.status_code == 200
        return {row["id"] for row in response.json()["results"]}

    assert listed(baba) == {str(laptop.pk), str(phone.pk)}
    assert listed(neema) == {str(phone.pk)}
    # And one device read alone: Dawa's laptop is "not found" for Neema, as if it didn't exist.
    assert client_of(neema).get(f"{DEVICES}{laptop.pk}/").status_code == 404
    assert client_of(baba).get(f"{DEVICES}{laptop.pk}/").json()["name"] == "Laptop ya Dawa"


def test_seller_sees_the_list(baba: StaffMember, asha: StaffMember, side_a: Side, vyakula: Side) -> None:
    # Jack's choice (2 Nov 2026): whoever works on a side sees its devices, but changes none of them. Asha, a seller on
    # Dawa, sees "Laptop ya Dawa" and when it was last seen; Vyakula's phone stays hidden from her.
    laptop = pair(baba, side_a, "Laptop ya Dawa")
    pair(baba, vyakula, "Simu ya Vyakula")

    response = client_of(asha).get(DEVICES)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == [str(laptop.pk)]


def test_device_rows_never_show_the_key_hash(baba: StaffMember, side_a: Side) -> None:
    # A key's hash never leaves the server (03 §5.9): not as a field, nor anywhere in the answer.
    laptop = pair(baba, side_a, "Laptop ya Dawa")

    response = client_of(baba).get(DEVICES)

    assert set(response.json()["results"][0]) == {
        "id",
        "name",
        "code",
        "home_side",
        "status",
        "last_seen_at",
        "created_at",
        "updated_at",
        "version",
    }
    assert laptop.key_hash not in response.content.decode()


def test_manager_renames_a_device(baba: StaffMember, side_a: Side) -> None:
    # The Dawa laptop moves to the front counter. A second screen, opened before the rename, still holds the old
    # version: its rename is refused (409), never one that undoes the first (02 §1).
    laptop = pair(baba, side_a, "Laptop ya Dawa")
    client = client_of(baba)

    renamed = client.patch(f"{DEVICES}{laptop.pk}/", {"name": "Laptop ya Kaunta", "version": laptop.version})
    stale = client.patch(f"{DEVICES}{laptop.pk}/", {"name": "Laptop ya Stoo", "version": laptop.version})

    assert renamed.status_code == 200
    assert (renamed.json()["name"], renamed.json()["version"]) == ("Laptop ya Kaunta", laptop.version + 1)
    assert stale.status_code == 409
    assert stale.json()["code"] == "version_conflict"


def test_manager_blocks_and_unblocks_with_a_reason(baba: StaffMember, side_a: Side, shop_a: Shop) -> None:
    # The laptop is stolen from the counter: blocked from the owner's phone, its key opens nothing from its next
    # request. The police bring it back: unblocked, the same key works again, so the records it holds can still
    # arrive (AUTH-1). Each with its line in the audit trail, with why.
    asked = start_pairing()
    with shop_context(shop_a):
        laptop_row = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side_a, by=baba)
    laptop = APIClient()
    laptop.cookies[DEVICE_KEY_COOKIE] = asked.key
    manager = client_of(baba)

    blocked = manager.post(f"{DEVICES}{laptop_row.pk}/block/", {"reason": "Imeibiwa kaunta"})
    refused = laptop.get(ME)
    unblocked = manager.post(f"{DEVICES}{laptop_row.pk}/unblock/", {"reason": "Polisi wameirudisha"})

    assert (blocked.status_code, blocked.json()["status"]) == (200, "blocked")
    assert (refused.status_code, refused.json()["code"]) == (401, "device.blocked")
    assert (unblocked.status_code, unblocked.json()["status"]) == (200, "active")
    assert laptop.get(ME).status_code == 200
    with shop_context(shop_a):
        lines = AuditEvent.objects.filter(subject_type="device", subject_id=laptop_row.pk).order_by("id")
        assert [(line.action, line.reason) for line in lines] == [
            (AuditAction.DEVICE_BLOCK, "Imeibiwa kaunta"),
            (AuditAction.DEVICE_UNBLOCK, "Polisi wameirudisha"),
        ]


@pytest.mark.parametrize(
    ("sent", "code", "fields"),
    [({"reason": "  "}, "device.reason_required", {}), ({}, "invalid", {"reason": ["required"]})],
)
def test_block_needs_a_reason(
    baba: StaffMember, side_a: Side, shop_a: Shop, sent: dict[str, str], code: str, fields: dict[str, list[str]]
) -> None:
    # Rule 7: a block is always written with why. A blank reason reaches the service and comes back with its own code,
    # which the screen translates; none at all is the form's own "required". Either way the device keeps working.
    laptop = pair(baba, side_a, "Laptop ya Dawa")

    response = client_of(baba).post(f"{DEVICES}{laptop.pk}/block/", sent)

    assert response.status_code == 400
    assert (response.json()["code"], response.json()["fields"]) == (code, fields)
    with shop_context(shop_a):
        assert Device.objects.get(pk=laptop.pk).status == "active"


def test_seller_cannot_rename_block_or_unblock(
    baba: StaffMember, asha: StaffMember, side_a: Side, shop_a: Shop
) -> None:
    # Asha sees the Dawa laptop on the list (Jack's A), but holds no device.manage: each change is refused (403), and
    # the device stays as it was. One device blocked by the owner, for her unblock to be tried on.
    laptop = pair(baba, side_a, "Laptop ya Dawa")
    phone = pair(baba, side_a, "Simu ya Dawa")
    client_of(baba).post(f"{DEVICES}{phone.pk}/block/", {"reason": "Imepotea"})
    asha_client = client_of(asha)

    tries = [
        asha_client.patch(f"{DEVICES}{laptop.pk}/", {"name": "Laptop ya Asha", "version": laptop.version}),
        asha_client.post(f"{DEVICES}{laptop.pk}/block/", {"reason": "Nimeamua"}),
        asha_client.post(f"{DEVICES}{phone.pk}/unblock/", {"reason": "Nimeipata"}),
    ]

    assert [(answer.status_code, answer.json()["code"]) for answer in tries] == [(403, "permission_denied")] * 3
    with shop_context(shop_a):
        assert Device.objects.get(pk=laptop.pk).name == "Laptop ya Dawa"
        assert Device.objects.get(pk=laptop.pk).status == "active"
        assert Device.objects.get(pk=phone.pk).status == "blocked"


def test_other_sides_manager_cannot_change_the_device(
    baba: StaffMember, neema: StaffMember, side_a: Side, shop_a: Shop
) -> None:
    # Neema manages Vyakula only, so the Dawa laptop is hidden from her: each change is "not found" (404), as for
    # another shop's device, never a 403 that would tell her it exists (PPL-5).
    laptop = pair(baba, side_a, "Laptop ya Dawa")
    neema_client = client_of(neema)

    tries = [
        neema_client.patch(f"{DEVICES}{laptop.pk}/", {"name": "Laptop ya Neema", "version": laptop.version}),
        neema_client.post(f"{DEVICES}{laptop.pk}/block/", {"reason": "Nimeamua"}),
        neema_client.post(f"{DEVICES}{laptop.pk}/unblock/", {"reason": "Nimeipata"}),
    ]

    assert [answer.status_code for answer in tries] == [404] * 3
    with shop_context(shop_a):
        stored = Device.objects.get(pk=laptop.pk)
    assert (stored.name, stored.status) == ("Laptop ya Dawa", "active")


def test_a_manager_of_one_side_changes_only_its_devices(
    baba: StaffMember, zawadi: StaffMember, side_a: Side, vyakula: Side, shop_a: Shop
) -> None:
    # Zawadi manages Vyakula and sells on Dawa. Each change is asked on the device's own home side: never on the whole
    # shop, nor on any side where she holds the key (02 §5). So on Vyakula she confirms, renames, blocks and unblocks;
    # on Dawa, which she sees, each is refused, and nothing changes.
    client = client_of(zawadi)
    made = client.post(DEVICES, confirm_form(start_pairing().request.code, vyakula, name="Simu ya Vyakula"))
    phone = made.json()
    on_vyakula = [
        made,
        client.patch(f"{DEVICES}{phone['id']}/", {"name": "Simu ya Kaunta", "version": phone["version"]}),
        client.post(f"{DEVICES}{phone['id']}/block/", {"reason": "Imepotea"}),
        client.post(f"{DEVICES}{phone['id']}/unblock/", {"reason": "Imepatikana"}),
    ]
    laptop = pair(baba, side_a, "Laptop ya Dawa")
    blocked = pair(baba, side_a, "Simu ya Dawa")
    client_of(baba).post(f"{DEVICES}{blocked.pk}/block/", {"reason": "Imepotea"})
    code = start_pairing().request.code
    on_dawa = [
        client.post(DEVICES, confirm_form(code, side_a, name="Laptop ya Pili")),
        client.patch(f"{DEVICES}{laptop.pk}/", {"name": "Laptop ya Zawadi", "version": laptop.version}),
        client.post(f"{DEVICES}{laptop.pk}/block/", {"reason": "Nimeamua"}),
        client.post(f"{DEVICES}{blocked.pk}/unblock/", {"reason": "Nimeipata"}),
    ]

    assert [answer.status_code for answer in on_vyakula] == [201, 200, 200, 200]
    assert [answer.status_code for answer in on_dawa] == [403, 403, 403, 403]
    assert still_waiting(code)
    with shop_context(shop_a):
        assert (Device.objects.get(pk=laptop.pk).name, Device.objects.get(pk=laptop.pk).status) == (
            "Laptop ya Dawa",
            "active",
        )
        assert Device.objects.get(pk=blocked.pk).status == "blocked"


def test_device_routes_name_their_permissions() -> None:
    # Seeing a side's devices needs only to see the side (Jack, 2 Nov 2026); every change, saying yes to one, renaming
    # it, blocking and unblocking it, needs device.manage on its home side (03 §5.9). Written out in full, so a change
    # to what a route asks for is a change to this test too.
    assert DeviceViewSet.action_permissions == {
        "list": base.SEES_THE_SIDE,
        "retrieve": base.SEES_THE_SIDE,
        "create": Permission.DEVICE_MANAGE,
        "partial_update": Permission.DEVICE_MANAGE,
        "block": Permission.DEVICE_MANAGE,
        "unblock": Permission.DEVICE_MANAGE,
    }
