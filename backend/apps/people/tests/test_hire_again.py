"""apps/people/tests/test_hire_again.py — a worker who left, hired again as the same person (PPL-11; 02 §5).

Baraka worked at the shop from 2 January 2025 and left on 12 March 2026. In June Baba hires him again. He is the same
person (one User), so his phone and his password stay his, and he comes back with a new job, from the day chosen: the
old job keeps what it said, its nickname, its days and its history, as a job that ended is never changed. That is
hire_again (apps/people/services.py), which the workers' page calls from the old job's page, or from Ongeza once his
phone has found him.

Refused: a job that hasn't ended; a person who works here again already, even when two managers hire him at the same
moment; a person who works at another shop now, until AUTH-7 (ADR-0045); a first day before his last one; a nickname
another current worker holds by now. Who may is the add's, staff.manage on the whole shop. Fake data only: the repo is
public (03 §10).
"""

import uuid
from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.core.models import ChangeOp
from apps.core.permissions import Permission
from apps.core.tenancy import shop_context, system_context
from apps.people.models import StaffMember, StaffStatus, User
from apps.people.services import add_staff, grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from tests.change_log import lines_written
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

FIRST_DAY = date(2025, 1, 2)
LAST_DAY = date(2026, 3, 12)
BACK_ON = date(2026, 6, 1)


@pytest.fixture
def baraka(shop_a: Shop) -> StaffMember:
    # His job at shop A, which ended on 12 March.
    user = User.objects.create_user(full_name="Baraka Mfano")
    with shop_context(shop_a):
        job = add_staff(
            shop=shop_a, user=user, display_name="Baraka", job_title="Muuzaji wa dawa", started_on=FIRST_DAY, by=None
        )
        return mark_left(job, left_on=LAST_DAY, by=None, reason="Amehamia Moshi")


@pytest.fixture
def meneja(staff_a: StaffMember) -> StaffMember:
    # A manager the owner has handed staff.manage, on the whole shop: he may add workers, so he may hire one again.
    with shop_context(staff_a.shop_id):
        grant_permission(staff_a, Permission.STAFF_MANAGE, side=None, by=None)
    return staff_a


def hire(
    old: StaffMember,
    *,
    display_name: str = "Baraka",
    started_on: date | None = BACK_ON,
    by: StaffMember | None = None,
    job_title: str = "Muuzaji",
) -> StaffMember:
    # As the page sends it: the nickname, the job title and the first day typed in the boxes.
    with shop_context(old.shop_id):
        return hire_again(old, display_name=display_name, job_title=job_title, started_on=started_on, by=by)


def jobs_of(person_id: uuid.UUID, shop: Shop) -> list[StaffMember]:
    with shop_context(shop):
        return list(StaffMember.objects.filter(user_id=person_id).order_by("started_on"))


def test_hired_again_as_the_same_person_with_a_new_job(baraka: StaffMember, meneja: StaffMember) -> None:
    new = hire(baraka, by=meneja)

    # One person, two jobs: the new one from the day chosen, named by who hired him.
    assert new.pk != baraka.pk
    assert new.user_id == baraka.user_id
    assert (new.status, new.display_name, new.job_title, new.started_on, new.left_on, new.created_by_id) == (
        StaffStatus.ACTIVE,
        "Baraka",
        "Muuzaji",
        BACK_ON,
        None,
        meneja.pk,
    )
    assert [job.pk for job in jobs_of(baraka.user_id, baraka.shop)] == [baraka.pk, new.pk]
    assert User.objects.filter(full_name="Baraka Mfano").count() == 1


def test_the_old_job_keeps_what_it_said(baraka: StaffMember) -> None:
    # A job that ended is history: its nickname, title and days stay as they were, whatever the new job says.
    hire(baraka, display_name="Bara", job_title="Mpakiaji")

    with shop_context(baraka.shop_id):
        old = StaffMember.objects.get(pk=baraka.pk)
    assert (old.status, old.display_name, old.job_title, old.started_on, old.left_on, old.version) == (
        StaffStatus.LEFT,
        "Baraka",
        "Muuzaji wa dawa",
        FIRST_DAY,
        LAST_DAY,
        baraka.version,
    )


def test_the_first_day_is_today_when_none_is_given(baraka: StaffMember) -> None:
    # Most come back the morning they are hired, as most are added (add_staff).
    new = hire(baraka, started_on=None)

    assert new.started_on == shop_today(baraka.shop)


def test_the_first_day_may_be_the_last_day(baraka: StaffMember) -> None:
    # Baba taps Ameondoka on Baraka by mistake: leaving is final, so hiring him again that same day mends it at once.
    new = hire(baraka, started_on=LAST_DAY)

    assert new.started_on == LAST_DAY


def test_the_first_day_is_never_before_the_last(baraka: StaffMember) -> None:
    # Two jobs of one person at one shop on the same days would pay and count those days twice. Said beside the box.
    with pytest.raises(ValidationError) as refused:
        hire(baraka, started_on=LAST_DAY - timedelta(days=1))

    assert [error.code for error in refused.value.error_dict["started_on"]] == ["staff.back_before_left"]
    assert len(jobs_of(baraka.user_id, baraka.shop)) == 1


def test_the_first_day_is_after_his_latest_job(baraka: StaffMember) -> None:
    # Baraka came back once and left again on 30 September. Hired again from his first job's page, his first day is
    # still measured from his latest last day, not the first job's.
    second = hire(baraka, started_on=BACK_ON)
    with shop_context(baraka.shop_id):
        mark_left(second, left_on=date(2026, 9, 30), by=None, reason="Amerudi shule")

    with pytest.raises(ValidationError) as refused:
        hire(baraka, started_on=date(2026, 9, 1))

    assert [error.code for error in refused.value.error_dict["started_on"]] == ["staff.back_before_left"]


@pytest.mark.parametrize("now", ["active", "suspended"])
def test_a_job_that_hasnt_ended_isnt_hired_again(staff_a2: StaffMember, now: str) -> None:
    # Only a job that ended: a worker still here, or suspended, has a job already.
    if now == "suspended":
        with shop_context(staff_a2.shop_id):
            suspend(staff_a2, by=None, reason="Hakuja siku tatu")

    with pytest.raises(ValidationError) as refused:
        hire(staff_a2, display_name="Staff A2 tena")

    assert refused.value.code == "staff.not_left"
    assert len(jobs_of(staff_a2.user_id, staff_a2.shop)) == 1


def test_someone_back_already_isnt_hired_again(baraka: StaffMember) -> None:
    # One current job per person per shop (02 §5): the old page, opened before he was back, is refused.
    hire(baraka)

    with pytest.raises(ValidationError) as refused:
        hire(baraka, display_name="Baraka M")

    assert refused.value.code == "staff.already_member"
    assert len(jobs_of(baraka.user_id, baraka.shop)) == 2


def test_a_person_working_at_another_shop_is_not_hired_again(baraka: StaffMember, shop_b: Shop) -> None:
    # Baraka works at shop B by now. A job at shop A too would make him a person at two shops before AUTH-7: his login
    # refused (AUTH-3), and shop A able to fix the name shop B shows. Found through the person's door, by shops' ids
    # alone (ADR-0045); the refusal names no shop.
    person = User.objects.get(pk=baraka.user_id)
    with shop_context(shop_b):
        add_staff(shop=shop_b, user=person, display_name="Baraka", by=None)

    with pytest.raises(ValidationError) as refused:
        hire(baraka)

    assert refused.value.code == "staff.works_elsewhere"
    assert len(jobs_of(baraka.user_id, baraka.shop)) == 1


def test_a_person_who_left_another_shop_too_is_hired_again(baraka: StaffMember, shop_b: Shop) -> None:
    # A job at shop B that ended is no job there: he works nowhere now.
    person = User.objects.get(pk=baraka.user_id)
    with shop_context(shop_b):
        at_b = add_staff(shop=shop_b, user=person, display_name="Baraka", started_on=FIRST_DAY, by=None)
        mark_left(at_b, left_on=LAST_DAY, by=None, reason="Amehamia Moshi")

    new = hire(baraka)

    assert new.user_id == baraka.user_id


def test_only_this_shops_jobs_count_for_the_first_day(baraka: StaffMember, shop_b: Shop) -> None:
    # Run as the system, which sees every shop (system_context, as a command would): Baraka's job at shop B, which
    # ended on 1 May, says nothing of when he may start again at shop A.
    person = User.objects.get(pk=baraka.user_id)
    with shop_context(shop_b):
        at_b = add_staff(shop=shop_b, user=person, display_name="Baraka", started_on=FIRST_DAY, by=None)
        mark_left(at_b, left_on=date(2026, 5, 1), by=None, reason="Amehamia Moshi")

    with system_context():
        new = hire_again(baraka, display_name="Baraka", started_on=date(2026, 4, 1), by=None)

    assert (new.shop_id, new.started_on) == (baraka.shop_id, date(2026, 4, 1))


def test_a_nickname_another_worker_holds_now_is_refused(baraka: StaffMember) -> None:
    # While Baraka was away, a second Baraka joined: nicknames are unique among current workers (02 §5).
    other = User.objects.create_user(full_name="Baraka Mwingine")
    with shop_context(baraka.shop_id):
        add_staff(shop=baraka.shop, user=other, display_name="baraka", by=None)

    with pytest.raises(ValidationError) as refused:
        hire(baraka)

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["staff.display_name_taken"]


def test_hiring_again_needs_staff_manage(baraka: StaffMember, staff_a2: StaffMember) -> None:
    # The add's rule: whoever may add a worker may hire one again, and nobody else.
    with pytest.raises(PermissionDenied):
        hire(baraka, by=staff_a2)

    assert len(jobs_of(baraka.user_id, baraka.shop)) == 1


def test_another_shops_job_is_refused(baraka: StaffMember, shop_b: Shop) -> None:
    # T1: shop B's visit can't hire shop A's people.
    with shop_context(shop_b), pytest.raises(ValidationError) as refused:
        hire_again(baraka, display_name="Baraka", by=None)

    assert refused.value.code == "staff.other_shop"


def test_the_laptops_hear_of_the_new_job(baraka: StaffMember) -> None:
    # A new staff row, which every laptop of the shop gets at its next sync; with no PIN yet, it shows no tile (PPL-4).
    with lines_written(baraka.shop_id) as lines:
        new = hire(baraka)

    assert lines == [("staff", new.pk, ChangeOp.UPSERT)]


@pytest.mark.django_db(transaction=True)
def test_two_managers_hiring_him_again_at_once_the_second_is_told_he_is_back(baraka: StaffMember) -> None:
    # Meneja and Baba both tap Mwajiri tena on Baraka's old page in the same second. The person's row is locked first,
    # so the second waits, then finds him back already: told so, not a server error from the database's rule.
    def the_second_hire() -> object:
        return hire(baraka, display_name="Baraka M")

    with transaction.atomic():
        hire(baraka)
        other, ended = in_another_transaction(the_second_hire)
        wait_until_someone_waits_for_me()
    other.join(timeout=5)
    assert not other.is_alive(), "The second hire still waits after the first committed."

    refused = ended[0]
    assert isinstance(refused, ValidationError)
    assert refused.code == "staff.already_member"
    assert len(jobs_of(baraka.user_id, baraka.shop)) == 2
