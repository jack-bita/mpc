"""apps/people/tests/test_who_changes_a_worker.py — who may suspend a person, bring them back or mark them left (PPL-4;
02 §5).

A suspension stops a person working at once, and a leaving is final, so the rule is the one for setting a PIN
(apps/people/tests/test_who_sets_a_pin.py), with codes of its own (the PIN's rule, by default, PPL-4's card):

    the one acting                                       the answer
    holds staff.manage on the whole shop, and every
    key this person was given                            done
    has no staff.manage, or has it on one side only      403
    acts on themselves                                   staff.own
    acts on an owner, or on a person who can open the
    admin                                                staff.superuser_only
    this person holds a key they lack                    staff.more_keys
    the system or the superuser, who is nobody's staff   done, for anyone

Who may is asked once both people's rows are locked, in id order, so it reads them as they are now: of two managers
suspending each other at once, the first wins (test_staff.py, AUTH-8). Each rule is checked for all three actions.

On the demo, where every visitor logs in as Meneja, the people the seed made stay as made (demo.people_fixed); a worker
a visitor added can be changed (Jack, PPL-4: A).

Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from pytest_django import Settings

from apps.control.models import AuditEvent
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, StaffStatus, User
from apps.people.services import add_staff, add_worker, grant_permission, mark_left, suspend, unsuspend
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@dataclass(frozen=True)
class Change:
    # One of the three actions on a person: what the person's status must be before it (`before`, set by the system
    # first, if need be), the action itself, and the status it leaves.
    before: StaffStatus
    act: Callable[[StaffMember, StaffMember | None], object]
    after: StaffStatus


SUSPEND = Change(
    StaffStatus.ACTIVE,
    lambda staff, by: suspend(staff, by=by, reason="Hakuja kazini siku 3"),
    StaffStatus.SUSPENDED,
)
BRING_BACK = Change(
    StaffStatus.SUSPENDED,
    lambda staff, by: unsuspend(staff, by=by, reason="Amerudi kazini"),
    StaffStatus.ACTIVE,
)
LEAVE = Change(
    StaffStatus.ACTIVE,
    lambda staff, by: mark_left(staff, left_on=staff.started_on, by=by, reason="Amehamia Moshi"),
    StaffStatus.LEFT,
)
EACH_CHANGE = pytest.mark.parametrize(
    "change",
    [pytest.param(SUSPEND, id="suspend"), pytest.param(BRING_BACK, id="bring back"), pytest.param(LEAVE, id="leave")],
)


def job(shop: Shop, name: str) -> StaffMember:
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, by=None)


def ready(staff: StaffMember, change: Change) -> None:
    # Put the person in the status the action starts from, as the system: a person is brought back only once suspended.
    if change.before == StaffStatus.SUSPENDED:
        with shop_context(staff.shop_id):
            suspend(staff, by=None, reason="Uchunguzi")


def do(change: Change, staff: StaffMember, *, by: StaffMember | None) -> None:
    with shop_context(staff.shop_id):
        change.act(staff, by)


def status_of(staff: StaffMember) -> StaffStatus:
    with shop_context(staff.shop_id):
        return StaffStatus(StaffMember.objects.get(pk=staff.pk).status)


def lines_about(staff: StaffMember) -> int:
    # How many audit lines name this person: a refused action writes none.
    with shop_context(staff.shop_id):
        return AuditEvent.objects.filter(subject_type="staff", subject_id=staff.pk).count()


def assert_unchanged(staff: StaffMember, change: Change, lines: int) -> None:
    assert status_of(staff) == change.before
    assert lines_about(staff) == lines


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


@EACH_CHANGE
def test_manager_with_the_key_changes_a_worker(change: Change, meneja: StaffMember, asha: StaffMember) -> None:
    ready(asha, change)

    do(change, asha, by=meneja)

    assert status_of(asha) == change.after


@EACH_CHANGE
def test_owner_changes_a_worker(change: Change, baba: StaffMember, asha: StaffMember) -> None:
    ready(asha, change)

    do(change, asha, by=baba)

    assert status_of(asha) == change.after


@EACH_CHANGE
def test_changing_a_worker_needs_the_key(change: Change, shop_a: Shop, give_role: GiveRole, asha: StaffMember) -> None:
    # A plain manager, whom the owner has handed no staff.manage: today he could suspend anyone, the owner included.
    plain = job(shop_a, "Plain")
    give_role(plain, RoleTemplate.MANAGER, None)
    ready(asha, change)
    lines = lines_about(asha)

    with pytest.raises(PermissionDenied):
        do(change, asha, by=plain)

    assert_unchanged(asha, change, lines)


@EACH_CHANGE
def test_key_on_one_side_is_not_enough(change: Change, shop_a: Shop, side_a: Side, asha: StaffMember) -> None:
    # A person's job belongs to the whole shop, on every side, so a key for Dawa alone doesn't reach it.
    dawa_only = job(shop_a, "Dawa")
    with shop_context(shop_a):
        grant_permission(dawa_only, Permission.STAFF_MANAGE, side=side_a, by=None)
    ready(asha, change)
    lines = lines_about(asha)

    with pytest.raises(PermissionDenied):
        do(change, asha, by=dawa_only)

    assert_unchanged(asha, change, lines)


@pytest.mark.parametrize("change", [pytest.param(SUSPEND, id="suspend"), pytest.param(LEAVE, id="leave")])
def test_nobody_changes_themselves(change: Change, baba: StaffMember, meneja: StaffMember) -> None:
    # A manager who suspended himself, or marked himself left, would lock himself out by a slip of the finger.
    for person in (baba, meneja):
        with pytest.raises(ValidationError) as refused:
            do(change, person, by=person)
        assert refused.value.code == "staff.own"
        assert status_of(person) == change.before


def test_a_suspended_person_cannot_bring_themselves_back(meneja: StaffMember) -> None:
    # Suspended, they hold no keys at all (02 §5), so the key is missing before anything else is asked.
    ready(meneja, BRING_BACK)

    with pytest.raises(PermissionDenied):
        do(BRING_BACK, meneja, by=meneja)

    assert status_of(meneja) == StaffStatus.SUSPENDED


@EACH_CHANGE
def test_nobody_at_the_shop_changes_the_owner(
    change: Change, baba: StaffMember, meneja: StaffMember, shop_a: Shop, give_role: GiveRole
) -> None:
    # A manager with the key can't; nor can a second owner, as two owners may have fallen out with each other.
    second_owner = job(shop_a, "Mama")
    give_role(second_owner, RoleTemplate.OWNER, None)
    ready(baba, change)
    lines = lines_about(baba)

    for acting in (meneja, second_owner):
        with pytest.raises(ValidationError) as refused:
            do(change, baba, by=acting)
        assert refused.value.code == "staff.superuser_only"

    assert_unchanged(baba, change, lines)


def test_nobody_at_the_shop_changes_an_admin_person(meneja: StaffMember, shop_a: Shop) -> None:
    # Someone who can open the admin stands above every shop's people.
    person = job(shop_a, "Admin")
    User.objects.filter(pk=person.user_id).update(is_staff=True)

    with pytest.raises(ValidationError) as refused:
        do(SUSPEND, person, by=meneja)

    assert refused.value.code == "staff.superuser_only"
    assert status_of(person) == StaffStatus.ACTIVE


@EACH_CHANGE
def test_manager_cannot_change_a_stronger_person(change: Change, meneja: StaffMember, shop_a: Shop) -> None:
    # Neema holds a key Meneja lacks, the owner's pay approval: whoever may stop her may hold back what that key does.
    neema = job(shop_a, "Neema")
    with shop_context(shop_a):
        grant_permission(neema, Permission.PAY_APPROVE, side=None, by=None)
    ready(neema, change)
    lines = lines_about(neema)

    with pytest.raises(ValidationError) as refused:
        do(change, neema, by=meneja)

    assert refused.value.code == "staff.more_keys"
    assert_unchanged(neema, change, lines)


@EACH_CHANGE
def test_the_system_may_change_anyone(change: Change, baba: StaffMember) -> None:
    # The superuser is nobody's staff, so `by` is None: the one way an owner is suspended or marked left.
    ready(baba, change)

    do(change, baba, by=None)

    assert status_of(baba) == change.after


@EACH_CHANGE
def test_both_jobs_are_locked_lightly_and_in_id_order(change: Change, meneja: StaffMember, asha: StaffMember) -> None:
    # Lessons 2 and 3, pinned in what is sent to PostgreSQL: both rows are locked before who may is asked, so the
    # answer reads them as they are now; light locks (no key), in one order, so two managers acting on each other take
    # turns and never wait for each other in a circle.
    ready(asha, change)

    with CaptureQueriesContext(connection) as queries:
        do(change, asha, by=meneja)

    [lock] = [query["sql"] for query in queries.captured_queries if "FOR NO KEY UPDATE" in query["sql"]]
    assert 'FROM "people_staffmember"' in lock
    assert 'ORDER BY "people_staffmember"."id" ASC' in lock


@EACH_CHANGE
def test_demo_people_fixed(
    change: Change, shop_a: Shop, meneja: StaffMember, asha: StaffMember, settings: Settings
) -> None:
    # On the demo every visitor logs in as Meneja, who holds staff.manage there (apps/demo/services.py). A visitor who
    # suspended Asha would take her off every other visitor's PIN tiles until the next morning's seed. The seed's people
    # are those the system made, with no one named as their adder, as Asha here.
    settings.DEMO_SEED = True
    ready(asha, change)
    lines = lines_about(asha)

    with pytest.raises(ValidationError) as refused:
        do(change, asha, by=meneja)

    assert refused.value.code == "demo.people_fixed"
    assert_unchanged(asha, change, lines)

    # A worker the visitor added on the page, through Meneja's login: trying the page is the point.
    with shop_context(shop_a):
        juma = add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", by=meneja)
    ready(juma, change)
    do(change, juma, by=meneja)
    assert status_of(juma) == change.after


def test_the_system_still_changes_the_seeds_people_on_the_demo(asha: StaffMember, settings: Settings) -> None:
    # The rule stops people, not the system, as for the logins (check_logins_may_change).
    settings.DEMO_SEED = True

    do(SUSPEND, asha, by=None)

    assert status_of(asha) == StaffStatus.SUSPENDED
