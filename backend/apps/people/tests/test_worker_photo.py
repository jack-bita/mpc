"""apps/people/tests/test_worker_photo.py — a worker's photo (PPL-9, 02 §5).

The job at one shop names the photo it shows now (`StaffMember.photo`), an attachment of kind `staff_photo` (CTRL-3).
Asha's row, as her photo is set, changed, and taken off:

    photo      what happened
    (none)     added by Meneja: her tile shows her full name
    0193…a1    Meneja took her photo
    0193…b2    Mzee chose a better one: the first one's file is gone, its row stays
    (none)     taken off, with a reason

Only which photo is shown lives on the job: the file, its label, who added it and who removed it are the attachment's
own (apps/control/models.py), so each fact lives once. Fake data only: the repo is public (03 §10).
"""

import hashlib
import uuid
from datetime import date

import pytest

from apps.control.models import Attachment, AttachmentKind, AttachmentType, EditEvent
from apps.control.services import expect_attachment
from apps.core.acting import acting_as
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

# A date in the past: a first day far ahead would read as a typing mistake.
START = date(2026, 3, 2)
# The first bytes every JPEG starts with, and some of our own: the server knows a photo by its first bytes (CTRL-3).
FACE = b"\xff\xd8\xff" + b"a made-up photo of Asha"


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    user = User.objects.create_user(full_name="Asha Demo")
    with shop_context(shop_a):
        return add_staff(shop=shop_a, user=user, display_name="Asha", started_on=START, by=None)


def a_photo_of(staff: StaffMember, *, by: StaffMember) -> Attachment:
    # A photo's row as the service writes it, its file still to come: enough for the job to name.
    return expect_attachment(
        id=uuid.uuid7(),
        kind=AttachmentKind.STAFF_PHOTO,
        subject=staff,
        content_type=AttachmentType.JPEG,
        size=len(FACE),
        sha256=hashlib.sha256(FACE).hexdigest(),
        by=by,
    )


def test_a_new_worker_has_no_photo(asha: StaffMember) -> None:
    # 02 §5: the photo is optional, so nobody is stopped from working for want of one.
    assert asha.photo_id is None


def test_a_photo_change_is_kept_in_the_edit_history(shop_a: Shop, asha: StaffMember, staff_a: StaffMember) -> None:
    # The photo has no audit line of its own (PPL-9's card): the edit history alone says who changed the face on every
    # laptop's tile, so the new column must be one PostgreSQL's trigger copies (ADR-0036).
    with shop_context(shop_a), acting_as(staff_a):
        photo = a_photo_of(asha, by=staff_a)
        asha.photo = photo
        asha.save(update_fields=["photo"])
        edits = list(EditEvent.objects.filter(subject_type="staff", subject_id=asha.pk))

    assert [(edit.created_by_id, edit.before, edit.after) for edit in edits] == [
        (staff_a.pk, {"photo_id": None}, {"photo_id": str(photo.pk)})
    ]
