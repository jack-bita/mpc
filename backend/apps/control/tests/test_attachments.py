"""apps/control/tests/test_attachments.py — tests for an attachment's row, waiting for its file (CTRL-3, 02 §13).

Asha's photo, as its record brings it to the server, before the file itself:

    id        kind         record        type        size     sha256      file   state
    0193…a1   staff_photo  Asha's job    image/jpeg  153,600  9f86d0…08   —      waiting

The file follows through the upload route (step 4 of CTRL-3) and must match the label. These tests check the label
and the row: who may pin what to which record, and what the database refuses whatever code writes it.

`control` may not import `shops` or `people` (ADR-0035), not even in its tests, so the shops, staff and devices come
from backend/conftest.py, typed by what they are to `control`: a shop's row, or an Actor. The worker's photo kind is
used, as a staff member is a fixture there; a clock-in photo's record, an attendance event, is ATT-3's. Fake data only:
the repo is public (03 §10).
"""

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Model
from django.utils import timezone

from apps.control.models import (
    ATTACHMENT_KINDS,
    LARGEST_FILE,
    Attachment,
    AttachmentKind,
    AttachmentType,
    attachment_file_name,
)
from apps.control.services import add_attachment, expect_attachment
from apps.core.links import LINK_TYPES
from apps.core.models import ShopScoped
from apps.core.tenancy import Actor, ShopMismatch, shop_context

pytestmark = pytest.mark.django_db

# The label of a made-up photo: its fingerprint is the real SHA-256 of these bytes, as the laptop would work it out.
PHOTO = b"\xff\xd8\xff not a real photo"
PHOTO_SHA256 = hashlib.sha256(PHOTO).hexdigest()


@dataclass(frozen=True)
class DeviceAlone:
    # An Actor that is no person: a paired device acting by itself (03 §5.4), so its staff_id is None.
    shop_id: uuid.UUID
    staff_id: uuid.UUID | None = None


def expect(subject: ShopScoped, by: Actor, **changes: Any) -> Attachment:
    # A worker's photo of `subject`, as an office screen would add it, with any part of the label changed.
    label: dict[str, Any] = {
        "id": uuid.uuid7(),
        "kind": AttachmentKind.STAFF_PHOTO,
        "content_type": AttachmentType.JPEG,
        "size": len(PHOTO),
        "sha256": PHOTO_SHA256,
    }
    return expect_attachment(subject=subject, by=by, **{**label, **changes})


def test_expect_attachment_writes_a_waiting_row(shop_a: Model, staff_a: Any, device_a: ShopScoped) -> None:
    # The photo was taken on the Dawa laptop, so the row names it (X3), and the id is the laptop's own (ADR-0007).
    photo_id = uuid.uuid7()
    with shop_context(shop_a):
        expect(staff_a, staff_a, id=photo_id, device=device_a)
        stored = Attachment.objects.get(pk=photo_id)
        # The link loads its record back, through the shop guard.
        assert stored.subject.pk == staff_a.pk

    assert (stored.shop_id, stored.kind) == (shop_a.pk, AttachmentKind.STAFF_PHOTO)
    # The record it is pinned to: its table's code and its id.
    assert (stored.subject_type, stored.subject_id) == ("staff", staff_a.pk)
    assert (stored.content_type, stored.size, stored.sha256) == (AttachmentType.JPEG, len(PHOTO), PHOTO_SHA256)
    assert (stored.created_by_id, stored.device_id) == (staff_a.pk, device_a.pk)
    # Waiting: no file yet, nothing received, nothing removed.
    assert stored.file_state == "waiting"
    assert (stored.file.name, stored.received_at, stored.file_removed_at) == ("", None, None)


def test_office_attachment_names_no_device(shop_a: Model, staff_a: Any) -> None:
    # A photo the owner adds on an office screen, from his own phone, comes from no shop laptop (PPL-9).
    with shop_context(shop_a):
        stored = expect(staff_a, staff_a)

    assert stored.device_id is None


def test_unknown_kind_refused(shop_a: Model, staff_a: Any) -> None:
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            expect(staff_a, staff_a, kind="selfie")

        assert refused.value.error_dict["kind"][0].code == "attachment.kind_unknown"
        assert not Attachment.objects.exists()


def test_subject_of_another_table_refused(shop_a: Model, staff_a: Any, side_a: ShopScoped) -> None:
    # Each kind is pinned to one table's records: a worker's photo on a side, or a clock-in photo on a worker, would be
    # opened with the wrong key. A bug in the calling code, so a server error, before anything is written.
    with shop_context(shop_a):
        with pytest.raises(ValueError, match="pinned to a 'staff' record"):
            expect(side_a, staff_a)
        with pytest.raises(ValueError, match="pinned to a 'attendance_event' record"):
            expect(staff_a, staff_a, kind=AttachmentKind.CLOCK_PHOTO)

        assert not Attachment.objects.exists()


def test_subject_of_another_shop_refused(
    shop_a: Model, shop_b: Model, staff_a: Any, staff_b: Any, device_a: ShopScoped
) -> None:
    # T1, three ways: a record of another shop than the one open, a person of another shop, a laptop of another shop.
    with shop_context(shop_a):
        with pytest.raises(ShopMismatch):
            expect(staff_b, staff_a)
        with pytest.raises(ShopMismatch):
            expect(staff_a, staff_b)
    with shop_context(shop_b):
        with pytest.raises(ShopMismatch):
            expect(staff_b, staff_b, device=device_a)
        assert not Attachment.objects.exists()


def test_record_never_saved_refused(shop_a: Model, staff_a: Any, side_a: ShopScoped) -> None:
    # A generic link has no foreign key, so the database can't check it: a row pinned to a record that was never saved
    # would point at nothing. A copy of Asha's job, never saved, stands for one.
    unsaved = type(staff_a)(shop_id=shop_a.pk, user_id=staff_a.user_id, display_name="Copy")
    with shop_context(shop_a), pytest.raises(ValueError, match="never saved"):
        expect(unsaved, staff_a)


def test_an_attachment_is_added_by_a_person(shop_a: Model, staff_a: Any) -> None:
    # `created_by` is kept for good, so a row with nobody in it would stay nameless.
    with shop_context(shop_a), pytest.raises(ValueError, match="no person"):
        expect(staff_a, DeviceAlone(shop_id=shop_a.pk))


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"content_type": "image/png"}, "attachment.not_an_image"),
        ({"size": 0}, "attachment.empty"),
        ({"size": LARGEST_FILE + 1}, "attachment.too_big"),
        ({"sha256": PHOTO_SHA256.upper()}, "attachment.sha256_invalid"),
        ({"sha256": PHOTO_SHA256[:40]}, "attachment.sha256_invalid"),
    ],
    ids=["png", "empty", "too-big", "upper-case-sha256", "short-sha256"],
)
def test_a_label_that_breaks_a_rule_refused(shop_a: Model, staff_a: Any, changes: dict[str, Any], code: str) -> None:
    # The database's rules, checked first by full_clean, so each comes back as its code, and nothing is written.
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            expect(staff_a, staff_a, **changes)

        codes = [error.code for errors in refused.value.error_dict.values() for error in errors]
        assert code in codes
        assert not Attachment.objects.exists()


def test_largest_file_allowed(shop_a: Model, staff_a: Any) -> None:
    # 1 MB itself is allowed; one byte more is not (above).
    with shop_context(shop_a):
        assert expect(staff_a, staff_a, size=LARGEST_FILE).size == LARGEST_FILE


def test_database_refuses_to_delete_an_attachment(shop_a: Model, staff_a: Any) -> None:
    # Rule 7: a photo is removed, its row kept with who, when and why. Nothing links to an attachment, so PROTECT can't
    # stop a delete: the table's own trigger does, whichever way it is sent.
    with shop_context(shop_a):
        row = expect(staff_a, staff_a)
        with pytest.raises(IntegrityError, match="never deleted"), transaction.atomic():
            row.delete()
        with pytest.raises(IntegrityError, match="never deleted"), transaction.atomic():
            Attachment.objects.filter(pk=row.pk).delete()

        assert Attachment.objects.filter(pk=row.pk).exists()


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        # A file with no time it arrived.
        ({"file": "x/y"}, "control_attachment_file_once_received"),
        # Arrived, but no file and no removal: a kept photo that lost its file.
        ({"received_at": timezone.now()}, "control_attachment_file_once_received"),
        # Removed with no reason (rule 7).
        ({"file_removed_at": timezone.now()}, "control_attachment_removal_says_why"),
        # A reason with no removal.
        ({"file_removed_reason": "Siku 90 zimepita"}, "control_attachment_removal_says_why"),
    ],
    ids=["file-not-received", "received-no-file", "removed-no-reason", "reason-not-removed"],
)
def test_database_refuses_a_file_between_states(
    shop_a: Model, staff_a: Any, changes: dict[str, Any], rule: str
) -> None:
    # The file is waiting, kept or removed, and nothing between: the database holds it even against code that skips the
    # services and full_clean, as a bulk update() does.
    with shop_context(shop_a):
        row = expect(staff_a, staff_a)
        with pytest.raises(IntegrityError, match=rule), transaction.atomic():
            Attachment.objects.filter(pk=row.pk).update(**changes)


def test_every_kind_has_its_rule() -> None:
    # A kind with no rule couldn't be checked or opened; a rule's table with no type code couldn't be linked to.
    assert set(ATTACHMENT_KINDS) == set(AttachmentKind)
    for rule in ATTACHMENT_KINDS.values():
        assert rule.subject_type in LINK_TYPES


def test_file_named_by_its_shop_and_its_own_id(shop_a: Model, staff_a: Any) -> None:
    # Never the name the laptop gave the file, which may hold a person's name: a path is no place for personal data
    # (03 §10). The shop first, so the storage keeps it in its shop (apps/core/storage.py).
    with shop_context(shop_a):
        row = expect(staff_a, staff_a)

    assert attachment_file_name(row, "IMG_0001 Asha.jpg") == f"{shop_a.pk}/{row.pk}"


def test_add_attachment_keeps_the_row_and_its_file(shop_a: Model, staff_a: Any) -> None:
    # A photo that reaches the server whole, as an office screen sends it (PPL-9): one call, and its label is the
    # server's own, worked out from the bytes.
    photo_id = uuid.uuid7()
    with shop_context(shop_a):
        add_attachment(id=photo_id, kind=AttachmentKind.STAFF_PHOTO, subject=staff_a, content=PHOTO, by=staff_a)
        stored = Attachment.objects.get(pk=photo_id)
        assert stored.file.read() == PHOTO

    assert stored.file_state == "kept"
    assert (stored.content_type, stored.size, stored.sha256) == (AttachmentType.JPEG, len(PHOTO), PHOTO_SHA256)
    assert (stored.subject_type, stored.subject_id) == ("staff", staff_a.pk)
    assert (stored.created_by_id, stored.device_id) == (staff_a.pk, None)


def test_add_attachment_knows_a_webp(shop_a: Model, staff_a: Any) -> None:
    webp = b"RIFF\x10\x00\x00\x00WEBP" + b"a made-up photo"
    with shop_context(shop_a):
        stored = add_attachment(
            id=uuid.uuid7(), kind=AttachmentKind.STAFF_PHOTO, subject=staff_a, content=webp, by=staff_a
        )

    assert stored.content_type == AttachmentType.WEBP


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (PHOTO + b"x" * LARGEST_FILE, "attachment.too_big"),
        (b"%PDF-1.7 not a photo", "attachment.not_an_image"),
        (b"", "attachment.not_an_image"),
    ],
    ids=["too-big", "not-an-image", "empty"],
)
def test_add_attachment_refuses_the_file_before_its_row(shop_a: Model, staff_a: Any, content: bytes, code: str) -> None:
    # About the whole file, as the laptop's upload refuses it, never filed under a label's field the caller never sent.
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            add_attachment(
                id=uuid.uuid7(), kind=AttachmentKind.STAFF_PHOTO, subject=staff_a, content=content, by=staff_a
            )

        assert refused.value.code == code
        assert not Attachment.objects.exists()
