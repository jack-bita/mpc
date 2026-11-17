"""apps/control/tests/test_remove_attachment_file.py — the hook for retention rules: a photo's file taken away for good,
its row kept (CTRL-3; 03 §5.13, rule 7).

Ninety days after March's pay run is approved, Asha's clock-in photo from 2 March must be gone (ATT-7):

    before    file 0193…/0193…a1   received 2 Mar 07:55                                   kept
    after     file —               received 2 Mar 07:55   removed 30 Jun, by the system,   removed
                                                          "Siku 90 baada ya mshahara"

The row first, the file only once that change is committed: the tests run the after-commit step themselves
(django_capture_on_commit_callbacks), as a test's transaction never commits. A clock-in photo's record is ATT-3's, so a
worker's photo stands in: the rule is the same for every kind. Fake data only: the repo is public (03 §10).
"""

import hashlib
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.control.models import Attachment, AttachmentKind, AttachmentType, EditEvent, attachment_file_name
from apps.control.services import expect_attachment, receive_attachment_file, remove_attachment_file
from apps.core.storage import FolderStorage
from apps.core.tenancy import ShopMismatch, shop_context, system_context

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class DeviceAlone:
    # An Actor that is no person: a paired device acting by itself (03 §5.4), so its staff_id is None.
    shop_id: uuid.UUID
    staff_id: uuid.UUID | None = None


# pytest-django's fixture: runs the after-commit steps a block registered, as a real commit would.
CommitSteps = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]

JPEG = b"\xff\xd8\xff\xe0" + b"Asha at 07:55, made up " * 40
REASON = "Siku 90 baada ya mshahara"


def photo(staff: Any, *, sent: bool = True) -> Attachment:
    # A worker's photo of `staff`: its row, and its file unless `sent` is False.
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
            row = receive_attachment_file(row.pk, content=JPEG)
    return row


def file_exists(row: Attachment, name: str | None) -> bool:
    # Whether the storage still holds a file of `row`'s shop by this name. Never asked of an empty name, which no file
    # has: "gone" would then pass for a photo that never had a file at all.
    assert name
    with shop_context(row.shop_id):
        return default_storage.exists(name)


def test_remove_file_keeps_the_row(staff_a: Any, django_capture_on_commit_callbacks: CommitSteps) -> None:
    # The nightly job, as the system: the file is gone from the storage, and the row says when it came, when it went,
    # and why.
    row = photo(staff_a)
    name = row.file.name
    with shop_context(staff_a.shop_id), django_capture_on_commit_callbacks(execute=True):
        removed = remove_attachment_file(row, reason=REASON)

    assert removed.file_state == "removed"
    assert (removed.file.name, removed.file_removed_reason, removed.file_removed_by_id) == ("", REASON, None)
    assert removed.received_at == row.received_at
    assert removed.file_removed_at is not None
    assert not file_exists(row, name)


def test_a_person_removes_with_their_name(staff_a: Any, django_capture_on_commit_callbacks: CommitSteps) -> None:
    row = photo(staff_a)
    with shop_context(staff_a.shop_id), django_capture_on_commit_callbacks(execute=True):
        removed = remove_attachment_file(row, reason="Picha ya mtu mwingine", by=staff_a)

    assert removed.file_removed_by_id == staff_a.pk


def test_removal_needs_a_reason(staff_a: Any) -> None:
    # Rule 7: always why. Spaces alone say nothing, and are refused too; the photo stays.
    row = photo(staff_a)
    with shop_context(staff_a.shop_id):
        with pytest.raises(ValidationError) as refused:
            remove_attachment_file(row, reason="   ")

        assert refused.value.error_dict["file_removed_reason"][0].code == "attachment.reason_required"
        assert Attachment.objects.get(pk=row.pk).file_state == "kept"
    assert file_exists(row, row.file.name)


def test_file_stays_until_the_removal_is_committed(
    staff_a: Any, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    # The removal's transaction rolls back, as it would if a later step of the same job failed: the row is "kept" again,
    # so its file must still be there. The delete waits for a commit that never comes.
    row = photo(staff_a)
    with shop_context(staff_a.shop_id), django_capture_on_commit_callbacks(execute=True) as steps:
        with pytest.raises(RuntimeError), transaction.atomic():
            remove_attachment_file(row, reason=REASON)
            raise RuntimeError("a later step failed")

        assert Attachment.objects.get(pk=row.pk).file_state == "kept"
    assert steps == []
    assert file_exists(row, row.file.name)


def test_removing_twice_changes_nothing(staff_a: Any, django_capture_on_commit_callbacks: CommitSteps) -> None:
    # A nightly job may run twice (03 §5.11): the second finds the file removed, and keeps the first's who, when, why.
    row = photo(staff_a)
    with shop_context(staff_a.shop_id), django_capture_on_commit_callbacks(execute=True):
        first = remove_attachment_file(row, reason=REASON)
        again = remove_attachment_file(row, reason="Tena", by=staff_a)

    assert (again.file_removed_at, again.file_removed_reason, again.file_removed_by_id) == (
        first.file_removed_at,
        REASON,
        None,
    )


@pytest.fixture
def failing_delete(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    # The names the storage fails to delete, as a full disk or a wrong permission would; every other delete works. A
    # test adds a name to make its delete fail, and takes it out once the disk is fixed.
    failing: set[str] = set()
    delete = FolderStorage.delete

    def maybe_fail(storage: FolderStorage, name: str) -> None:
        if name in failing:
            raise PermissionError(f"cannot delete {name}")
        delete(storage, name)

    monkeypatch.setattr(FolderStorage, "delete", maybe_fail)
    return failing


@pytest.mark.django_db(transaction=True)
def test_a_failed_delete_stops_no_other(
    staff_a: Any, failing_delete: set[str], caplog: pytest.LogCaptureFixture
) -> None:
    # ATT-7 removes two photos in one transaction, and the first delete fails: the second still runs, and the failure is
    # logged, not raised at the job after its rows are committed. transaction=True: a real commit, so Django itself
    # runs the steps after it, as on the server.
    first, second = photo(staff_a), photo(staff_a)
    failing_delete.add(str(first.file.name))
    with shop_context(staff_a.shop_id), transaction.atomic():
        remove_attachment_file(first, reason=REASON)
        remove_attachment_file(second, reason=REASON)

    assert file_exists(first, first.file.name)
    assert not file_exists(second, second.file.name)
    assert "cannot delete" in caplog.text
    with shop_context(staff_a.shop_id):
        assert {row.file_state for row in Attachment.objects.all()} == {"removed"}


def test_a_second_run_deletes_what_a_failed_delete_left(
    staff_a: Any, failing_delete: set[str], django_capture_on_commit_callbacks: CommitSteps
) -> None:
    # The night's delete failed, so the photo stayed on disk though its row says removed. The next night's run finds the
    # row removed, keeps its first who, when and why, and deletes the file again.
    row = photo(staff_a)
    name = str(row.file.name)
    failing_delete.add(name)
    with shop_context(staff_a.shop_id), django_capture_on_commit_callbacks(execute=True):
        first = remove_attachment_file(row, reason=REASON)
    assert file_exists(row, name)

    failing_delete.discard(name)  # the disk is fixed
    with shop_context(staff_a.shop_id), django_capture_on_commit_callbacks(execute=True):
        again = remove_attachment_file(row, reason="Tena")

    assert not file_exists(row, name)
    assert (again.file_removed_at, again.file_removed_reason) == (first.file_removed_at, REASON)


def test_removal_deletes_a_file_an_undone_upload_left(
    staff_a: Any, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    # An upload wrote the file, then its row's change was undone (CTRL-3's "file first, then the row"): the row still
    # waits, and a file sits under its name. Removing the photo deletes that file too, by the photo's own name.
    row = photo(staff_a, sent=False)
    name = attachment_file_name(row, "")
    with shop_context(staff_a.shop_id):
        default_storage.save(name, ContentFile(JPEG))
    with shop_context(staff_a.shop_id), django_capture_on_commit_callbacks(execute=True):
        remove_attachment_file(row, reason=REASON)

    assert not file_exists(row, name)


def test_a_photo_that_never_came_can_be_removed(staff_a: Any) -> None:
    # Its laptop was lost before it could send the photo: the row is closed all the same, so a late upload is dropped.
    row = photo(staff_a, sent=False)
    with shop_context(staff_a.shop_id):
        removed = remove_attachment_file(row, reason=REASON)

    assert removed.file_state == "removed"
    assert removed.received_at is None


def test_a_removed_file_is_never_kept_again(staff_a: Any) -> None:
    # The laptop sends the photo after it was removed: nothing is kept, and the laptop is told it's done.
    row = photo(staff_a, sent=False)
    with shop_context(staff_a.shop_id):
        remove_attachment_file(row, reason=REASON)
        again = receive_attachment_file(row.pk, content=JPEG)

    assert (again.file_state, again.file.name) == ("removed", "")


def test_a_system_job_removes_any_shops_file(staff_a: Any, django_capture_on_commit_callbacks: CommitSteps) -> None:
    # ATT-7's nightly job works shop by shop as the system (system_context): the delete opens the file's own shop.
    row = photo(staff_a)
    name = row.file.name
    with system_context(), django_capture_on_commit_callbacks(execute=True):
        remove_attachment_file(row, reason=REASON)

    assert not file_exists(row, name)


def test_a_device_alone_cannot_remove(staff_a: Any) -> None:
    # A laptop acting by itself is no person: the row would keep a remover with no name for good. The system acts as
    # None instead, and a person as themselves.
    row = photo(staff_a)
    with shop_context(staff_a.shop_id), pytest.raises(ValueError, match="no person"):
        remove_attachment_file(row, reason=REASON, by=DeviceAlone(shop_id=staff_a.shop_id))


def test_another_shops_person_cannot_remove(staff_a: Any, staff_b: Any) -> None:
    # T1: shop B's manager can't remove shop A's photo, even inside A's visit.
    row = photo(staff_a)
    with shop_context(staff_a.shop_id), pytest.raises(ShopMismatch):
        remove_attachment_file(row, reason=REASON, by=staff_b)


def test_removal_recorded_in_the_edit_history(staff_a: Any) -> None:
    # The removal is an edit of the row, so the history keeps it beside the row's own columns (ADR-0036).
    row = photo(staff_a)
    with shop_context(staff_a.shop_id):
        remove_attachment_file(row, reason=REASON, by=staff_a)
        edits = list(EditEvent.objects.filter(subject_type="attachment", subject_id=row.pk).order_by("created_at"))

    removal = edits[-1]
    assert removal.after["file_removed_reason"] == REASON
    assert removal.after["file"] in ("", None)
    assert removal.created_by_id == staff_a.pk
