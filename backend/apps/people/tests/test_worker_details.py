"""apps/people/tests/test_worker_details.py — fixing a worker's details (PPL-10; 02 §5).

Meneja added Asha with a typo in her name. He opens her page, taps Badilisha, fixes it and saves. Baba, on his own
phone, had her page open too: if he saves a fix of his own after Meneja's, from the copy he read before it, his save
is refused (409 version_conflict) instead of quietly undoing Meneja's. A worker's job is an Editable row for that
(apps/core/editing.py): its `version` goes up by 1 at each fix, and a fix sent with an older one is refused.

A suspension, a leaving or a PIN isn't a fix: each locks the row its own way and writes only its own columns, so it
leaves the version as it is, and a fix typed meanwhile still saves. Fake data only: the repo is public (03 §10).
"""

from datetime import date

import pytest

from apps.control.models import EditEvent
from apps.core.editing import VersionConflict, editing
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, suspend
from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

START = date(2026, 3, 2)


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    # Added with the wrong job title, to be fixed.
    user = User.objects.create_user(full_name="Asha Mfano")
    with shop_context(shop_a):
        return add_staff(shop=shop_a, user=user, display_name="Asha", job_title="Muuzji", started_on=START, by=None)


def test_a_new_job_starts_at_its_first_version(asha: StaffMember) -> None:
    # Every job starts at 1, and nobody has fixed it yet: the adding is in `created_by` and `created_at`.
    assert (asha.version, asha.updated_by_id, asha.updated_at) == (1, None, None)


def test_a_fix_moves_the_version_on_and_names_who(asha: StaffMember, staff_a: StaffMember) -> None:
    with shop_context(asha.shop_id):
        with editing(asha, version=1, by=staff_a) as fresh:
            fresh.job_title = "Muuzaji"
        stored = StaffMember.objects.get(pk=asha.pk)
    assert (stored.job_title, stored.version, stored.updated_by_id) == ("Muuzaji", 2, staff_a.pk)
    assert stored.updated_at is not None


def test_a_fix_from_an_old_copy_is_refused(asha: StaffMember, staff_a: StaffMember) -> None:
    # Meneja and Baba both read Asha at version 1. Meneja's fix goes first and moves her to 2.
    with shop_context(asha.shop_id):
        with editing(asha, version=1, by=staff_a) as fresh:
            fresh.job_title = "Muuzaji"
        # Baba's fix, from his copy at 1, would put his own words over Meneja's: refused, and nothing of it is saved.
        with pytest.raises(VersionConflict), editing(asha, version=1, by=None) as fresh:
            fresh.job_title = "Muuzaji wa dawa"
        stored = StaffMember.objects.get(pk=asha.pk)
    assert (stored.job_title, stored.version) == ("Muuzaji", 2)


def test_a_suspension_leaves_the_version_as_it_is(asha: StaffMember) -> None:
    # Not a fix: Meneja's half-typed fix of her job title, read at version 1, still saves after Baba suspends her, on
    # top of the row as it is then. Her status stays suspended: the fix writes the row read under its own lock.
    with shop_context(asha.shop_id):
        suspend(asha, by=None, reason="Hakuja siku tatu")
        with editing(asha, version=1, by=None) as fresh:
            fresh.job_title = "Muuzaji"
        stored = StaffMember.objects.get(pk=asha.pk)
    assert (stored.status, stored.job_title, stored.version) == ("suspended", "Muuzaji", 2)


def test_the_history_keeps_the_fix_and_not_the_version(asha: StaffMember, staff_a: StaffMember) -> None:
    # The edit history's trigger skips an editable row's own bookkeeping (ADR-0036): the line says what the owner
    # needs, the job title before and after, and keeps who and when in its own columns.
    with shop_context(asha.shop_id):
        with editing(asha, version=1, by=staff_a) as fresh:
            fresh.job_title = "Muuzaji"
        lines = list(EditEvent.objects.filter(subject_type="staff", subject_id=asha.pk))
    assert [(line.before, line.after, line.created_by_id) for line in lines] == [
        ({"job_title": "Muuzji"}, {"job_title": "Muuzaji"}, staff_a.pk)
    ]
