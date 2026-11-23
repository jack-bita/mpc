"""apps/people/tests/test_who_changes_a_worker.py — who may suspend a person, bring them back, mark them left, fix
their details, take a role or a key away from them, or set or take off their photo (PPL-4, PPL-10, PPL-7, PPL-9; 02 §5).

A suspension stops a person working at once, and a leaving is final; a fix may change a person's phone, which is a
login name, so whoever sets it could then set a temporary password and log in as them. So the rule is the one for
setting a PIN (apps/people/tests/test_who_sets_a_pin.py), with codes of its own (the PIN's rule, by default, PPL-4's and
PPL-10's cards):

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
suspending each other at once, the first wins (test_staff.py, AUTH-8). Most rules are checked for all four actions:
acting on oneself, for the three that can be tried on oneself (bringing oneself back is refused sooner, as a suspended
person holds no keys), and acting on an admin person, for a suspension alone. Each action that goes through writes its
one audit line.

Taking a role or a key away follows the same rule (Jack, PPL-7: A), with one more: a worker who left keeps theirs, even
from the superuser, as history.

Setting a photo and taking one off follow the same rule too (Jack, PPL-9), for a person at the shop: a photo is added by
someone, so the superuser, who is nobody's staff, has no way to yet (04 §20, item 31).

On the demo, where every visitor logs in as Meneja, the people the seed made stay as made (demo.people_fixed); a worker
a visitor added can be changed (Jack, PPL-4: A), but no photo is kept there at all (test_worker_photo.py).

Fake data only: the repo is public (03 §10).
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from pytest_django import Settings

from apps.control.models import AuditEvent
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import PermissionGrant, Role, RoleAssignment, StaffMember, StaffStatus, User
from apps.people.services import (
    add_staff,
    add_worker,
    assign_role,
    change_worker,
    end_permission,
    end_role,
    grant_permission,
    mark_left,
    remove_worker_photo,
    set_worker_photo,
    suspend,
    unsuspend,
)
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@dataclass(frozen=True)
class Change:
    # One of the four actions on a person: what the person's status must be before it (`before`, set by the system
    # first, if need be), the action itself, and the status it leaves. A fix leaves the status as it was: what proves it
    # went through is its audit line, which every action writes (assert_done).
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
# A fix of the worker's job title, from the copy the page read: none of these actions moves the version on, so the
# fixture's copy is still the one in the database.
FIX = Change(
    StaffStatus.ACTIVE,
    lambda staff, by: change_worker(staff, version=staff.version, reason="Alikosewa kazi", by=by, job_title="Fundi"),
    StaffStatus.ACTIVE,
)
EACH_CHANGE = pytest.mark.parametrize(
    "change",
    [
        pytest.param(SUSPEND, id="suspend"),
        pytest.param(BRING_BACK, id="bring back"),
        pytest.param(LEAVE, id="leave"),
        pytest.param(FIX, id="fix"),
    ],
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


def assert_done(staff: StaffMember, change: Change, lines: int) -> None:
    # The status it leaves, and its one audit line, with who and why (T3).
    assert status_of(staff) == change.after
    assert lines_about(staff) == lines + 1


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
    lines = lines_about(asha)

    do(change, asha, by=meneja)

    assert_done(asha, change, lines)


@EACH_CHANGE
def test_owner_changes_a_worker(change: Change, baba: StaffMember, asha: StaffMember) -> None:
    ready(asha, change)
    lines = lines_about(asha)

    do(change, asha, by=baba)

    assert_done(asha, change, lines)


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


@pytest.mark.parametrize(
    "change", [pytest.param(SUSPEND, id="suspend"), pytest.param(LEAVE, id="leave"), pytest.param(FIX, id="fix")]
)
def test_nobody_changes_themselves(change: Change, baba: StaffMember, meneja: StaffMember) -> None:
    # A manager who suspended himself, or marked himself left, would lock himself out by a slip of the finger. One who
    # put his own phone on his job could set himself a temporary password with no current one: he asks the owner.
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
    # The superuser is nobody's staff, so `by` is None: the one way an owner is suspended, marked left or fixed.
    ready(baba, change)
    lines = lines_about(baba)

    do(change, baba, by=None)

    assert_done(baba, change, lines)


@EACH_CHANGE
def test_both_jobs_are_locked_lightly_and_in_id_order(change: Change, meneja: StaffMember, asha: StaffMember) -> None:
    # Lessons 2 and 3, pinned in what is sent to PostgreSQL: both rows are locked before who may is asked, so the
    # answer reads them as they are now; light locks (no key), in one order, so two managers acting on each other take
    # turns and never wait for each other in a circle. The first lock: a fix then locks the job again inside editing(),
    # which this transaction already holds, and the person after the jobs, every one of them lightly. The shop's change
    # counter, which a status change takes for its laptops' line, is locked whole, as it must be (SYNC-1).
    ready(asha, change)

    with CaptureQueriesContext(connection) as queries:
        do(change, asha, by=meneja)

    locks = [query["sql"] for query in queries.captured_queries if re.search(r"FOR (NO KEY )?UPDATE", query["sql"])]
    people_locks = [lock for lock in locks if re.search(r'FROM "people_(staffmember|user)"', lock)]
    assert all("FOR NO KEY UPDATE" in lock for lock in people_locks)
    if change is FIX:
        # A fix changes the person too (their name, their phone), so the person is locked after the jobs: two managers
        # of two shops fixing one person's name take turns, and each audit line's "before" is true (change_worker).
        assert any('FROM "people_user"' in lock for lock in people_locks)
    lock = locks[0]
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
    lines = lines_about(juma)
    do(change, juma, by=meneja)
    assert_done(juma, change, lines)


def test_the_system_still_changes_the_seeds_people_on_the_demo(asha: StaffMember, settings: Settings) -> None:
    # The rule stops people, not the system, as for the logins (check_logins_may_change).
    settings.DEMO_SEED = True

    do(SUSPEND, asha, by=None)

    assert status_of(asha) == StaffStatus.SUSPENDED


# Taking a role or a key away (PPL-7): the rule of Simamisha, as for the four actions above (Jack: A). An end changes no
# status and writes no audit line: what proves it is the row, ended or still open.


@dataclass(frozen=True)
class TakeAway:
    # One of the two ends: what it takes away (a row given to the person by the system first), and the end itself.
    give: Callable[[StaffMember], RoleAssignment | PermissionGrant]
    end: Callable[[RoleAssignment | PermissionGrant, StaffMember | None], object]


def a_role(staff: StaffMember) -> RoleAssignment:
    # The Worker role on every side, which every manager here holds the keys of.
    with shop_context(staff.shop_id):
        return assign_role(staff, Role.objects.get(template=RoleTemplate.WORKER), side=None, by=None)


def a_key(staff: StaffMember) -> PermissionGrant:
    with shop_context(staff.shop_id):
        return grant_permission(staff, Permission.STOCK_COUNT, side=None, by=None)


def _end_role(row: RoleAssignment | PermissionGrant, by: StaffMember | None) -> object:
    return end_role(cast(RoleAssignment, row), reason="Amehamia Vyakula", by=by)


def _end_key(row: RoleAssignment | PermissionGrant, by: StaffMember | None) -> object:
    return end_permission(cast(PermissionGrant, row), reason="Amehamia Vyakula", by=by)


END_ROLE = TakeAway(a_role, _end_role)
END_KEY = TakeAway(a_key, _end_key)
EACH_END = pytest.mark.parametrize("take_away", [pytest.param(END_ROLE, id="role"), pytest.param(END_KEY, id="key")])


def end(take_away: TakeAway, row: RoleAssignment | PermissionGrant, *, by: StaffMember | None) -> None:
    with shop_context(row.shop_id):
        take_away.end(row, by)


def is_ended(row: RoleAssignment | PermissionGrant) -> bool:
    with shop_context(row.shop_id):
        return type(row).objects.get(pk=row.pk).ended_at is not None


def code_of_ending(take_away: TakeAway, row: RoleAssignment | PermissionGrant, *, by: StaffMember | None) -> str:
    # The refusal's code, and the row still open: a refused end changes nothing.
    with pytest.raises(ValidationError) as refused:
        end(take_away, row, by=by)
    assert not is_ended(row)
    return str(refused.value.code)


@EACH_END
def test_manager_or_owner_with_the_key_takes_one_away(
    take_away: TakeAway, meneja: StaffMember, baba: StaffMember, asha: StaffMember
) -> None:
    for acting in (meneja, baba):
        row = take_away.give(asha)
        end(take_away, row, by=acting)
        assert is_ended(row)


@EACH_END
def test_taking_one_away_needs_the_key_on_the_whole_shop(
    take_away: TakeAway, shop_a: Shop, side_a: Side, give_role: GiveRole, asha: StaffMember
) -> None:
    # A plain manager, handed no staff.manage; and one handed it for Dawa alone, as a person's job belongs to the whole
    # shop.
    plain = job(shop_a, "Plain")
    give_role(plain, RoleTemplate.MANAGER, None)
    dawa_only = job(shop_a, "Dawa")
    with shop_context(shop_a):
        grant_permission(dawa_only, Permission.STAFF_MANAGE, side=side_a, by=None)
    row = take_away.give(asha)

    for acting in (plain, dawa_only):
        with pytest.raises(PermissionDenied):
            end(take_away, row, by=acting)
    assert not is_ended(row)


@EACH_END
def test_nobody_takes_their_own_away(take_away: TakeAway, meneja: StaffMember) -> None:
    # A manager who took away his own role by a slip of the finger would lock himself out.
    assert code_of_ending(take_away, take_away.give(meneja), by=meneja) == "staff.own"


@EACH_END
def test_nobody_at_the_shop_takes_the_owners_away(
    take_away: TakeAway, baba: StaffMember, meneja: StaffMember, shop_a: Shop, give_role: GiveRole
) -> None:
    # Not a manager handed staff.manage, so he can't take the Owner's role away; nor a second owner. The Owner role
    # itself included: the superuser's alone, to take away as to give (Jack: A).
    second_owner = job(shop_a, "Mama")
    give_role(second_owner, RoleTemplate.OWNER, None)
    with shop_context(shop_a):
        [owner_role] = RoleAssignment.objects.filter(staff=baba)
    row = take_away.give(baba)
    for acting in (meneja, second_owner):
        assert code_of_ending(take_away, row, by=acting) == "staff.superuser_only"
        assert code_of_ending(END_ROLE, owner_role, by=acting) == "staff.superuser_only"


@EACH_END
def test_nobody_at_the_shop_takes_an_admin_persons_away(take_away: TakeAway, meneja: StaffMember, shop_a: Shop) -> None:
    person = job(shop_a, "Admin")
    User.objects.filter(pk=person.user_id).update(is_staff=True)

    assert code_of_ending(take_away, take_away.give(person), by=meneja) == "staff.superuser_only"


@EACH_END
def test_manager_cannot_take_from_a_stronger_person(take_away: TakeAway, meneja: StaffMember, shop_a: Shop) -> None:
    # Neema holds the owner's pay approval, which Meneja lacks: whoever may weaken her may hold back what it does.
    neema = job(shop_a, "Neema")
    with shop_context(shop_a):
        grant_permission(neema, Permission.PAY_APPROVE, side=None, by=None)

    assert code_of_ending(take_away, take_away.give(neema), by=meneja) == "staff.more_keys"


@EACH_END
def test_a_worker_who_left_keeps_theirs(take_away: TakeAway, meneja: StaffMember, asha: StaffMember) -> None:
    # As history, even for the superuser (02 §5): their job is over, so an end would change nothing they may do.
    row = take_away.give(asha)
    do(LEAVE, asha, by=None)

    for acting in (meneja, None):
        assert code_of_ending(take_away, row, by=acting) == "staff.left"


@EACH_END
def test_a_suspended_worker_may_lose_one(take_away: TakeAway, meneja: StaffMember, asha: StaffMember) -> None:
    # Suspended, she holds nothing now, but would hold it all once brought back: so it may be taken away meanwhile.
    row = take_away.give(asha)
    do(SUSPEND, asha, by=None)

    end(take_away, row, by=meneja)

    assert is_ended(row)


@EACH_END
def test_the_superuser_takes_anyones_away(take_away: TakeAway, baba: StaffMember) -> None:
    # `by` None: the one way an owner loses a role or a key, their Owner role included.
    with shop_context(baba.shop_id):
        [owner_role] = RoleAssignment.objects.filter(staff=baba)
    row = take_away.give(baba)

    end(take_away, row, by=None)
    end(END_ROLE, owner_role, by=None)

    assert is_ended(row) and is_ended(owner_role)


@EACH_END
def test_an_end_locks_both_jobs_then_the_row(take_away: TakeAway, meneja: StaffMember, asha: StaffMember) -> None:
    # The card's Watch out, pinned in what is sent to PostgreSQL: both jobs first, lightly and in id order, as every
    # change of a person locks them (_locked_for_a_change), then the row being ended. Two managers acting on each other
    # and on each other's rows then take turns, and never wait for each other in a circle.
    row = take_away.give(asha)

    with CaptureQueriesContext(connection) as queries:
        end(take_away, row, by=meneja)

    locks = [query["sql"] for query in queries.captured_queries if re.search(r"FOR (NO KEY )?UPDATE", query["sql"])]
    assert 'FROM "people_staffmember"' in locks[0]
    assert 'ORDER BY "people_staffmember"."id" ASC' in locks[0] and "FOR NO KEY UPDATE" in locks[0]
    assert f'FROM "{row._meta.db_table}"' in locks[1]


@EACH_END
def test_demo_people_keep_their_roles_and_keys(
    take_away: TakeAway, shop_a: Shop, meneja: StaffMember, asha: StaffMember, settings: Settings
) -> None:
    # A visitor who took Meneja's Manager role away would stop every tap until the next reset (OPS-3): the seed's people
    # keep theirs. A worker the visitor added may lose one.
    settings.DEMO_SEED = True
    assert code_of_ending(take_away, take_away.give(asha), by=meneja) == "demo.people_fixed"

    with shop_context(shop_a):
        juma = add_worker(shop=shop_a, full_name="Juma Mfano", display_name="Juma", by=meneja)
    row = take_away.give(juma)
    end(take_away, row, by=meneja)
    assert is_ended(row)


# A worker's photo (PPL-9): set, or taken off. Neither changes a status or writes an audit line: what proves each is
# which photo the job shows after it.

# The first bytes every JPEG starts with, and some of our own (CTRL-3).
FACE = b"\xff\xd8\xff" + b"a made-up photo"


def _set_photo(staff: StaffMember, by: StaffMember) -> object:
    return set_worker_photo(staff, photo_id=uuid.uuid7(), content=FACE, by=by)


def _take_photo_off(staff: StaffMember, by: StaffMember) -> object:
    # The photo shown now, as the page names it; any id for a person with none, whom a refusal never gets to ask about.
    return remove_worker_photo(staff, photo_id=shown(staff) or uuid.uuid7(), reason="Hataki picha", by=by)


PhotoAct = Callable[[StaffMember, StaffMember], object]
EACH_PHOTO_ACT = pytest.mark.parametrize(
    "act", [pytest.param(_set_photo, id="set"), pytest.param(_take_photo_off, id="take off")]
)


@pytest.fixture
def mama(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A second owner.
    staff = job(shop_a, "Mama")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def shown(staff: StaffMember) -> uuid.UUID | None:
    with shop_context(staff.shop_id):
        return StaffMember.objects.get(pk=staff.pk).photo_id


def with_a_photo(staff: StaffMember, *, by: StaffMember) -> StaffMember:
    # The person as they are once a photo is there, so a refused removal has one to leave alone.
    with shop_context(staff.shop_id):
        return set_worker_photo(staff, photo_id=uuid.uuid7(), content=FACE, by=by)


def photo_act(act: PhotoAct, staff: StaffMember, *, by: StaffMember) -> None:
    with shop_context(staff.shop_id):
        act(staff, by)


def code_of_photo_act(act: PhotoAct, staff: StaffMember, *, by: StaffMember) -> str:
    # The refusal's code, and the photo as it was: a refused act changes nothing.
    before = shown(staff)
    with pytest.raises(ValidationError) as refused:
        photo_act(act, staff, by=by)
    assert shown(staff) == before
    return str(refused.value.code)


@EACH_PHOTO_ACT
def test_manager_or_owner_with_the_key_changes_a_photo(
    act: PhotoAct, meneja: StaffMember, baba: StaffMember, asha: StaffMember
) -> None:
    for acting in (meneja, baba):
        before = with_a_photo(asha, by=baba).photo_id
        photo_act(act, asha, by=acting)
        assert shown(asha) != before
        assert (shown(asha) is None) == (act is _take_photo_off)


@EACH_PHOTO_ACT
def test_changing_a_photo_needs_the_key_on_the_whole_shop(
    act: PhotoAct, shop_a: Shop, side_a: Side, give_role: GiveRole, baba: StaffMember, asha: StaffMember
) -> None:
    # A plain manager, handed no staff.manage; and one handed it for Dawa alone.
    plain = job(shop_a, "Plain")
    give_role(plain, RoleTemplate.MANAGER, None)
    dawa_only = job(shop_a, "Dawa")
    with shop_context(shop_a):
        grant_permission(dawa_only, Permission.STAFF_MANAGE, side=side_a, by=None)
    before = with_a_photo(asha, by=baba).photo_id

    for acting in (plain, dawa_only):
        with pytest.raises(PermissionDenied):
            photo_act(act, asha, by=acting)
    assert shown(asha) == before


@EACH_PHOTO_ACT
def test_nobody_changes_their_own_photo(act: PhotoAct, meneja: StaffMember, baba: StaffMember) -> None:
    with_a_photo(meneja, by=baba)

    for person in (meneja, baba):
        assert code_of_photo_act(act, person, by=person) == "staff.own"


@EACH_PHOTO_ACT
def test_nobody_at_the_shop_changes_the_owners_photo(
    act: PhotoAct, baba: StaffMember, mama: StaffMember, meneja: StaffMember
) -> None:
    for acting in (meneja, mama):
        assert code_of_photo_act(act, baba, by=acting) == "staff.superuser_only"


@EACH_PHOTO_ACT
def test_nobody_at_the_shop_changes_an_admin_persons_photo(act: PhotoAct, meneja: StaffMember, shop_a: Shop) -> None:
    person = job(shop_a, "Admin")
    User.objects.filter(pk=person.user_id).update(is_staff=True)

    assert code_of_photo_act(act, person, by=meneja) == "staff.superuser_only"


@EACH_PHOTO_ACT
def test_manager_cannot_change_a_stronger_persons_photo(
    act: PhotoAct, meneja: StaffMember, baba: StaffMember, shop_a: Shop
) -> None:
    neema = job(shop_a, "Neema")
    with shop_context(shop_a):
        grant_permission(neema, Permission.PAY_APPROVE, side=None, by=None)
    with_a_photo(neema, by=baba)

    assert code_of_photo_act(act, neema, by=meneja) == "staff.more_keys"


@EACH_PHOTO_ACT
def test_a_worker_who_left_keeps_their_photo_as_it_was(
    act: PhotoAct, meneja: StaffMember, baba: StaffMember, asha: StaffMember
) -> None:
    with_a_photo(asha, by=baba)
    do(LEAVE, asha, by=None)

    assert code_of_photo_act(act, asha, by=meneja) == "staff.left"


@EACH_PHOTO_ACT
def test_a_suspended_workers_photo_may_change(
    act: PhotoAct, meneja: StaffMember, baba: StaffMember, asha: StaffMember
) -> None:
    before = with_a_photo(asha, by=baba).photo_id
    do(SUSPEND, asha, by=None)

    photo_act(act, asha, by=meneja)

    assert shown(asha) != before


@EACH_PHOTO_ACT
def test_a_photo_act_locks_both_jobs_first(
    act: PhotoAct, meneja: StaffMember, baba: StaffMember, asha: StaffMember
) -> None:
    # As every change of a person: both jobs first, lightly and in id order, and only then the photos' rows, so two
    # managers setting one worker's photo at once take turns, and the second finds the first's photo to replace.
    with_a_photo(asha, by=baba)

    with CaptureQueriesContext(connection) as queries:
        photo_act(act, asha, by=meneja)

    locks = [query["sql"] for query in queries.captured_queries if re.search(r"FOR (NO KEY )?UPDATE", query["sql"])]
    assert 'FROM "people_staffmember"' in locks[0]
    assert 'ORDER BY "people_staffmember"."id" ASC' in locks[0] and "FOR NO KEY UPDATE" in locks[0]
    assert all('FROM "control_attachment"' in lock for lock in locks[1:])


def test_the_seeds_people_keep_their_photo_on_the_demo(
    meneja: StaffMember, baba: StaffMember, asha: StaffMember, settings: Settings
) -> None:
    # Taking one off is refused there as any change of the seed's people is; setting one is refused for everyone
    # (demo.photos_fixed, test_worker_photo.py).
    with_a_photo(asha, by=baba)
    settings.DEMO_SEED = True

    assert code_of_photo_act(_take_photo_off, asha, by=meneja) == "demo.people_fixed"
