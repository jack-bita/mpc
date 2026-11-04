"""apps/people/tests/test_who_sets_a_pin.py — who may give a person a PIN (AUTH-4; 02 §5; Jack, 4 Nov 2026).

A PIN logs in as the whole person, office pages included, so whoever sets one can act as them. So the rule is the one
for a temporary password (apps/people/tests/test_temporary_password.py), with codes of its own:

    the one setting it                                   the answer
    holds staff.manage on the whole shop, and every
    key this person was given                            the PIN is set
    has no staff.manage, or has it on one side only      403
    sets their own                                       pin.own
    sets an owner's, or a person's who can open the
    admin                                                pin.superuser_only
    this person holds a key they lack                    pin.more_keys
    the system or the superuser, who is nobody's staff   the PIN is set, for anyone

Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from typing import Any
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.pins import hash_pin, pin_matches
from apps.people.services import add_staff, grant_permission, mark_left, set_pin, suspend
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

PIN = "4829"


def job(shop: Shop, name: str) -> StaffMember:
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, by=None)


def set_for(staff: StaffMember, *, by: StaffMember | None) -> None:
    with shop_context(staff.shop_id):
        set_pin(staff, PIN, by=by)


def assert_no_pin(staff: StaffMember) -> None:
    with shop_context(staff.shop_id):
        staff.refresh_from_db()
    assert staff.pin_hash == ""


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager the owner has handed staff.manage, on the whole shop.
    staff = job(shop_a, "Meneja")
    give_role(staff, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(staff, Permission.STAFF_MANAGE, side=None, by=None)
    return staff


@pytest.fixture
def asha(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Asha")
    give_role(staff, RoleTemplate.SELLER, side_a)
    return staff


def test_manager_with_the_key_sets_a_workers_pin(meneja: StaffMember, asha: StaffMember) -> None:
    set_for(asha, by=meneja)

    with shop_context(asha.shop_id):
        asha.refresh_from_db()
    assert pin_matches(PIN, asha.pin_hash)


def test_owner_sets_a_workers_pin(baba: StaffMember, asha: StaffMember) -> None:
    set_for(asha, by=baba)

    with shop_context(asha.shop_id):
        asha.refresh_from_db()
    assert pin_matches(PIN, asha.pin_hash)


def test_setting_a_pin_needs_the_key(shop_a: Shop, side_a: Side, give_role: GiveRole, asha: StaffMember) -> None:
    # A plain manager, whom the owner has handed no staff.manage.
    plain = job(shop_a, "Plain")
    give_role(plain, RoleTemplate.MANAGER, None)
    with pytest.raises(PermissionDenied):
        set_for(asha, by=plain)
    assert_no_pin(asha)


def test_key_on_one_side_is_not_enough(shop_a: Shop, side_a: Side, asha: StaffMember) -> None:
    # A PIN opens the whole person, on every side, so a key for Dawa alone doesn't reach it.
    dawa_only = job(shop_a, "Dawa")
    with shop_context(shop_a):
        grant_permission(dawa_only, Permission.STAFF_MANAGE, side=side_a, by=None)
    with pytest.raises(PermissionDenied):
        set_for(asha, by=dawa_only)
    assert_no_pin(asha)


def test_nobody_sets_their_own_pin(baba: StaffMember, meneja: StaffMember) -> None:
    for person in (baba, meneja):
        with pytest.raises(ValidationError) as refused:
            set_for(person, by=person)
        assert refused.value.code == "pin.own"
        assert_no_pin(person)


def test_nobody_at_the_shop_sets_the_owners_pin(
    baba: StaffMember, meneja: StaffMember, shop_a: Shop, give_role: GiveRole
) -> None:
    # A manager with the key can't; nor can a second owner, as two owners may have fallen out with each other.
    second_owner = job(shop_a, "Mama")
    give_role(second_owner, RoleTemplate.OWNER, None)
    for setter in (meneja, second_owner):
        with pytest.raises(ValidationError) as refused:
            set_for(baba, by=setter)
        assert refused.value.code == "pin.superuser_only"
    assert_no_pin(baba)


def test_a_suspended_owner_is_still_the_owner(baba: StaffMember, meneja: StaffMember) -> None:
    # A suspended person holds no keys, so a manager would otherwise look stronger, and hold their login when they came
    # back (AUTH-6).
    with shop_context(baba.shop_id):
        suspend(baba, by=None, reason="Uchunguzi")
    with pytest.raises(ValidationError) as refused:
        set_for(baba, by=meneja)
    assert refused.value.code == "pin.superuser_only"


def test_nobody_at_the_shop_sets_an_admin_persons_pin(meneja: StaffMember, shop_a: Shop) -> None:
    # Someone who can open the admin stands above every shop's people, so nobody at a shop may act as them.
    person = job(shop_a, "Admin")
    User.objects.filter(pk=person.user_id).update(is_staff=True)
    with pytest.raises(ValidationError) as refused:
        set_for(person, by=meneja)
    assert refused.value.code == "pin.superuser_only"


def test_manager_cannot_set_a_stronger_persons_pin(meneja: StaffMember, shop_a: Shop) -> None:
    # A worker holding a key Meneja lacks: knowing her PIN, he could use that key.
    strong = job(shop_a, "Neema")
    with shop_context(shop_a):
        grant_permission(strong, Permission.PAY_APPROVE, side=None, by=None)
    with pytest.raises(ValidationError) as refused:
        set_for(strong, by=meneja)
    assert refused.value.code == "pin.more_keys"
    assert_no_pin(strong)


def test_someone_who_left_gets_no_pin(meneja: StaffMember, asha: StaffMember) -> None:
    with shop_context(asha.shop_id):
        mark_left(asha, left_on=asha.started_on, by=None, reason="Amehamia mji mwingine")
    with pytest.raises(ValidationError) as refused:
        set_for(asha, by=meneja)
    assert refused.value.code == "staff.left"


def test_the_system_may_set_anyones_pin(baba: StaffMember) -> None:
    # The superuser is nobody's staff, so `by` is None: the one way an owner gets a PIN.
    set_for(baba, by=None)

    with shop_context(baba.shop_id):
        baba.refresh_from_db()
    assert pin_matches(PIN, baba.pin_hash)


def test_who_may_is_asked_before_the_hash(baba: StaffMember, meneja: StaffMember) -> None:
    # A refused try pays for no slow hash: 19 MiB a time.
    with mock.patch("apps.people.services.hash_pin") as hashing, pytest.raises(ValidationError):
        set_for(baba, by=meneja)
    hashing.assert_not_called()


def test_both_jobs_are_locked_lightly_and_in_id_order(meneja: StaffMember, asha: StaffMember) -> None:
    # The two things that keep two requests from waiting for each other for good, pinned in what is sent to PostgreSQL,
    # as for a temporary password. Without a lock on the giver's row, a suspension at this same moment wouldn't be seen.
    with CaptureQueriesContext(connection) as queries:
        set_for(asha, by=meneja)
    [lock] = [query["sql"] for query in queries.captured_queries if "FOR NO KEY UPDATE" in query["sql"]]
    assert 'FROM "people_staffmember"' in lock
    assert 'ORDER BY "people_staffmember"."id" ASC' in lock


def during_the_hash(happening: Callable[[], object]) -> Any:
    # Something happens while the slow hash runs, when no lock is held.
    def hashing(pin: str) -> str:
        happening()
        return hash_pin(pin)

    return mock.patch("apps.people.services.hash_pin", side_effect=hashing)


def test_a_giver_suspended_during_the_hash_sets_nothing(meneja: StaffMember, asha: StaffMember) -> None:
    suspended = during_the_hash(lambda: suspend(meneja, by=None, reason="Uchunguzi"))
    with suspended, pytest.raises(PermissionDenied):
        set_for(asha, by=meneja)
    assert_no_pin(asha)


def test_a_key_given_during_the_hash_counts(baba: StaffMember, meneja: StaffMember, asha: StaffMember) -> None:
    given = during_the_hash(lambda: grant_permission(asha, Permission.PAY_APPROVE, side=None, by=baba))
    with given, pytest.raises(ValidationError) as refused:
        set_for(asha, by=meneja)
    assert refused.value.code == "pin.more_keys"
    assert_no_pin(asha)
