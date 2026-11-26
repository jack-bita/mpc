"""apps/control/tests/test_attachment_file_route.py — the address an office screen opens a photo at (CTRL-3; 03 §5.13).

    GET /api/v1/control/attachments/<photo id>/file/
    someone holding the kind's key, the file kept   200: the photo, its type as its label, never kept by the browser
    someone without it                              403 permission_denied, before anything about the photo is told
    the file not sent yet                           404 attachment.file_waiting
    the file removed (90 days after its pay run)    404 attachment.file_removed
    another shop's photo, or an id no shop has      404 not_found, alike

A worker's photo is opened by anyone working at the shop; a clock-in photo needs `attendance.manage` on the whole shop
(ATTACHMENT_KINDS). A clock-in photo's record, an attendance event, is ATT-3's to make, and `control` may not import
`staffpay` (ADR-0035), so the key's tests give the worker's photo a key for the length of each test. The people come
from backend/conftest.py, logged in as the office screens are. Fake data only: the repo is public (03 §10).
"""

import hashlib
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.core.files.storage import default_storage
from django.db.models import Model
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.control.models import (
    ATTACHMENT_KINDS,
    Attachment,
    AttachmentKind,
    AttachmentType,
    KindRule,
    attachment_file_name,
)
from apps.control.services import expect_attachment, receive_attachment_file, remove_attachment_file
from apps.core.models import StoredFile
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context

pytestmark = pytest.mark.django_db

GiveRole = Callable[[Any, RoleTemplate, Any], None]

# A made-up photo: the first bytes of a JPEG, then words that are no picture.
JPEG = b"\xff\xd8\xff\xe0" + b"Asha's face, made up " * 40


def address(attachment_id: uuid.UUID) -> str:
    return f"/api/v1/control/attachments/{attachment_id}/file/"


def client_for(staff: Any) -> APIClient:
    # The way the office screens call: logged in as this person, at their shop (backend/conftest.py).
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)
    return client


def photo(staff: Any, *, sent: bool = True) -> Attachment:
    # A worker's photo of `staff`, its row as its record brings it, and its file, unless `sent` is False.
    with shop_context(staff.shop_id):
        row = expect_attachment(
            id=uuid.uuid7(),
            kind=AttachmentKind.STAFF_PHOTO,
            subject=staff,
            content_type=AttachmentType.JPEG,
            size=len(JPEG),
            sha256=hashlib.sha256(JPEG).hexdigest(),
            by=staff,
        )
        if sent:
            receive_attachment_file(row.pk, content=JPEG)
    return row


@pytest.fixture
def staff_photo_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # For the length of a test, a worker's photo is opened as a clock-in photo is: with `attendance.manage`, on the
    # whole shop.
    monkeypatch.setitem(
        ATTACHMENT_KINDS, AttachmentKind.STAFF_PHOTO, KindRule("staff", frozenset({Permission.ATTENDANCE_MANAGE}))
    )


def code_of(answer: Any) -> tuple[int, str]:
    return answer.status_code, answer.json()["code"]


def test_file_opened_with_its_key(staff_a: Any, staff_client_a: APIClient) -> None:
    # The owner opens Asha's photo: the bytes as kept, as the label's type, and never kept by the browser or a cache on
    # the way, as it is a person's photo behind a key that can be taken away (03 §10).
    row = photo(staff_a)

    answer = staff_client_a.get(address(row.pk))

    assert answer.status_code == 200
    assert answer.getvalue() == JPEG
    assert answer["Content-Type"] == "image/jpeg"
    assert answer["Cache-Control"] == "private, no-store"
    assert answer["X-Content-Type-Options"] == "nosniff"


def test_staff_photo_opened_by_anyone_working_here(
    staff_a: Any, staff_a2: Any, side_a: Model, give_role: GiveRole
) -> None:
    # A worker's face already shows on every laptop's PIN tiles, so a loader on one side may see it too.
    give_role(staff_a2, RoleTemplate.WORKER, side_a)
    row = photo(staff_a)

    assert client_for(staff_a2).get(address(row.pk)).status_code == 200


@pytest.mark.usefixtures("staff_photo_needs_a_key")
def test_file_refused_without_its_key(staff_a: Any, staff_a2: Any, side_a: Model, give_role: GiveRole) -> None:
    # A kind behind a key: the loader holds none of it, so the photo is refused, before anything about it is told; the
    # owner holds every key, and opens it.
    give_role(staff_a2, RoleTemplate.WORKER, side_a)
    give_role(staff_a, RoleTemplate.OWNER, None)
    row = photo(staff_a)

    assert code_of(client_for(staff_a2).get(address(row.pk))) == (403, "permission_denied")
    assert client_for(staff_a).get(address(row.pk)).status_code == 200


@pytest.mark.usefixtures("staff_photo_needs_a_key")
def test_a_key_on_one_side_opens_no_whole_shop_photo(
    staff_a: Any, staff_a2: Any, side_a: Model, give_role: GiveRole
) -> None:
    # A manager of the Drugs side alone holds `attendance.manage` there, not on the whole shop, where a worker's
    # attendance belongs: refused (02 §5).
    give_role(staff_a2, RoleTemplate.MANAGER, side_a)
    row = photo(staff_a)

    assert code_of(client_for(staff_a2).get(address(row.pk))) == (403, "permission_denied")


@pytest.mark.usefixtures("staff_photo_needs_a_key")
def test_without_the_key_nothing_is_told_about_the_photo(
    staff_a: Any, staff_a2: Any, side_a: Model, give_role: GiveRole
) -> None:
    # The key is asked before the file's state: someone without it can't learn whether the photo has come, nor, from
    # the answer's words, what kind of photo it is.
    give_role(staff_a2, RoleTemplate.WORKER, side_a)
    row = photo(staff_a, sent=False)

    answer = client_for(staff_a2).get(address(row.pk))

    assert code_of(answer) == (403, "permission_denied")
    assert AttachmentKind.STAFF_PHOTO.value not in answer.content.decode()


def test_waiting_file_says_so(staff_a: Any, staff_client_a: APIClient) -> None:
    # Asha's clock-in came, her photo not yet: the laptop sends it when it can (CTRL-6).
    row = photo(staff_a, sent=False)

    assert code_of(staff_client_a.get(address(row.pk))) == (404, "attachment.file_waiting")


def test_removed_file_says_so(staff_a: Any, staff_client_a: APIClient) -> None:
    # Ninety days after its pay run, the photo was removed (ATT-7): the row says so, and the screen with it.
    row = photo(staff_a)
    with shop_context(staff_a.shop_id):
        remove_attachment_file(row, reason="Siku 90 baada ya mshahara")

    assert code_of(staff_client_a.get(address(row.pk))) == (404, "attachment.file_removed")


def test_photo_removed_while_it_is_opened_says_so(staff_a: Any, staff_client_a: APIClient) -> None:
    # The owner opens Asha's photo at the moment the nightly job removes it: the row was read as kept, but the job's
    # delete ran before the file was opened. Its file is taken away here behind the row's back, as that delete would.
    row = photo(staff_a)
    with shop_context(staff_a.shop_id):
        default_storage.delete(attachment_file_name(row, ""))

    assert code_of(staff_client_a.get(address(row.pk))) == (404, "attachment.file_removed")


def test_another_shops_attachment_not_found(staff_b: Any, staff_client_a: APIClient) -> None:
    # T1: shop B's photo, asked for by shop A's owner, answers exactly as an id no shop has.
    theirs = photo(staff_b)
    nobody = uuid.uuid7()

    answer = staff_client_a.get(address(theirs.pk))
    control = staff_client_a.get(address(nobody))

    assert code_of(answer) == (404, "not_found")
    assert answer.content.replace(str(theirs.pk).encode(), b"<id>") == control.content.replace(
        str(nobody).encode(), b"<id>"
    )


def test_who_sees_no_side_opens_nothing(staff_a: Any, staff_a2: Any) -> None:
    # A person who holds no key on any side sees no row of the whole shop (apps/core/api/base.py): not found.
    row = photo(staff_a)

    assert code_of(client_for(staff_a2).get(address(row.pk))) == (404, "not_found")


def test_kinds_are_opened_with_their_keys() -> None:
    # Written out in full, so a change to who may open a kind is a change to this test too (CTRL-3's card): a clock-in
    # photo with `attendance.manage` on the whole shop, a worker's face by anyone working at the shop, and a worker's
    # signature with the two keys of pay, never removed (WAGE-9).
    assert {
        AttachmentKind.CLOCK_PHOTO: KindRule("attendance_event", frozenset({Permission.ATTENDANCE_MANAGE})),
        AttachmentKind.STAFF_PHOTO: KindRule("staff", frozenset()),
        AttachmentKind.SIGNATURE: KindRule(
            "payslip_payment", frozenset({Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE}), removable=False
        ),
    } == ATTACHMENT_KINDS


def test_a_kind_behind_two_keys_needs_both(
    monkeypatch: pytest.MonkeyPatch, staff_a: Any, staff_a2: Any, give_role: GiveRole
) -> None:
    # A signature opens with both keys of pay, as the pay does (WAGE-9): one of them alone is refused. Shown with two
    # keys a manager holds one of, as `control` may not make a payment (ADR-0035): he holds `attendance.manage` on the
    # whole shop, not `pay.approve`, the owner's own (02 §5); the owner holds both.
    monkeypatch.setitem(
        ATTACHMENT_KINDS,
        AttachmentKind.STAFF_PHOTO,
        KindRule("staff", frozenset({Permission.ATTENDANCE_MANAGE, Permission.PAY_APPROVE})),
    )
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    give_role(staff_a, RoleTemplate.OWNER, None)
    row = photo(staff_a)

    assert code_of(client_for(staff_a2).get(address(row.pk))) == (403, "permission_denied")
    assert client_for(staff_a).get(address(row.pk)).status_code == 200


def test_file_served_from_the_demo_storage(settings: Settings, staff_a: Any, staff_client_a: APIClient) -> None:
    # The demo keeps its files in its database (apps/core/storage.py): sent there and opened from there, the same.
    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": "apps.core.storage.DatabaseStorage"}}
    row = photo(staff_a)

    answer = staff_client_a.get(address(row.pk))

    assert answer.status_code == 200
    assert answer.getvalue() == JPEG
    # From the database itself, not a folder: had the switch failed, the photo would have gone to the folder, and this
    # test would pass without the demo's storage ever being used.
    with shop_context(staff_a.shop_id):
        assert bytes(StoredFile.objects.get(name=attachment_file_name(row, "")).content) == JPEG
