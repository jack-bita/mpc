"""apps/people/tests/test_worker_details.py — fixing a worker's details (PPL-10; 02 §5).

Meneja added Asha with a typo in her name. He opens her page, taps Badilisha, fixes it and saves. Baba, on his own
phone, had her page open too: if he saves a fix of his own after Meneja's, from the copy he read before it, his save
is refused (409 version_conflict) instead of quietly undoing Meneja's. A worker's job is an Editable row for that
(apps/core/editing.py): its `version` goes up by 1 at each fix, and a fix sent with an older one is refused.

A suspension, a leaving or a PIN isn't a fix: each locks the row its own way and writes only its own columns, so it
leaves the version as it is, and a fix typed meanwhile still saves.

The fix itself is change_worker (apps/people/services.py). Only the boxes sent change; every change asks why, and
writes one audit line with each detail before and after, as the full name and the phone are the person's, which no
shop's edit history keeps (Jack, PPL-10: A). A phone is stored in one form, and one another person has is refused,
saying only that it is in use. What a laptop shows travels: a new full name to every shop where the person works, a
new nickname to this one; the job title, the first day and the phone to none. On the demo no worker gets a phone
(Jack, PPL-10: A). Who may is test_who_changes_a_worker.py's. Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.control.models import AuditAction, AuditEvent, EditEvent
from apps.core.acting import acting_as
from apps.core.editing import VersionConflict, editing
from apps.core.models import ChangeOp
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, add_worker, change_worker, grant_permission, mark_left, suspend
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from tests.change_log import lines_written
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

START = date(2026, 3, 2)
WHY = "Niliandika vibaya"


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


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager the owner has handed staff.manage, on the whole shop: he may fix the workers (the PIN's rule).
    user = User.objects.create_user(full_name="Meneja Mfano")
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=user, display_name="Meneja", by=None)
    give_role(staff, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(staff, Permission.STAFF_MANAGE, side=None, by=None)
    return staff


def fix(staff: StaffMember, *, version: int = 1, by: StaffMember | None = None, **details: object) -> StaffMember:
    # A fix as the page sends it: the boxes it changed, the version it read, and why.
    with shop_context(staff.shop_id):
        return change_worker(staff, version=version, reason=WHY, by=by, **details)  # type: ignore[arg-type]


def stored(staff: StaffMember) -> StaffMember:
    with shop_context(staff.shop_id):
        return StaffMember.objects.select_related("user").get(pk=staff.pk)


def details_lines(staff: StaffMember) -> list[AuditEvent]:
    with shop_context(staff.shop_id):
        return list(
            AuditEvent.objects.filter(subject_type="staff", subject_id=staff.pk, action="staff.details_changed")
        )


def codes(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, list[str]]:
    # Each box's codes, as the API's fields carry them (apps/core/api/errors.py).
    return {name: [error.code or "" for error in errors] for name, errors in refused.value.error_dict.items()}


def test_a_fix_changes_only_the_details_sent(asha: StaffMember) -> None:
    fixed = fix(asha, job_title="Muuzaji")

    now = stored(asha)
    assert (now.job_title, now.display_name, now.started_on, now.user.full_name) == (
        "Muuzaji",
        "Asha",
        START,
        "Asha Mfano",
    )
    assert fixed.version == now.version == 2


def test_a_fix_from_an_old_copy_is_refused_before_its_boxes_are_judged(asha: StaffMember) -> None:
    # Baba's copy, read at version 1, holds an empty nickname: refused as old, which sends the page to read Asha again,
    # not as blank, as whatever its boxes say was typed on what Asha no longer is.
    fix(asha, job_title="Muuzaji")

    with pytest.raises(VersionConflict):
        fix(asha, display_name="")

    assert (stored(asha).display_name, stored(asha).version) == ("Asha", 2)


def test_a_fix_of_the_persons_details_alone_moves_the_version_too(asha: StaffMember) -> None:
    # The page's copy holds her phone too: Baba's phone, typed on the copy read before Meneja's, is refused.
    fix(asha, phone="0712 345 678")

    with pytest.raises(VersionConflict):
        fix(asha, phone="0754 000 111")

    assert (stored(asha).user.phone, stored(asha).version) == ("+255712345678", 2)


def test_a_fix_needs_a_reason(asha: StaffMember) -> None:
    with pytest.raises(ValidationError) as refused, shop_context(asha.shop_id):
        change_worker(asha, version=1, reason="   ", by=None, job_title="Muuzaji")

    assert refused.value.code == "staff.reason_required"
    assert (stored(asha).job_title, details_lines(asha)) == ("Muuzji", [])


def test_a_phone_is_stored_in_one_form(asha: StaffMember) -> None:
    # Typed as people write it; stored as every phone is (apps/core/phones.py), so a login by it finds her.
    fix(asha, phone="0712 345 678")

    assert stored(asha).user.phone == "+255712345678"


def test_an_empty_phone_box_takes_the_phone_off(asha: StaffMember) -> None:
    # Asha logs in with her PIN alone: she has no password, so a phone she no longer has may go.
    fix(asha, phone="0712 345 678")
    fix(asha, version=2, phone="")

    # NULL, never "": many people without a phone must not clash on `unique` (apps/people/models.py).
    assert stored(asha).user.phone is None


def with_a_password(staff: StaffMember, *, email: str | None = None) -> None:
    # The person logs in with a password from their own phone, as a temporary one leaves them (AUTH-6).
    person = User.objects.get(pk=staff.user_id)
    person.set_password("siri-ya-mfano-2026")
    person.email = email
    person.save()


def test_a_phone_that_is_someones_only_way_in_cant_be_taken_off(asha: StaffMember) -> None:
    # Baba set Asha a temporary password, and she has no email: emptying her phone would lock her out for good.
    fix(asha, phone="0712 345 678")
    with_a_password(asha)

    with pytest.raises(ValidationError) as refused:
        fix(asha, version=2, phone="")

    assert codes(refused) == {"phone": ["phone.needed_to_log_in"]}
    assert (stored(asha).user.phone, stored(asha).version, len(details_lines(asha))) == ("+255712345678", 2, 1)


def test_such_a_phone_may_change_and_may_go_once_there_is_an_email(asha: StaffMember) -> None:
    # A new number keeps her way in: she logs in with it and the same password. With an email, she has another.
    fix(asha, phone="0712 345 678")
    with_a_password(asha)

    fix(asha, version=2, phone="0754 000 111")
    assert stored(asha).user.phone == "+255754000111"

    with_a_password(asha, email="asha@example.com")
    fix(asha, version=3, phone="")
    assert stored(asha).user.phone is None


def test_a_phone_another_person_has_is_refused_and_says_only_that(asha: StaffMember, shop_b: Shop) -> None:
    # Someone at another shop already has the number. The refusal says it is in use, under the phone's box, and
    # nothing more: not whose it is, nor at which shop, which this shop has no right to know.
    User.objects.create_user(full_name="Mtu wa Duka Jingine", phone="0712 345 678")

    with pytest.raises(ValidationError) as refused:
        fix(asha, phone="0712345678")

    assert codes(refused) == {"phone": ["unique"]}
    assert "Mtu wa Duka Jingine" not in str(refused.value)
    assert (stored(asha).user.phone, stored(asha).version) == (None, 1)


def test_every_refusal_comes_back_together(asha: StaffMember, staff_a2: StaffMember) -> None:
    # A blank full name, a wrong phone, a blank job title (which may be empty) and a nickname another current worker
    # has, in any letter case: each box's refusal at once, so Meneja fixes them all in one go. Nothing is saved.
    with pytest.raises(ValidationError) as refused:
        fix(asha, full_name="  ", phone="12345", job_title="", display_name="staff a2")

    assert codes(refused) == {
        "full_name": ["blank"],
        "phone": ["phone.invalid"],
        "__all__": ["staff.display_name_taken"],
    }
    now = stored(asha)
    assert (now.user.full_name, now.job_title, now.version) == ("Asha Mfano", "Muuzji", 1)


def test_each_fix_writes_one_audit_line_with_before_and_after(asha: StaffMember, meneja: StaffMember) -> None:
    # Baba asks a week later who changed Asha's phone, and why: one line holds it all, the job's details beside the
    # person's, as the edit history can't keep a person's (ADR-0036).
    fix(
        asha,
        by=meneja,
        full_name="Asha Mfano Mpya",
        phone="0712 345 678",
        job_title="Muuzaji",
        started_on=date(2026, 3, 3),
    )

    [line] = details_lines(asha)
    assert (line.action, line.reason, line.created_by_id) == (AuditAction.STAFF_DETAILS_CHANGED, WHY, meneja.pk)
    assert line.before == {"full_name": "Asha Mfano", "phone": None, "job_title": "Muuzji", "started_on": "2026-03-02"}
    assert line.after == {
        "full_name": "Asha Mfano Mpya",
        "phone": "+255712345678",
        "job_title": "Muuzaji",
        "started_on": "2026-03-03",
    }


def test_a_box_typed_back_as_it_was_writes_nothing(asha: StaffMember) -> None:
    # Nothing to fix: no new version, no audit line, no line for the laptops.
    with lines_written(asha.shop_id) as lines:
        fix(asha, full_name=" Asha Mfano ", display_name="Asha", job_title="Muuzji", phone="")

    assert (stored(asha).version, details_lines(asha), lines) == (1, [], [])


def test_a_full_name_fix_reaches_every_shop_where_they_work(
    asha: StaffMember, meneja: StaffMember, shop_b: Shop
) -> None:
    # Asha works at a second shop too. Her name is on her tile in both, so both shops' laptops hear of it, in the office
    # visit Meneja opens at his own shop (acting_as, apps/core/acting.py).
    person = User.objects.get(pk=asha.user_id)
    with shop_context(shop_b):
        at_b = add_staff(shop=shop_b, user=person, display_name="Asha", by=None)

    with lines_written(asha.shop_id) as at_a, lines_written(shop_b) as at_b_lines, acting_as(meneja):
        fix(asha, by=meneja, full_name="Asha Mfano Mpya")

    assert (at_a, at_b_lines) == ([("staff", asha.pk, ChangeOp.UPSERT)], [("staff", at_b.pk, ChangeOp.UPSERT)])


def test_a_nickname_fix_writes_this_jobs_line(asha: StaffMember) -> None:
    with lines_written(asha.shop_id) as lines:
        fix(asha, display_name="Asha M")

    assert lines == [("staff", asha.pk, ChangeOp.UPSERT)]


def test_what_no_laptop_shows_tells_no_laptop(asha: StaffMember) -> None:
    # The job title, the first day and the phone stay on the server (StaffRecord): fixing them writes no line.
    with lines_written(asha.shop_id) as lines:
        fix(asha, job_title="Muuzaji", started_on=date(2026, 3, 3), phone="0712 345 678")

    assert lines == []


def test_a_suspended_worker_can_still_be_fixed(asha: StaffMember, meneja: StaffMember) -> None:
    # 02 §5: never one who left, but a suspended one, yes. Asha is suspended while a missing week is looked into, and
    # Meneja fixes her job title in the meantime: the fix goes through, and she stays suspended.
    with shop_context(asha.shop_id):
        suspend(asha, by=None, reason="Hakuja siku tatu")

    fix(asha, by=meneja, job_title="Muuzaji")

    now = stored(asha)
    assert (now.status, now.job_title, now.version) == ("suspended", "Muuzaji", 2)
    assert len(details_lines(asha)) == 1


def fixed_at_the_same_moment(first: StaffMember, second: StaffMember, **details: str) -> object:
    # The first fix saved and not yet committed when the second arrives: the second's check can't see it, so its save
    # reaches the database's unique rule, which waits for the first. Once the first commits, the second is refused.
    def the_second_fix() -> object:
        return fix(second, version=1, by=None, **details)

    with transaction.atomic():
        fix(first, version=1, by=None, **details)
        other, ended = in_another_transaction(the_second_fix)
        wait_until_someone_waits_for_me()
    other.join(timeout=5)
    assert not other.is_alive(), "The second fix still waits after the first committed."
    return ended[0]


@pytest.mark.django_db(transaction=True)
def test_a_nickname_taken_at_the_same_moment_answers_as_taken(asha: StaffMember, staff_a2: StaffMember) -> None:
    # Meneja names Asha "Juma" while Baba names the other worker "Juma": the second hears it is taken, not a server
    # error.
    refused = fixed_at_the_same_moment(asha, staff_a2, display_name="Juma")

    assert isinstance(refused, ValidationError)
    assert refused.error_dict["__all__"][0].code == "staff.display_name_taken"
    assert (stored(staff_a2).display_name, stored(staff_a2).version) == ("Staff A2", 1)


@pytest.mark.django_db(transaction=True)
def test_a_phone_taken_at_the_same_moment_answers_as_taken(asha: StaffMember, staff_a2: StaffMember) -> None:
    refused = fixed_at_the_same_moment(asha, staff_a2, phone="0712 345 678")

    assert isinstance(refused, ValidationError)
    assert {name: [error.code for error in errors] for name, errors in refused.error_dict.items()} == {
        "phone": ["unique"]
    }
    assert (stored(staff_a2).user.phone, stored(staff_a2).version) == (None, 1)
    assert details_lines(staff_a2) == []


def test_a_worker_who_left_cant_be_fixed(asha: StaffMember) -> None:
    # Her job is history: what it said then stays as it was, even for the system.
    with shop_context(asha.shop_id):
        mark_left(asha, left_on=START, by=None, reason="Amehamia Moshi")

    with pytest.raises(ValidationError) as refused:
        fix(asha, job_title="Muuzaji")

    assert refused.value.code == "staff.left"


def test_a_first_day_still_to_come_fixed_to_today_lets_one_who_never_started_go(shop_a: Shop) -> None:
    # PPL-6's review: Juma was added to start next week, then never came. His last day lies between his first day and
    # today, so he can't be marked left yet; fixing his first day to today lets him go.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        juma = add_worker(
            shop=shop_a, full_name="Juma Mfano", display_name="Juma", started_on=today + timedelta(7), by=None
        )
        with pytest.raises(ValidationError) as refused:
            mark_left(juma, left_on=today, by=None, reason="Hakuja kuanza kazi")
    assert refused.value.error_dict["__all__"][0].code == "staff.left_before_start"

    fix(juma, started_on=today)
    with shop_context(shop_a):
        mark_left(juma, left_on=today, by=None, reason="Hakuja kuanza kazi")

    assert stored(juma).status == "left"


def test_no_phone_on_the_demo(shop_a: Shop, meneja: StaffMember, settings: Settings) -> None:
    # Every visitor logs in as Meneja: a stranger's real number typed on a worker they added would show to every later
    # visitor. The worker's other details can be fixed, as trying the page is the point (Jack, PPL-10: A).
    settings.DEMO_SEED = True
    with shop_context(shop_a):
        juma = add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", by=meneja)

    with pytest.raises(ValidationError) as refused:
        fix(juma, by=meneja, phone="0712 345 678")
    assert refused.value.code == "demo.phones_fixed"

    fix(juma, by=meneja, job_title="Mpakiaji")
    assert (stored(juma).job_title, stored(juma).user.phone) == ("Mpakiaji", None)
