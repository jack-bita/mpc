"""apps/people/tests/test_worker_photo.py — a worker's photo (PPL-9, 02 §5).

The job at one shop names the photo it shows now (`StaffMember.photo`), an attachment of kind `staff_photo` (CTRL-3).
Asha's row, as her photo is set, changed, and taken off:

    photo      what happened
    (none)     added by Meneja: her tile shows her full name
    0193…a1    Meneja took her photo
    0193…b2    Mzee chose a better one: the first one's file is gone, its row stays
    (none)     taken off, with a reason

Only which photo is shown lives on the job: the file, its label, who added it and who removed it are the attachment's
own (apps/control/models.py), so each fact lives once. Who may is test_who_changes_a_worker.py's; here the owner acts.
Each change also names the job in the shop's change log, so the laptops, whose PIN tiles show the face, hear of it
(PPL-14).

A file is deleted once its row's change is committed, so the tests run the after-commit step themselves
(django_capture_on_commit_callbacks), as a test's transaction never commits. Fake data only: the repo is public (03
§10).
"""

import hashlib
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date
from typing import Any, Literal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from pytest_django import Settings

from apps.control.models import (
    LARGEST_FILE,
    Attachment,
    AttachmentKind,
    AttachmentType,
    AuditEvent,
    EditEvent,
    attachment_file_name,
)
from apps.control.services import expect_attachment
from apps.core.acting import acting_as
from apps.core.editing import VersionConflict
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, add_worker, remove_worker_photo, set_worker_photo
from apps.shops.models import Shop, Side
from tests.change_log import lines_written

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]
# pytest-django's fixture: runs the after-commit steps a block registered, as a real commit would.
CommitSteps = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]

# A date in the past: a first day far ahead would read as a typing mistake.
START = date(2026, 3, 2)
# The first bytes every JPEG starts with, and some of our own: the server knows a photo by its first bytes (CTRL-3).
FACE = b"\xff\xd8\xff" + b"a made-up photo of Asha"
BETTER_FACE = b"\xff\xd8\xff" + b"a better made-up photo of Asha"
PNG = b"\x89PNG\r\n\x1a\n" + b"a picture of another kind"


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    user = User.objects.create_user(full_name="Asha Demo")
    with shop_context(shop_a):
        return add_staff(shop=shop_a, user=user, display_name="Asha", started_on=START, by=None)


@pytest.fixture
def baba(staff_a: StaffMember, give_role: GiveRole) -> StaffMember:
    give_role(staff_a, RoleTemplate.OWNER, None)
    return staff_a


@pytest.fixture
def mama(staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    # A second owner, for a photo one of them adds and the other changes.
    give_role(staff_a2, RoleTemplate.OWNER, None)
    return staff_a2


def a_photo_of(staff: StaffMember, *, by: StaffMember, kind: AttachmentKind = AttachmentKind.STAFF_PHOTO) -> Attachment:
    # A photo's row alone, its file still to come, as a record would bring it: never through the service under test.
    with shop_context(staff.shop_id):
        return expect_attachment(
            id=uuid.uuid7(),
            kind=kind,
            subject=staff,
            content_type=AttachmentType.JPEG,
            size=len(FACE),
            sha256=hashlib.sha256(FACE).hexdigest(),
            by=by,
        )


def set_photo(
    staff: StaffMember,
    *,
    by: StaffMember,
    content: bytes = FACE,
    photo_id: uuid.UUID | None = None,
    instead_of: uuid.UUID | None | Literal["now"] = "now",
) -> uuid.UUID:
    # The photo set as the office's route sets it, with the id the phone made, and the photo its page showed: the one
    # that shows now, as on a page just read, unless a test says otherwise.
    photo_id = photo_id or uuid.uuid7()
    seen = photo_of(staff) if instead_of == "now" else instead_of
    with shop_context(staff.shop_id):
        set_worker_photo(staff, photo_id=photo_id, instead_of=seen, content=content, by=by)
    return photo_id


def photo_of(staff: StaffMember) -> uuid.UUID | None:
    # Which photo the job shows, read again.
    with shop_context(staff.shop_id):
        return StaffMember.objects.get(pk=staff.pk).photo_id


def row_of(staff: StaffMember, photo_id: uuid.UUID) -> Attachment:
    with shop_context(staff.shop_id):
        return Attachment.objects.get(pk=photo_id)


def stored_bytes(row: Attachment) -> bytes | None:
    # The photo's file as the storage holds it, by its own fixed name; None once it is gone.
    name = attachment_file_name(row, "")
    with shop_context(row.shop_id):
        if not default_storage.exists(name):
            return None
        with default_storage.open(name) as file:
            return bytes(file.read())


def code_of(refused: pytest.ExceptionInfo[ValidationError]) -> str:
    # A refusal's one code, whether it is about the whole photo or filed under a field.
    [problem] = refused.value.error_list if hasattr(refused.value, "error_list") else refused.value.error_dict["id"]
    return str(problem.code)


def test_a_new_worker_has_no_photo(asha: StaffMember) -> None:
    # 02 §5: the photo is optional, so nobody is stopped from working for want of one.
    assert asha.photo_id is None


def test_a_photo_change_is_kept_in_the_edit_history(shop_a: Shop, asha: StaffMember, staff_a: StaffMember) -> None:
    # The photo has no audit line of its own (PPL-9's card): the edit history alone says who changed the face on every
    # laptop's tile, so the new column must be one PostgreSQL's trigger copies (ADR-0036).
    photo = a_photo_of(asha, by=staff_a)
    with shop_context(shop_a), acting_as(staff_a):
        asha.photo = photo
        asha.save(update_fields=["photo"])
        edits = list(EditEvent.objects.filter(subject_type="staff", subject_id=asha.pk))

    assert [(edit.created_by_id, edit.before, edit.after) for edit in edits] == [
        (staff_a.pk, {"photo_id": None}, {"photo_id": str(photo.pk)})
    ]


def test_the_first_photo_shows_on_the_job(asha: StaffMember, baba: StaffMember) -> None:
    photo_id = set_photo(asha, by=baba)

    assert photo_of(asha) == photo_id
    row = row_of(asha, photo_id)
    # Pinned to this very job, added by whoever set it, on an office screen: no laptop of the shop took it (X3).
    assert (row.kind, row.subject_type, row.subject_id) == (AttachmentKind.STAFF_PHOTO, "staff", asha.pk)
    assert (row.created_by_id, row.device_id) == (baba.pk, None)
    # The label is the server's own, worked out from the bytes that came, so no page can say one thing and send another.
    assert (row.content_type, row.size, row.sha256) == (
        AttachmentType.JPEG,
        len(FACE),
        hashlib.sha256(FACE).hexdigest(),
    )
    assert row.file_state == "kept"
    assert stored_bytes(row) == FACE


def test_a_new_photo_takes_the_old_ones_place(
    asha: StaffMember, baba: StaffMember, mama: StaffMember, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    # Two people, so that a row that named one of them for both would show.
    first = set_photo(asha, by=mama)
    with django_capture_on_commit_callbacks(execute=True):
        second = set_photo(asha, by=baba, content=BETTER_FACE)

    assert photo_of(asha) == second
    new = row_of(asha, second)
    assert stored_bytes(new) == BETTER_FACE
    assert (new.created_by_id, new.file_removed_by_id) == (baba.pk, None)
    # The old one's file is gone, as personal data is kept only as long as it is needed (03 §10); its row stays (rule
    # 7), with who and when, and why as a code: the system has no words of its own (ADR-0040).
    old = row_of(asha, first)
    assert old.file_state == "removed"
    assert (old.created_by_id, old.file_removed_by_id) == (mama.pk, baba.pk)
    assert old.file_removed_reason == "staff.photo_replaced"
    assert old.file_removed_at is not None
    assert stored_bytes(old) is None


def test_the_same_photo_sent_twice_is_one_photo(
    asha: StaffMember, baba: StaffMember, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    # Meneja's phone lost the answer on the way, and sends the same photo again with the same id (ADR-0007).
    photo_id = set_photo(asha, by=baba)
    with django_capture_on_commit_callbacks(execute=True):
        set_photo(asha, by=baba, photo_id=photo_id, instead_of=None)

    assert photo_of(asha) == photo_id
    with shop_context(asha.shop_id):
        [row] = Attachment.objects.all()
    # Still kept: the photo never takes its own place, which would delete its own file.
    assert row.file_state == "kept"
    assert stored_bytes(row) == FACE


def test_an_old_photo_sent_again_never_comes_back(
    asha: StaffMember, baba: StaffMember, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    # The first photo's send, stuck on a slow network, arrives a second time after Mzee chose a better one.
    first = set_photo(asha, by=baba)
    with django_capture_on_commit_callbacks(execute=True):
        second = set_photo(asha, by=baba, content=BETTER_FACE)
        set_photo(asha, by=baba, photo_id=first, instead_of=None)

    assert photo_of(asha) == second
    assert row_of(asha, first).file_state == "removed"
    assert stored_bytes(row_of(asha, first)) is None
    assert stored_bytes(row_of(asha, second)) == BETTER_FACE


@pytest.mark.parametrize("seen", ["none", "the first"])
def test_a_photo_nobody_saw_is_never_replaced(
    asha: StaffMember, baba: StaffMember, mama: StaffMember, seen: str
) -> None:
    # Meneja's page shows no photo, or the first one. Meanwhile Mzee sets a better one, which Meneja never saw. Then
    # Meneja's comes, late or not: refused, as a replaced photo's file is gone for good (Jack, PPL-9's review: A).
    shown = set_photo(asha, by=baba) if seen == "the first" else None
    better = set_photo(asha, by=mama, content=BETTER_FACE)
    menejas = uuid.uuid7()

    with pytest.raises(VersionConflict):
        set_photo(asha, by=baba, photo_id=menejas, instead_of=shown)

    assert photo_of(asha) == better
    assert stored_bytes(row_of(asha, better)) == BETTER_FACE
    with shop_context(asha.shop_id):
        assert not Attachment.objects.filter(pk=menejas).exists()


def test_a_photo_taken_off_meanwhile_is_not_quietly_replaced(asha: StaffMember, baba: StaffMember) -> None:
    # Meneja's page still shows a photo someone else took off, with a reason he hasn't read: he is told, and decides.
    seen = set_photo(asha, by=baba)
    with shop_context(asha.shop_id):
        remove_worker_photo(asha, photo_id=seen, reason="Hataki picha", by=baba)

    with pytest.raises(VersionConflict):
        set_photo(asha, by=baba, content=BETTER_FACE, instead_of=seen)

    assert photo_of(asha) is None


def test_a_photo_taken_off_never_comes_back_by_itself(
    asha: StaffMember, baba: StaffMember, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    photo_id = set_photo(asha, by=baba)
    with shop_context(asha.shop_id), django_capture_on_commit_callbacks(execute=True):
        remove_worker_photo(asha, photo_id=photo_id, reason="Hataki picha", by=baba)
        set_worker_photo(asha, photo_id=photo_id, instead_of=None, content=FACE, by=baba)

    assert photo_of(asha) is None
    assert stored_bytes(row_of(asha, photo_id)) is None


def test_another_file_under_the_same_id_refused(asha: StaffMember, baba: StaffMember) -> None:
    # One id, one photo: another file under it can only be a page's mistake, and would else be taken for a repeat and
    # quietly lost.
    photo_id = set_photo(asha, by=baba)

    with pytest.raises(ValidationError) as refused:
        set_photo(asha, by=baba, content=BETTER_FACE, photo_id=photo_id)

    assert code_of(refused) == "attachment.file_differs"
    assert stored_bytes(row_of(asha, photo_id)) == FACE


def test_an_id_of_another_record_is_taken(asha: StaffMember, baba: StaffMember, staff_a2: StaffMember) -> None:
    # A coworker's photo named as Asha's: refused, and nothing of it changes hands. Asha never shows a coworker's face.
    theirs = set_photo(staff_a2, by=baba)

    with pytest.raises(ValidationError) as refused:
        set_photo(asha, by=baba, photo_id=theirs)

    assert code_of(refused) == "id.taken"
    assert photo_of(asha) is None
    assert row_of(staff_a2, theirs).subject_id == staff_a2.pk


def test_a_photo_is_kept_whole_or_not_at_all(
    asha: StaffMember,
    baba: StaffMember,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: CommitSteps,
) -> None:
    # The last step fails, the old photo's removal: the new photo's row is undone with the rest, and its file was never
    # written, as a file no row names is a face that nothing would ever find to delete (PPL-9's review). The old photo
    # still shows, its file too.
    shown = set_photo(asha, by=baba)
    new = uuid.uuid7()

    def fails(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the old photo could not be removed")

    monkeypatch.setattr("apps.people.services.remove_attachment_file", fails)
    with django_capture_on_commit_callbacks(execute=True), pytest.raises(RuntimeError):
        set_photo(asha, by=baba, content=BETTER_FACE, photo_id=new)

    assert photo_of(asha) == shown
    assert stored_bytes(row_of(asha, shown)) == FACE
    with shop_context(asha.shop_id):
        assert not Attachment.objects.filter(pk=new).exists()
        assert not default_storage.exists(f"{asha.shop_id}/{new}")


@pytest.mark.parametrize(
    ("content", "code"),
    [
        pytest.param(FACE + b"x" * LARGEST_FILE, "attachment.too_big", id="too big"),
        pytest.param(PNG, "attachment.not_an_image", id="not a JPEG or a WebP"),
        pytest.param(b"", "attachment.not_an_image", id="empty"),
    ],
)
def test_a_file_that_is_no_photo_changes_nothing(
    asha: StaffMember, baba: StaffMember, content: bytes, code: str
) -> None:
    # The photo she has stays: a refused one never takes its place, and leaves no row behind.
    shown = set_photo(asha, by=baba)

    with pytest.raises(ValidationError) as refused:
        set_photo(asha, by=baba, content=content)

    assert code_of(refused) == code
    assert photo_of(asha) == shown
    with shop_context(asha.shop_id):
        assert Attachment.objects.count() == 1


def test_a_photo_of_exactly_1_mb_is_kept(asha: StaffMember, baba: StaffMember) -> None:
    largest = FACE + b"x" * (LARGEST_FILE - len(FACE))

    assert stored_bytes(row_of(asha, set_photo(asha, by=baba, content=largest))) == largest


def test_a_photo_taken_off_keeps_its_row(
    asha: StaffMember, baba: StaffMember, mama: StaffMember, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    photo_id = set_photo(asha, by=mama)
    with shop_context(asha.shop_id), django_capture_on_commit_callbacks(execute=True):
        answer = remove_worker_photo(asha, photo_id=photo_id, reason="  Hataki picha  ", by=baba)

    assert answer.photo_id is None
    assert photo_of(asha) is None
    row = row_of(asha, photo_id)
    assert row.file_state == "removed"
    # Who added it, who took it off, and why, in their own words (rule 7).
    assert (row.created_by_id, row.file_removed_by_id, row.file_removed_reason) == (mama.pk, baba.pk, "Hataki picha")
    assert stored_bytes(row) is None


@pytest.mark.parametrize("reason", ["", "   "], ids=["empty", "spaces"])
def test_taking_a_photo_off_needs_a_reason(asha: StaffMember, baba: StaffMember, reason: str) -> None:
    photo_id = set_photo(asha, by=baba)

    with shop_context(asha.shop_id), pytest.raises(ValidationError) as refused:
        remove_worker_photo(asha, photo_id=photo_id, reason=reason, by=baba)

    assert code_of(refused) == "staff.reason_required"
    assert photo_of(asha) == photo_id


def test_taking_a_photo_off_twice_is_done_once(asha: StaffMember, baba: StaffMember) -> None:
    # Meneja and Mzee both press Ondoa picha, or one presses again after an answer that was lost: the second finds it
    # gone already, which is what was wanted, and the first's reason stays.
    photo_id = set_photo(asha, by=baba)
    with shop_context(asha.shop_id):
        remove_worker_photo(asha, photo_id=photo_id, reason="Hataki picha", by=baba)
        again = remove_worker_photo(asha, photo_id=photo_id, reason="Tena", by=baba)

    assert again.photo_id is None
    assert row_of(asha, photo_id).file_removed_reason == "Hataki picha"


def test_a_late_removal_never_takes_off_a_newer_photo(asha: StaffMember, baba: StaffMember) -> None:
    # Meneja presses Ondoa picha on a slow network. Meanwhile Mzee sets a better photo, which Meneja never saw: it
    # stays, its file too, and Meneja's page reads the worker again.
    seen = set_photo(asha, by=baba)
    newer = set_photo(asha, by=baba, content=BETTER_FACE)

    with shop_context(asha.shop_id), pytest.raises(VersionConflict):
        remove_worker_photo(asha, photo_id=seen, reason="Hataki picha", by=baba)

    assert photo_of(asha) == newer
    assert stored_bytes(row_of(asha, newer)) == BETTER_FACE


def test_taking_off_a_photo_nobody_set_changes_nothing(asha: StaffMember, baba: StaffMember) -> None:
    with shop_context(asha.shop_id):
        answer = remove_worker_photo(asha, photo_id=uuid.uuid7(), reason="Hataki picha", by=baba)
        assert answer.photo_id is None
        assert not EditEvent.objects.filter(subject_type="staff", subject_id=asha.pk).exists()


def test_each_photo_change_names_who_made_it(
    asha: StaffMember, baba: StaffMember, django_capture_on_commit_callbacks: CommitSteps
) -> None:
    # Each of the three lives in the edit history alone, so it must name the person even outside an office visit, as
    # every staff action does (02 v1.7): the job's own line, and the photo's, as its file came and went.
    with django_capture_on_commit_callbacks(execute=True):
        first = set_photo(asha, by=baba)
        second = set_photo(asha, by=baba, content=BETTER_FACE)
        with shop_context(asha.shop_id):
            remove_worker_photo(asha, photo_id=second, reason="Hataki picha", by=baba)

    with shop_context(asha.shop_id):
        of_job = list(EditEvent.objects.filter(subject_type="staff", subject_id=asha.pk).order_by("id"))
        of_photos = list(EditEvent.objects.filter(subject_type="attachment", subject_id__in=[first, second]))
        lines = AuditEvent.objects.filter(subject_id=asha.pk).count()
    assert [(edit.before["photo_id"], edit.after["photo_id"]) for edit in of_job] == [
        (None, str(first)),
        (str(first), str(second)),
        (str(second), None),
    ]
    # Two files came, two went: four lines.
    assert len(of_photos) == 4
    assert {edit.created_by_id for edit in [*of_job, *of_photos]} == {baba.pk}
    # No audit line: the history already says who, when, from which and to which (PPL-9's card).
    assert lines == 0


def test_each_photo_change_tells_the_laptops(asha: StaffMember, baba: StaffMember) -> None:
    # A laptop learns what changed from the shop's change log alone (SYNC-15): with no line, a new face would never
    # reach a tile, and one taken off would stay on it. One line each, naming her job, as her nickname's fix does.
    with lines_written(asha.shop_id) as added:
        set_photo(asha, by=baba)
    with lines_written(asha.shop_id) as replaced:
        second = set_photo(asha, by=baba, content=BETTER_FACE)
    with lines_written(asha.shop_id) as taken_off, shop_context(asha.shop_id):
        remove_worker_photo(asha, photo_id=second, reason="Hataki picha", by=baba)

    hers = [("staff", asha.pk, "upsert")]
    assert (added, replaced, taken_off) == (hers, hers, hers)


def test_a_photo_change_that_changes_nothing_tells_no_laptop(asha: StaffMember, baba: StaffMember) -> None:
    # The same photo sent again after a lost answer, one refused, and a removal with nothing left to remove: every
    # laptop's copy is right as it is, so none is told to read her row again.
    shown = set_photo(asha, by=baba)
    with lines_written(asha.shop_id) as sent_again:
        set_photo(asha, by=baba, photo_id=shown, instead_of=None)
    with lines_written(asha.shop_id) as no_photo, pytest.raises(ValidationError):
        set_photo(asha, by=baba, content=PNG)
    with lines_written(asha.shop_id) as late, pytest.raises(VersionConflict):
        set_photo(asha, by=baba, content=BETTER_FACE, instead_of=None)
    with shop_context(asha.shop_id):
        remove_worker_photo(asha, photo_id=shown, reason="Hataki picha", by=baba)
        with lines_written(asha.shop_id) as removed_again:
            remove_worker_photo(asha, photo_id=shown, reason="Tena", by=baba)

    assert (sent_again, no_photo, late, removed_again) == ([], [], [], [])


def test_a_photo_reaches_the_laptops_of_its_own_shop_alone(asha: StaffMember, baba: StaffMember, shop_b: Shop) -> None:
    # Asha works at two shops. The photo is her job's at shop A, not hers (02 §5), so shop B's laptops, whose tiles show
    # shop B's photo of her, hear nothing: unlike her name, which is the person's and reaches both.
    with shop_context(shop_b):
        add_staff(shop=shop_b, user=User.objects.get(pk=asha.user_id), display_name="Asha", started_on=START, by=None)

    with lines_written(asha.shop_id) as at_a, lines_written(shop_b) as at_b:
        set_photo(asha, by=baba)

    assert (at_a, at_b) == ([("staff", asha.pk, "upsert")], [])


def test_a_photo_leaves_the_version_alone(asha: StaffMember, baba: StaffMember) -> None:
    # As a suspension or a PIN does (PPL-10): Mzee sets Asha's photo while Meneja is typing her new phone, and Meneja's
    # fix still saves. The one row that moves is the photo's own column.
    photo_id = set_photo(asha, by=baba)
    with shop_context(asha.shop_id):
        remove_worker_photo(asha, photo_id=photo_id, reason="Hataki picha", by=baba)
        assert StaffMember.objects.get(pk=asha.pk).version == asha.version


def test_a_photo_stays_in_its_shop(asha: StaffMember, baba: StaffMember, shop_b: Shop, staff_b: StaffMember) -> None:
    # T1, both ways: a worker of another shop than the one open, and a person of another shop acting.
    for opened, acting in ((shop_b, staff_b), (shop_b, baba), (asha.shop, staff_b)):
        with shop_context(opened):
            with pytest.raises(ValidationError) as refused:
                set_worker_photo(asha, photo_id=uuid.uuid7(), instead_of=None, content=FACE, by=acting)
            assert code_of(refused) == "staff.other_shop"
            with pytest.raises(ValidationError) as refused:
                remove_worker_photo(asha, photo_id=uuid.uuid7(), reason="Hataki picha", by=acting)
            assert code_of(refused) == "staff.other_shop"
    assert photo_of(asha) is None


def test_no_photo_is_kept_on_the_demo(shop_a: Shop, asha: StaffMember, baba: StaffMember, settings: Settings) -> None:
    # Every visitor there is Meneja, so a photo one saves would show to every visitor after, and it could be a real
    # person's face (Jack, PPL-9). Refused for the seed's people and for a worker a visitor added alike, and nothing is
    # kept: not the file, not its row.
    settings.DEMO_SEED = True
    with shop_context(shop_a):
        juma = add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", by=baba)

    for worker in (asha, juma):
        with pytest.raises(ValidationError) as refused:
            set_photo(worker, by=baba)
        assert code_of(refused) == "demo.photos_fixed"
        assert photo_of(worker) is None
    with shop_context(shop_a):
        assert not Attachment.objects.exists()
