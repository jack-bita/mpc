"""apps/people/tests/test_selectors.py — who may act, asked directly, with no request (apps/people/selectors.py;
AUTH-3; ADR-0038).

These rules are shared: a PIN's session asks them too (job_of_pin_session, AUTH-4), and so will AUTH-7's choice of shop,
so what they answer is pinned here, apart from any one login. What each answer becomes on the wire is in
test_staff_session.py and test_device_login.py.

Fake data only: the repo is public (03 §10).
"""

from unittest import mock

import pytest

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.selectors import LoginRefused, check_shop_active, job_of_person
from apps.people.services import add_staff, mark_left, suspend
from apps.shops.models import Shop, ShopStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def person() -> User:
    return User.objects.create_user(full_name="Meneja Mfano", phone="+255712345678")


def give_job(person: User, shop: Shop) -> StaffMember:
    with shop_context(shop):
        return add_staff(shop=shop, user=person, display_name="Meneja", by=None)


def refusal_of(person: User) -> str:
    with pytest.raises(LoginRefused) as refused:
        job_of_person(person)
    return refused.value.code


def test_one_job_is_that_job(person: User, shop_a: Shop) -> None:
    staff = give_job(person, shop_a)
    assert job_of_person(person) == staff


def test_no_job_is_none(person: User) -> None:
    assert job_of_person(person) is None


def test_someone_who_left_has_no_job(person: User, shop_a: Shop) -> None:
    staff = give_job(person, shop_a)
    with shop_context(shop_a):
        mark_left(staff, left_on=staff.started_on, by=None, reason="Moved to another town")
    assert job_of_person(person) is None


def test_a_job_gone_after_the_door_is_no_job(person: User, shop_a: Shop) -> None:
    # The door named a shop, but the job is gone by the next read. It reads as no job: never an error, never a guess.
    with mock.patch("apps.people.selectors.shops_of_person", return_value=[shop_a.pk]):
        assert job_of_person(person) is None


def test_two_shops_are_never_guessed(person: User, shop_a: Shop, shop_b: Shop) -> None:
    give_job(person, shop_a)
    give_job(person, shop_b)
    assert refusal_of(person) == "staff.choose_shop"


def test_a_suspended_person_is_told_so(person: User, shop_a: Shop) -> None:
    staff = give_job(person, shop_a)
    with shop_context(shop_a):
        suspend(staff, by=None, reason="Cash short for two weeks")
    assert refusal_of(person) == "staff.suspended"


def test_a_suspended_shop_is_named_before_the_person(person: User, shop_a: Shop) -> None:
    # Both stopped: the shop's suspension is the one to tell, as lifting the person's own wouldn't let them in.
    staff = give_job(person, shop_a)
    with shop_context(shop_a):
        suspend(staff, by=None, reason="Cash short for two weeks")
    Shop.objects.filter(pk=shop_a.pk).update(status=ShopStatus.SUSPENDED)
    assert refusal_of(person) == "shop.suspended"


def test_a_person_who_must_change_their_password_is_told_so(person: User, shop_a: Shop) -> None:
    # Someone else typed their password, so they must choose their own first (ADR-0038).
    give_job(person, shop_a)
    User.objects.filter(pk=person.pk).update(must_change_password=True)
    person.refresh_from_db()
    assert refusal_of(person) == "password.must_change"


def test_a_suspension_is_named_before_the_mark(person: User, shop_a: Shop) -> None:
    # Both stopped: the suspension is the one to tell, as choosing a new password wouldn't let them in.
    staff = give_job(person, shop_a)
    with shop_context(shop_a):
        suspend(staff, by=None, reason="Cash short for two weeks")
    User.objects.filter(pk=person.pk).update(must_change_password=True)
    person.refresh_from_db()
    assert refusal_of(person) == "staff.suspended"


def test_no_job_is_none_with_the_mark_too(person: User) -> None:
    # The owner's first login may come before their job is added, or the superuser may hold the mark: they are nobody
    # at any shop, so there is no office route to close. The refusal is for a job, and a job they don't have stays None.
    User.objects.filter(pk=person.pk).update(must_change_password=True)
    person.refresh_from_db()
    assert job_of_person(person) is None


def test_a_shop_status_nobody_has_named_is_refused() -> None:
    # Fails closed: a status a later card adds stays refused until that card says otherwise.
    with pytest.raises(LoginRefused) as refused:
        check_shop_active(Shop(status="closing_down"))
    assert refused.value.code == "shop.suspended"
