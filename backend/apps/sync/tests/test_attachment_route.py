"""apps/sync/tests/test_attachment_route.py — the address a shop laptop sends a photo's file to (CTRL-3; 03 §5.13).

Asha clocked in at 07:55 with no internet. Her clock-in reached the server with her photo's label, and the row waits
(test_attachments.py); now the laptop sends the photo itself:

    PUT /api/sync/v1/attachments/<photo id>/   the body is the photo's bytes
    the file as its label says                 204: kept, and the same again answers 204, changing nothing
    another file, or one cut short             400 attachment.file_differs; nothing kept
    over 1 MB                                  400 attachment.too_big, refused before a byte of it is read
    not a JPEG or a WebP                       400 attachment.not_an_image
    an id this shop doesn't hold               404 attachment.not_found, as for an id no shop has

These test the route and the service behind it (receive_attachment_file, apps/control/services.py), as one: the key,
the CSRF token, each refusal, two copies at once, and that an answer holds nothing of another shop, which the tenancy
sweep checks too (DEVICE_ROUTES_WITHOUT_A_LOOK). The photos are a few made-up bytes that start the way a JPEG or a
WebP does, never a real photo. Fake data only: the repo is public (03 §10).
"""

import hashlib
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test.client import MULTIPART_CONTENT
from rest_framework.test import APIClient

from apps.control.models import LARGEST_FILE, Attachment, AttachmentKind, AttachmentType, EditEvent
from apps.control.services import expect_attachment, receive_attachment_file
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import block, confirm_pairing, start_pairing
from apps.shops.models import Shop, Side
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The address and the cookie's name, written out here rather than imported: they are a promise to the laptop.
DEVICE_ME = "/api/devices/v1/me/"
KEY_COOKIE = "device_key"

# Made-up photos: the first bytes every JPEG and every WebP starts with, then words that are no picture.
JPEG = b"\xff\xd8\xff\xe0" + b"Asha's clock-in, made up " * 40
WEBP = b"RIFF\x00\x01\x00\x00WEBPVP8 " + b"a made-up WebP " * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"not one of the two " * 40


def address(attachment_id: uuid.UUID) -> str:
    return f"/api/sync/v1/attachments/{attachment_id}/"


def a_browser(key: str, *, csrf: bool = False) -> APIClient:
    # A browser that holds this device's key in its cookie. `csrf`: check CSRF as a real browser's visit is checked.
    client = APIClient(enforce_csrf_checks=csrf)
    client.cookies[KEY_COOKIE] = key
    return client


def put(client: APIClient, attachment_id: uuid.UUID, content: bytes, **headers: Any) -> Any:
    # The file as the laptop sends it: its bytes as the whole body, with the type the laptop gave it.
    return client.put(address(attachment_id), data=content, content_type="image/jpeg", **headers)


def pair(manager: StaffMember, side: Side, name: str) -> tuple[Device, str]:
    # A laptop paired the way the app pairs one: it asks and keeps its key, and the manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        device = confirm_pairing(asked.request.code, name=name, home_side=side, by=manager)
    return device, asked.key


@pytest.fixture
def manager(staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def laptop(manager: StaffMember, side_a: Side) -> tuple[Device, str]:
    return pair(manager, side_a, "Laptop ya Dawa")


def waiting(staff: StaffMember, content: bytes = JPEG, kind: AttachmentType = AttachmentType.JPEG) -> Attachment:
    # The row a record brings for a photo of `staff`, with the label of `content`, as the laptop worked it out.
    with shop_context(staff.shop_id):
        return expect_attachment(
            id=uuid.uuid7(),
            kind=AttachmentKind.STAFF_PHOTO,
            subject=staff,
            content_type=kind,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            by=staff,
        )


def stored(attachment: Attachment) -> Attachment:
    # The row as the database holds it now, through its own shop.
    with shop_context(attachment.shop_id):
        return Attachment.objects.get(pk=attachment.pk)


def kept_bytes(attachment: Attachment) -> bytes:
    # The file the storage keeps for the row, read through its own shop (apps/core/storage.py).
    with shop_context(attachment.shop_id):
        row = Attachment.objects.get(pk=attachment.pk)
        with row.file.open("rb") as file:
            return bytes(file.read())


def code_of(answer: Any) -> tuple[int, str]:
    return answer.status_code, answer.json()["code"]


def test_file_kept_once(shop_a: Shop, staff_a: StaffMember, laptop: tuple[Device, str]) -> None:
    # The file matches its label, so it is kept, under its shop's id and its own (never Asha's name), and the row says
    # when it came.
    photo = waiting(staff_a)
    _device, key = laptop

    answer = put(a_browser(key), photo.pk, JPEG)

    assert (answer.status_code, answer.content) == (204, b"")
    row = stored(photo)
    assert row.file_state == "kept"
    assert row.file.name == f"{shop_a.pk}/{photo.pk}"
    assert row.received_at is not None
    assert kept_bytes(photo) == JPEG


def test_webp_kept(staff_a: StaffMember, laptop: tuple[Device, str]) -> None:
    # The laptop may shrink a photo into WebP instead of JPEG (03 §5.13): kept the same way.
    photo = waiting(staff_a, WEBP, AttachmentType.WEBP)

    assert put(a_browser(laptop[1]), photo.pk, WEBP).status_code == 204
    assert kept_bytes(photo) == WEBP


def test_same_file_twice_answers_done(staff_a: StaffMember, laptop: tuple[Device, str]) -> None:
    # The laptop's first answer was lost on a bad line, so it sends again: the same answer, and nothing changes, not
    # even the time the file came.
    photo = waiting(staff_a)
    client = a_browser(laptop[1])
    put(client, photo.pk, JPEG)
    came = stored(photo).received_at

    again = put(client, photo.pk, JPEG)

    assert again.status_code == 204
    assert stored(photo).received_at == came
    assert kept_bytes(photo) == JPEG


@pytest.mark.parametrize(
    ("sent", "label", "kind"),
    [
        # Another photo sent under this id, of the same size.
        (JPEG[:-1] + b"!", JPEG, AttachmentType.JPEG),
        # The photo cut short on the way.
        (JPEG[:100], JPEG, AttachmentType.JPEG),
        # The right bytes, but a label that called them a JPEG: kept, it would be served as the wrong type.
        (WEBP, WEBP, AttachmentType.JPEG),
    ],
    ids=["another-photo", "cut-short", "wrong-type"],
)
def test_file_that_differs_refused(
    staff_a: StaffMember, laptop: tuple[Device, str], sent: bytes, label: bytes, kind: AttachmentType
) -> None:
    photo = waiting(staff_a, label, kind)

    answer = put(a_browser(laptop[1]), photo.pk, sent)

    assert code_of(answer) == (400, "attachment.file_differs")
    assert stored(photo).file_state == "waiting"


def test_file_not_an_image_refused(staff_a: StaffMember, laptop: tuple[Device, str]) -> None:
    # A PNG, or any file that isn't one of the two photos a laptop makes, by its first bytes, whatever it is called.
    photo = waiting(staff_a)

    answer = put(a_browser(laptop[1]), photo.pk, PNG)

    assert code_of(answer) == (400, "attachment.not_an_image")
    assert stored(photo).file_state == "waiting"


def test_file_too_big_refused_unread(
    monkeypatch: pytest.MonkeyPatch, staff_a: StaffMember, laptop: tuple[Device, str]
) -> None:
    # A file over 1 MB is refused from the request's head, its length, before the file is read or the service asked: a
    # 50 MB upload never fills the server's memory.
    photo = waiting(staff_a)

    def never(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("The file was read.")

    monkeypatch.setattr("apps.sync.api.views.receive_attachment_file", never)

    answer = put(a_browser(laptop[1]), photo.pk, JPEG + b"x" * LARGEST_FILE)

    assert code_of(answer) == (400, "attachment.too_big")


def test_file_too_big_refused_by_the_service_too(staff_a: StaffMember) -> None:
    # A request that gives no length reaches the service, which checks the size again.
    photo = waiting(staff_a)
    with shop_context(staff_a.shop_id), pytest.raises(ValidationError) as refused:
        receive_attachment_file(photo.pk, content=JPEG + b"x" * LARGEST_FILE)

    assert refused.value.code == "attachment.too_big"


def test_file_before_its_record_not_found(laptop: tuple[Device, str]) -> None:
    # The laptop sent the photo before its clock-in reached the server: "not found", and the laptop tries again after
    # its next push (CTRL-6).
    answer = put(a_browser(laptop[1]), uuid.uuid7(), JPEG)

    assert code_of(answer) == (404, "attachment.not_found")


def test_another_shops_attachment_not_found(staff_b: StaffMember, laptop: tuple[Device, str]) -> None:
    # T1: shop A's laptop sends a file under shop B's photo's id, the right file even. The answer is exactly the one
    # for an id no shop has, and B's photo is untouched.
    theirs = waiting(staff_b)
    client = a_browser(laptop[1])

    answer = put(client, theirs.pk, JPEG)
    nobody = uuid.uuid7()
    control = put(client, nobody, JPEG)

    assert code_of(answer) == (404, "attachment.not_found")
    assert answer.content == control.content
    assert stored(theirs).file_state == "waiting"


def test_attachment_upload_answers_hold_nothing_of_another_shop(
    staff_a: StaffMember, staff_b: StaffMember, side_b: Side, give_role: GiveRole
) -> None:
    # The tenancy sweep sends this route only empty bodies, so it looks here for what a real upload answers. Shop B's
    # laptop sends shop A's photo, the right file under the right id: refused as an id no shop has, with not a word of
    # shop A's, and A's photo stays waiting for A's own laptop (03 §5.4).
    ours = waiting(staff_a)
    give_role(staff_b, RoleTemplate.MANAGER, None)
    _device_b, key_b = pair(staff_b, side_b, "Laptop B")

    answer = put(a_browser(key_b), ours.pk, JPEG)

    assert code_of(answer) == (404, "attachment.not_found")
    shown = answer.content.decode()
    for of_a in (str(ours.pk), str(staff_a.shop_id), str(staff_a.pk), ours.sha256, staff_a.display_name):
        assert of_a not in shown
    assert stored(ours).file_state == "waiting"


def test_upload_needs_a_paired_device(
    shop_a: Shop, manager: StaffMember, staff_a: StaffMember, laptop: tuple[Device, str]
) -> None:
    # A device's key alone opens the door: no key, a made-up one, or a person's own login keeps nothing. A blocked
    # laptop, a stolen one, keeps nothing either, and learns why.
    photo = waiting(staff_a)
    phone = APIClient()
    phone.force_login(manager.user)
    for client in (APIClient(), a_browser("a" * 43), phone):
        assert code_of(put(client, photo.pk, JPEG)) == (401, "not_authenticated")
    device, key = laptop
    with shop_context(shop_a):
        block(device, by=manager, reason="Laptop imeibiwa")
    assert code_of(put(a_browser(key), photo.pk, JPEG)) == (401, "device.blocked")
    assert stored(photo).file_state == "waiting"


def test_upload_needs_csrf(staff_a: StaffMember, laptop: tuple[Device, str]) -> None:
    # The laptop's cookie goes with every request to our address, even one another website makes it send: without the
    # token, that website could put its own picture where Asha's clock-in photo goes (ADR-0038).
    photo = waiting(staff_a)
    client = a_browser(laptop[1], csrf=True)
    assert code_of(put(client, photo.pk, JPEG)) == (403, "permission_denied")
    assert stored(photo).file_state == "waiting"
    # With the token, as the app sends it: from the cookie `me` hands out.
    client.get(DEVICE_ME)
    sent = put(client, photo.pk, JPEG, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert sent.status_code == 204


def test_upload_is_not_a_form(staff_a: StaffMember, laptop: tuple[Device, str]) -> None:
    # The body is the file's own bytes. A form around it (multipart, as a web page's file box sends) is other bytes
    # than the label's: refused, never unwrapped by a parser.
    photo = waiting(staff_a)

    answer = a_browser(laptop[1]).put(address(photo.pk), data={"file": JPEG}, content_type=MULTIPART_CONTENT)

    assert answer.status_code == 400
    assert stored(photo).file_state == "waiting"


def test_arrival_recorded_with_the_device(staff_a: StaffMember, laptop: tuple[Device, str]) -> None:
    # The file's arrival is an edit of the row, so the edit history keeps it, with the laptop that sent it and nobody
    # as the person: a device sent it, on its own (X3, ADR-0036).
    photo = waiting(staff_a)
    device, key = laptop

    put(a_browser(key), photo.pk, JPEG)

    with shop_context(staff_a.shop_id):
        [edit] = EditEvent.objects.filter(subject_type="attachment", subject_id=photo.pk)
    assert (edit.device_id, edit.created_by_id) == (device.pk, None)
    assert set(edit.after) == {"file", "received_at"}


@pytest.mark.django_db(transaction=True)
def test_two_uploads_at_once_take_turns(staff_a: StaffMember) -> None:
    # Two copies of one upload at the same moment: a tab and the service worker. The second waits for the row, which
    # the first holds until it commits, then finds the file kept and changes nothing. transaction=True, so the second
    # connection sees the first's rows at all.
    photo = waiting(staff_a)

    def second_copy() -> object:
        with shop_context(staff_a.shop_id):
            return receive_attachment_file(photo.pk, content=JPEG)

    with shop_context(staff_a.shop_id), transaction.atomic():
        receive_attachment_file(photo.pk, content=JPEG)
        second, ended = in_another_transaction(second_copy)
        wait_until_someone_waits_for_me()
    second.join(timeout=5)
    assert not second.is_alive(), "The second copy still waits after the first committed."
    (kept,) = ended
    assert isinstance(kept, Attachment)
    came = stored(photo).received_at
    assert kept.received_at == came
    assert kept_bytes(photo) == JPEG
