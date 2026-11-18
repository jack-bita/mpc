"""apps/people/tests/test_hire_again.py — a worker who left, hired again as the same person (PPL-11; 02 §5).

Baraka worked at the shop from 2 January 2025 and left on 12 March 2026. In June Baba hires him again. He is the same
person (one User), so his phone and his password stay his, and he comes back with a new job, from the day chosen: the
old job keeps what it said, its nickname, its days and its history, as a job that ended is never changed. That is
hire_again (apps/people/services.py), which the workers' page calls from the old job's page, or from Ongeza once his
phone has found him.

Refused: a job that hasn't ended; a person who works here again already, even when two managers hire him at the same
moment; a person who works at another shop now, until AUTH-7 (ADR-0045); a first day before his last one; a nickname
another current worker holds by now. Who may is the add's, staff.manage on the whole shop.

And Ongeza's Simu box (add_worker): a new worker gets their phone as they are added. Baraka's phone, typed there by a
Baba who forgot he once worked here, makes nobody: the answer names his old job, so the page offers Mwajiri tena
(staff.left_here). Any other phone a person has is only in use, saying nothing of whose, and joins nobody: a manager
who could join someone to his shop by their phone could then set their PIN and log in as them. On the demo, no phone
(PPL-10). Fake data only: the repo is public (03 §10).
"""

import uuid
from datetime import date, timedelta
from typing import cast

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.core.models import ChangeOp
from apps.core.permissions import Permission
from apps.core.tenancy import shop_context, system_context
from apps.people.models import StaffMember, StaffStatus, User
from apps.people.services import add_staff, add_worker, grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from tests.change_log import lines_written
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

FIRST_DAY = date(2025, 1, 2)
LAST_DAY = date(2026, 3, 12)
BACK_ON = date(2026, 6, 1)
PHONE = "0712 345 678"


@pytest.fixture
def baraka(shop_a: Shop) -> StaffMember:
    # His job at shop A, which ended on 12 March. His phone stays his.
    user = User.objects.create_user(full_name="Baraka Mfano", phone=PHONE)
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


# Ongeza's Simu box.


def add(shop: Shop, *, phone: str, full_name: str = "Juma Mfano", display_name: str = "Juma") -> StaffMember:
    # As Ongeza sends it, by the system: who may add is the route's and add_worker's own, tested with the routes.
    with shop_context(shop):
        return add_worker(shop=shop, full_name=full_name, display_name=display_name, phone=phone, by=None)


def phone_codes(refused: pytest.ExceptionInfo[ValidationError]) -> list[str]:
    return [error.code or "" for error in refused.value.error_dict["phone"]]


def test_a_new_worker_gets_their_phone(shop_a: Shop) -> None:
    # Typed as people write it; stored as every phone is (apps/core/phones.py), so a login by it finds him.
    juma = add(shop_a, phone="0754 000 111")

    assert User.objects.get(pk=juma.user_id).phone == "+255754000111"


def test_an_empty_phone_box_is_no_phone(shop_a: Shop) -> None:
    juma = add(shop_a, phone="")

    assert User.objects.get(pk=juma.user_id).phone is None


def test_a_wrong_phone_is_refused_beside_its_box(shop_a: Shop) -> None:
    with pytest.raises(ValidationError) as refused:
        add(shop_a, phone="12345")

    assert phone_codes(refused) == ["phone.invalid"]
    assert not User.objects.filter(full_name="Juma Mfano").exists()


def test_the_phone_of_a_worker_who_left_finds_him(baraka: StaffMember) -> None:
    # Baba starts adding Baraka as new. His phone finds him: nothing is made, and the answer names his old job, his full
    # name and his last day, which the workers' list already shows whoever may add, so the page asks "Mwajiri tena?".
    people = User.objects.count()

    with pytest.raises(ValidationError) as refused:
        add(baraka.shop, phone=PHONE, full_name="Baraka Mfano", display_name="Baraka")

    assert refused.value.code == "staff.left_here"
    assert refused.value.params == {"staff": baraka.pk, "full_name": "Baraka Mfano", "left_on": LAST_DAY}
    assert User.objects.count() == people
    assert len(jobs_of(baraka.user_id, baraka.shop)) == 1


def test_the_phone_names_his_latest_job(baraka: StaffMember) -> None:
    # He came back once and left again on 30 September: Mwajiri tena is offered from the job that ended last.
    second = hire(baraka)
    with shop_context(baraka.shop_id):
        mark_left(second, left_on=date(2026, 9, 30), by=None, reason="Amerudi shule")

    with pytest.raises(ValidationError) as refused:
        add(baraka.shop, phone=PHONE)

    assert refused.value.params == {"staff": second.pk, "full_name": "Baraka Mfano", "left_on": date(2026, 9, 30)}


@pytest.mark.parametrize(
    "whose",
    [
        "works here",
        "works at another shop",
        "left here, works elsewhere",
        "left here, suspended elsewhere",
        "left here, back here",
        "left another shop, works nowhere",
        "no job",
    ],
)
def test_the_phone_of_anyone_else_is_only_in_use(baraka: StaffMember, shop_b: Shop, whose: str) -> None:
    # Never joined, and never named: shop B's manager who typed shop A's owner's phone must learn nothing, and must get
    # no way to set his PIN. Baraka, who left here, works at shop B by now, or is suspended there, which is a job still
    # (the door counts it): hiring him again would be refused (staff.works_elsewhere), so his phone too is only in use
    # here, and says nothing of another shop. Back here already, he is no one to hire again. And a person who left
    # shop B, and works nowhere, is shop B's to name: typed at shop A, never.
    person = User.objects.get(pk=baraka.user_id)
    if whose == "works here":
        person = User.objects.create_user(full_name="Asha Mfano", phone="0754 000 111")
        with shop_context(baraka.shop_id):
            add_staff(shop=baraka.shop, user=person, display_name="Asha", by=None)
    elif whose == "works at another shop":
        person = User.objects.create_user(full_name="Asha Mfano", phone="0754 000 111")
        with shop_context(shop_b):
            add_staff(shop=shop_b, user=person, display_name="Asha", by=None)
    elif whose == "left here, works elsewhere":
        with shop_context(shop_b):
            add_staff(shop=shop_b, user=person, display_name="Baraka", by=None)
    elif whose == "left here, suspended elsewhere":
        with shop_context(shop_b):
            at_b = add_staff(shop=shop_b, user=person, display_name="Baraka", by=None)
            suspend(at_b, by=None, reason="Hakuja siku tatu")
    elif whose == "left here, back here":
        hire(baraka)
    elif whose == "left another shop, works nowhere":
        person = User.objects.create_user(full_name="Asha Mfano", phone="0754 000 111")
        with shop_context(shop_b):
            at_b = add_staff(shop=shop_b, user=person, display_name="Asha", started_on=FIRST_DAY, by=None)
            mark_left(at_b, left_on=LAST_DAY, by=None, reason="Amehamia Moshi")
    else:
        person = User.objects.create_user(full_name="Asha Mfano", phone="0754 000 111")
    people = User.objects.count()

    with pytest.raises(ValidationError) as refused:
        add(baraka.shop, phone=cast(str, person.phone))

    assert phone_codes(refused) == ["unique"]
    assert all(not error.params or "full_name" not in error.params for error in refused.value.error_dict["phone"])
    assert User.objects.count() == people


def test_no_phone_on_ongeza_on_the_demo(shop_a: Shop, meneja: StaffMember, settings: Settings) -> None:
    # Every visitor logs in as Meneja: a stranger's real number typed on a worker they added would show to every later
    # visitor (PPL-10). An empty box is no phone, so the add goes through.
    settings.DEMO_SEED = True
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", phone=PHONE, by=meneja)
    assert refused.value.code == "demo.phones_fixed"

    with shop_context(shop_a):
        juma = add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", phone="", by=meneja)
    assert User.objects.get(pk=juma.user_id).phone is None


def test_a_visitors_worker_who_left_is_hired_again_on_the_demo(
    shop_a: Shop, meneja: StaffMember, settings: Settings
) -> None:
    # Every visitor logs in as Meneja: a worker a visitor added, and marked left, can be hired again, as trying the page
    # is the point (PPL-4: A). The seed's people are never marked left there (demo.people_fixed), so none of them can
    # come back as a second job either.
    settings.DEMO_SEED = True
    with shop_context(shop_a):
        juma = add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", started_on=FIRST_DAY, by=meneja)
        mark_left(juma, left_on=LAST_DAY, by=meneja, reason="Amehamia Moshi")

    back = hire(juma, display_name="Juma", by=meneja)

    assert (back.user_id, back.status, back.created_by_id) == (juma.user_id, StaffStatus.ACTIVE, meneja.pk)


@pytest.mark.django_db(transaction=True)
def test_a_phone_taken_at_the_same_moment_answers_as_taken(shop_a: Shop) -> None:
    # Meneja adds Juma with a new phone while Baba adds Hamisi with the same one, in the same second: each check passes,
    # as neither sees the other's save; the database's unique rule waits for the first and refuses the second. The
    # second hears the number is in use, not a server error.
    def the_second_add() -> object:
        return add(shop_a, phone="0754 000 111", full_name="Hamisi Mfano", display_name="Hamisi")

    with transaction.atomic():
        add(shop_a, phone="0754 000 111")
        other, ended = in_another_transaction(the_second_add)
        wait_until_someone_waits_for_me()
    other.join(timeout=5)
    assert not other.is_alive(), "The second add still waits after the first committed."

    refused = ended[0]
    assert isinstance(refused, ValidationError)
    assert {name: [error.code for error in errors] for name, errors in refused.error_dict.items()} == {
        "phone": ["unique"]
    }
    assert not User.objects.filter(full_name="Hamisi Mfano").exists()
