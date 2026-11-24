"""apps/sync/tests/test_staff_photo_route.py — the address a shop laptop reads a worker's photo at, for their tile on
the PIN screen (PPL-14; 03 §5.13).

Asha's row on the laptop names the photo she shows (StaffRecord), and the laptop asks for that photo, once, and keeps
it, so her face shows with no internet too:

    GET /api/sync/v1/staff-photos/<photo id>/
    the photo a person on the laptop's list shows now     200: the photo, its type as its label, never kept by a cache
    any other photo, and an id no shop has                404 attachment.not_found, alike

A laptop's own list is the rows the pull hands it (staff_rows): the people at work, the suspended among them. The photos
it may read are exactly the ones its rows name, those of the people with a PIN, who log in there, and nothing else of
the shop's: not a clock-in photo, which only whoever manages attendance may open, not a photo a newer one replaced, not
the face of someone who left, was switched off, or never had a PIN. A lost or stolen laptop then holds the faces of the
people who log in at it, and can ask for no more. Every "not found" reads the same, so an answer says nothing of what
the shop keeps.

How a photo is handed out is photo_answer's (apps/control/api/downloads.py), tested at the office's door. The tenancy
sweep asks this route about shop A's photos as shop B's laptop. The photos are a few made-up bytes that start the way a
JPEG does, never a real photo. Fake data only: the repo is public (03 §10).
"""

import hashlib
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.control.models import Attachment, AttachmentKind, AttachmentType
from apps.control.services import expect_attachment, receive_attachment_file
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import (
    add_staff,
    block,
    change_person,
    confirm_pairing,
    mark_left,
    remove_worker_photo,
    set_pin,
    set_worker_photo,
    start_pairing,
    suspend,
)
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.sync.push import Sent, push
from apps.sync.selectors import staff_photo

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The cookie's name, written out here rather than imported: it is a promise to the laptop.
KEY_COOKIE = "device_key"
START = date(2026, 3, 2)

# Made-up photos: the first bytes every JPEG starts with, then words that are no picture.
FACE = b"\xff\xd8\xff\xe0" + b"Asha's face, made up " * 40
BETTER_FACE = b"\xff\xd8\xff\xe0" + b"a better face of Asha, made up " * 40


def address(photo_id: uuid.UUID) -> str:
    return f"/api/sync/v1/staff-photos/{photo_id}/"


def a_browser(key: str) -> APIClient:
    # A browser that holds this device's key in its cookie, as the laptop's does.
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    return client


def pair(manager: StaffMember, side: Side, name: str) -> tuple[Device, str]:
    # A laptop paired the way the app pairs one: it asks and keeps its key, and the manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        device = confirm_pairing(asked.request.code, name=name, home_side=side, by=manager)
    return device, asked.key


def hire(shop: Shop, full_name: str, nickname: str) -> StaffMember:
    user = User.objects.create_user(full_name=full_name)
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=nickname, started_on=START, by=None)


def with_a_pin(staff: StaffMember) -> StaffMember:
    with shop_context(staff.shop_id):
        return set_pin(staff, "2580", by=None)


def set_photo(
    staff: StaffMember, *, by: StaffMember, content: bytes = FACE, instead_of: uuid.UUID | None = None
) -> uuid.UUID:
    # The photo set as the office sets it (PPL-9).
    photo_id = uuid.uuid7()
    with shop_context(staff.shop_id):
        set_worker_photo(staff, photo_id=photo_id, instead_of=instead_of, content=content, by=by)
    return photo_id


def clock_photo_of(staff: StaffMember, device: Device) -> uuid.UUID:
    # Asha taps Ingia at the laptop, which takes her photo: the tap goes up with the photo's label, then its file, as
    # the app sends them (ATT-3, CTRL-6).
    photo_id, tapped = uuid.uuid7(), timezone.now()
    label = {
        "id": str(photo_id),
        "kind": "clock_photo",
        "content_type": "image/jpeg",
        "size": len(FACE),
        "sha256": hashlib.sha256(FACE).hexdigest(),
    }
    tap = Sent(
        id=uuid.uuid7(),
        type="clock",
        schema_version=2,
        device_seq=1,
        client_time=tapped,
        created_by=staff.pk,
        payload={"kind": "in", "last_server_time": tapped.isoformat(), "photo": label},
    )
    with shop_context(staff.shop_id):
        [answer] = push(
            device, [tap], received_at=tapped, sent_at=tapped, unsent_count=0, app_version="2026.11.2", outages=[]
        )
        assert answer.status == "accepted"
        assert receive_attachment_file(photo_id, content=FACE).kind == AttachmentKind.CLOCK_PHOTO
    return photo_id


@pytest.fixture
def baba(staff_a: StaffMember, give_role: GiveRole) -> StaffMember:
    give_role(staff_a, RoleTemplate.OWNER, None)
    return staff_a


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    # She logs in at the laptops, with a PIN, so they have a tile for her face to show on.
    return with_a_pin(hire(shop_a, "Asha Mfano", "Asha"))


@pytest.fixture
def laptop(baba: StaffMember, side_a: Side) -> tuple[Device, str]:
    return pair(baba, side_a, "Laptop ya Dawa")


def code_of(answer: Any) -> tuple[int, str]:
    return answer.status_code, answer.json()["code"]


def assert_not_found(answer: Any, client: APIClient) -> None:
    # The very answer an id no shop has gets: its status, its code and its words.
    control = client.get(address(uuid.uuid7()))
    assert code_of(control) == (404, "attachment.not_found")
    assert code_of(answer) == (404, "attachment.not_found")
    assert answer.content == control.content


def test_a_laptop_reads_the_photo_a_row_names(asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]) -> None:
    photo_id = set_photo(asha, by=baba)
    _device, key = laptop

    answer = a_browser(key).get(address(photo_id))

    assert answer.status_code == 200
    assert answer.getvalue() == FACE
    assert answer["Content-Type"] == "image/jpeg"
    # The laptop keeps its own copy, in its database, which it drops when the row stops naming the photo. A copy in the
    # browser's cache, or a proxy's on the way, is one nothing would ever drop.
    assert answer["Cache-Control"] == "private, no-store"
    assert answer["X-Content-Type-Options"] == "nosniff"


def test_a_suspended_persons_photo_is_read_too(
    shop_a: Shop, asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    # She has no tile while she is suspended, but she is on the laptop's list (X2), and back on the tiles the moment she
    # is brought back, maybe before the next sync could fetch her face.
    photo_id = set_photo(asha, by=baba)
    with shop_context(shop_a):
        suspend(asha, by=baba, reason="Likizo ya adhabu")
    _device, key = laptop

    assert a_browser(key).get(address(photo_id)).status_code == 200


def test_a_photo_a_newer_one_replaced_is_not_found(
    asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    # A laptop that pulled just before the change asks for the old one: not found, and its next pull names the new one.
    first = set_photo(asha, by=baba)
    better = set_photo(asha, by=baba, content=BETTER_FACE, instead_of=first)
    client = a_browser(laptop[1])

    assert_not_found(client.get(address(first)), client)
    assert client.get(address(better)).getvalue() == BETTER_FACE


def test_a_photo_taken_off_is_not_found(
    shop_a: Shop, asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    photo_id = set_photo(asha, by=baba)
    with shop_context(shop_a):
        remove_worker_photo(asha, photo_id=photo_id, reason="Hataki picha", by=baba)
    client = a_browser(laptop[1])

    assert_not_found(client.get(address(photo_id)), client)


def test_a_leavers_photo_is_not_found(
    shop_a: Shop, asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    # The photo stays on her old job in the office (parking lot 31), but a laptop holds only the people at work.
    photo_id = set_photo(asha, by=baba)
    with shop_context(shop_a):
        mark_left(asha, left_on=shop_today(shop_a), by=baba, reason="Amehamia mji mwingine")
    client = a_browser(laptop[1])

    assert_not_found(client.get(address(photo_id)), client)


def test_a_switched_off_persons_photo_is_not_found(
    asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    photo_id = set_photo(asha, by=baba)
    asha.user.is_active = False
    change_person(asha.user, changed=["is_active"])
    client = a_browser(laptop[1])

    assert_not_found(client.get(address(photo_id)), client)


def test_a_photo_of_someone_with_no_pin_is_not_found(
    shop_a: Shop, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    # The cook never logs in at a laptop: no PIN, so no tile, and her face would sit on every laptop shown to nobody
    # (Jack: A, PPL-14's review). It comes with her PIN, at the next sync.
    cook = hire(shop_a, "Zawadi Mfano", "Zawadi")
    photo_id = set_photo(cook, by=baba)
    client = a_browser(laptop[1])

    assert_not_found(client.get(address(photo_id)), client)

    with_a_pin(cook)
    assert client.get(address(photo_id)).getvalue() == FACE


def test_a_photo_no_row_names_is_not_found(asha: StaffMember, laptop: tuple[Device, str]) -> None:
    # A whole worker's photo, its file kept, pinned to Asha, but not the one her job shows: which one shows is the job's
    # to say (StaffMember.photo), never what a photo is pinned to.
    with shop_context(asha.shop_id):
        row = expect_attachment(
            id=uuid.uuid7(),
            kind=AttachmentKind.STAFF_PHOTO,
            subject=asha,
            content_type=AttachmentType.JPEG,
            size=len(FACE),
            sha256=hashlib.sha256(FACE).hexdigest(),
            by=asha,
        )
        receive_attachment_file(row.pk, content=FACE)
    client = a_browser(laptop[1])

    assert_not_found(client.get(address(row.pk)), client)


def test_a_clock_in_photo_is_never_handed_to_a_laptop(asha: StaffMember, laptop: tuple[Device, str]) -> None:
    # A clock-in photo is for whoever manages attendance (ATTACHMENT_KINDS), never for whoever stands at the laptop,
    # though a laptop took it and its file is kept. Nor one a job was made to name, by a bug no foreign key can refuse:
    # the kind is asked too.
    device, key = laptop
    photo_id = clock_photo_of(asha, device)
    client = a_browser(key)

    assert_not_found(client.get(address(photo_id)), client)
    with shop_context(asha.shop_id):
        StaffMember.objects.filter(pk=asha.pk).update(photo=photo_id)
    assert_not_found(client.get(address(photo_id)), client)
    # Nor one pinned to her job too: the kind is asked by itself, never only through whose photo it is.
    with shop_context(asha.shop_id):
        Attachment.objects.filter(pk=photo_id).update(subject_id=asha.pk)
    assert_not_found(client.get(address(photo_id)), client)


def test_a_photo_of_someone_else_is_never_handed_to_a_laptop(
    shop_a: Shop, asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    # A job made to name a coworker's photo, by a bug no foreign key can refuse: Juma's tile would wear the face of
    # Asha, who left. Not found, as a photo shows only on the very job it is pinned to.
    ashas = set_photo(asha, by=baba)
    juma = with_a_pin(hire(shop_a, "Juma Mfano", "Juma"))
    with shop_context(shop_a):
        mark_left(asha, left_on=shop_today(shop_a), by=baba, reason="Amehamia mji mwingine")
        StaffMember.objects.filter(pk=juma.pk).update(photo=ashas)
    client = a_browser(laptop[1])

    assert_not_found(client.get(address(ashas)), client)


def test_another_shops_photo_is_never_read_whatever_a_row_names(
    asha: StaffMember, baba: StaffMember, shop_b: Shop, staff_b: StaffMember, side_b: Side, give_role: GiveRole
) -> None:
    # The same bug, across shops: a job of shop B names shop A's photo. The link is followed by the database, past the
    # shop's guard, so the shop is asked too (T1): the row itself never leaves shop A, not only its file, which the
    # storage would refuse by its name. And the answer is the one an id no shop has gets.
    ours = set_photo(asha, by=baba)
    give_role(staff_b, RoleTemplate.OWNER, None)
    _device_b, key_b = pair(staff_b, side_b, "Laptop B")
    with_a_pin(staff_b)
    with shop_context(shop_b):
        StaffMember.objects.filter(pk=staff_b.pk).update(photo=ours)
        assert staff_photo(shop_b, ours) is None
    client = a_browser(key_b)

    assert_not_found(client.get(address(ours)), client)
    # Nor one pinned to that very job too: the shop is asked by itself, never only through whose photo it is.
    with shop_context(asha.shop_id):
        Attachment.objects.filter(pk=ours).update(subject_id=staff_b.pk)
    with shop_context(shop_b):
        assert staff_photo(shop_b, ours) is None
    assert_not_found(client.get(address(ours)), client)


def test_each_shops_laptop_reads_its_own_photo_of_one_person(
    asha: StaffMember,
    baba: StaffMember,
    laptop: tuple[Device, str],
    shop_b: Shop,
    staff_b: StaffMember,
    side_b: Side,
    give_role: GiveRole,
) -> None:
    # Asha works at two shops, with a photo at each, as a file belongs to one shop (02 §5). Each laptop reads its own
    # shop's, and the other's is an id it has never heard of.
    give_role(staff_b, RoleTemplate.OWNER, None)
    with shop_context(shop_b):
        at_b = with_a_pin(add_staff(shop=shop_b, user=asha.user, display_name="Asha", started_on=START, by=None))
    ours, theirs = set_photo(asha, by=baba), set_photo(at_b, by=staff_b, content=BETTER_FACE)
    here, there = a_browser(laptop[1]), a_browser(pair(staff_b, side_b, "Laptop B")[1])

    assert here.get(address(ours)).getvalue() == FACE
    assert there.get(address(theirs)).getvalue() == BETTER_FACE
    assert_not_found(here.get(address(theirs)), here)
    assert_not_found(there.get(address(ours)), there)


def test_a_photo_needs_a_paired_device(
    shop_a: Shop, asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]
) -> None:
    # A device's key alone opens the door: no key, a made-up one, or a person's own login reads nothing here. A blocked
    # laptop, a stolen one, reads nothing either, and learns why.
    photo_id = set_photo(asha, by=baba)
    phone = APIClient()
    phone.force_login(baba.user)
    for client in (APIClient(), a_browser("a" * 43), phone):
        assert code_of(client.get(address(photo_id))) == (401, "not_authenticated")
    device, key = laptop
    with shop_context(shop_a):
        block(device, by=baba, reason="Laptop imeibiwa")
    assert code_of(a_browser(key).get(address(photo_id))) == (401, "device.blocked")


def test_a_photo_is_only_read_here(asha: StaffMember, baba: StaffMember, laptop: tuple[Device, str]) -> None:
    # A laptop sets no worker's photo and takes none off: that is the office's, by someone who may (PPL-9).
    photo_id = set_photo(asha, by=baba)
    client = a_browser(laptop[1])

    for answer in (
        client.put(address(photo_id), data=BETTER_FACE, content_type="image/jpeg"),
        client.post(address(photo_id)),
        client.delete(address(photo_id)),
    ):
        assert answer.status_code == 405
    assert client.get(address(photo_id)).getvalue() == FACE
    with shop_context(asha.shop_id):
        assert Attachment.objects.get(pk=photo_id).file_state == "kept"
