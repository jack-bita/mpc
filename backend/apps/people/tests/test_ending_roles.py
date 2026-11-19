"""apps/people/tests/test_ending_roles.py — a role or an extra key taken away (02 §5, PPL-7).

Taking one away is an edit of its row, never a delete (rule 7): the row stays, marked ended, with who, when and why.
An ended row counts nowhere (test_permissions.py), and the same role or key can be given again later, as a new row.

The first tests check what the database holds to, ending a row by writing its three columns by hand; the rest, what
end_role and end_permission do. Who may end one is test_who_changes_a_worker.py's.
"""

from collections.abc import Callable

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.control.models import EditEvent
from apps.core.models import ChangeOp
from apps.core.permissions import HeldPermissions, Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import PermissionGrant, Role, RoleAssignment, StaffMember
from apps.people.permissions import held_permissions
from apps.people.services import assign_role, copy_role_templates, end_permission, end_role, grant_permission
from apps.shops.models import Shop, Side
from tests.change_log import lines_written
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

pytestmark = pytest.mark.django_db


@pytest.fixture
def seller(shop_a: Shop) -> Role:
    # Shop A's own Seller role, copied from its template: shop_a is a bare Shop row with no roles.
    with shop_context(shop_a):
        return copy_role_templates(shop_a)[RoleTemplate.SELLER]


def given(staff: StaffMember, seller: Role, side: Side) -> tuple[RoleAssignment, PermissionGrant]:
    # One row of each table, given by the system, on the same side: what each test then ends or deletes.
    with shop_context(staff.shop_id):
        role = assign_role(staff, seller, side=side, by=None)
        key = grant_permission(staff, Permission.STOCK_COUNT, side=side, by=None)
    return role, key


def end(row: RoleAssignment | PermissionGrant) -> None:
    # The row ended by the superuser (no one named), as the service will write it: when, and why.
    with shop_context(row.shop_id):
        type(row).objects.filter(pk=row.pk).update(ended_at=timezone.now(), end_reason="Amehamia Vyakula")


def refused(row: RoleAssignment | PermissionGrant, **change: object) -> None:
    # The change, refused by the database. In a savepoint of its own, so the test's transaction goes on after it.
    with shop_context(row.shop_id), pytest.raises(IntegrityError), transaction.atomic():
        type(row).objects.filter(pk=row.pk).update(**change)


def code_of(give: Callable[[], object]) -> str:
    # The code of the one rule a give broke, as full_clean names it: a once rule names no field.
    with pytest.raises(ValidationError) as broken:
        give()
    [error] = broken.value.error_dict["__all__"]
    return str(error.code)


def test_a_role_or_a_key_is_never_deleted(shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role) -> None:
    # Rule 7: nothing links to these rows, so PROTECT never stops a delete, and the edit history's trigger ignores one.
    # The no-delete trigger refuses it, however it is sent: a bulk delete() here, or SQL typed by hand.
    for row in given(staff_a, seller, side_a):
        with shop_context(shop_a), pytest.raises(IntegrityError), transaction.atomic():
            type(row).objects.filter(pk=row.pk).delete()
        with shop_context(shop_a):
            assert type(row).objects.filter(pk=row.pk).exists()


def test_an_end_is_whole_or_not_at_all(shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role) -> None:
    # An end says when and why, so a row is either open, with all three empty, or ended, with a time and a reason. Who
    # ended it may be empty: the superuser, who is nobody's staff. Half an end would leave a row that counts nowhere
    # with no reason anyone could read, or a reason on a row that still counts.
    now = timezone.now()
    for row in given(staff_a, seller, side_a):
        refused(row, ended_at=now)
        refused(row, ended_at=now, end_reason="   ")
        refused(row, end_reason="Amehamia Vyakula")
        refused(row, ended_by=staff_a)
        # Ended by a person, with all three: allowed, as the service will write it.
        with shop_context(shop_a):
            type(row).objects.filter(pk=row.pk).update(ended_at=now, ended_by=staff_a, end_reason="Amehamia Vyakula")


def test_an_ended_role_is_given_again_as_a_new_row(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role
) -> None:
    # The once rules count only rows not ended: Asha's Seller role on Dawa, taken away, can be given to her again, as a
    # new row, and the old one stays as history. Given twice while it counts is still refused.
    role, key = given(staff_a, seller, side_a)
    end(role)
    end(key)
    with shop_context(shop_a):
        again = assign_role(staff_a, seller, side=side_a, by=None)
        key_again = grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=None)
        assert again.pk != role.pk and key_again.pk != key.pk
        assert RoleAssignment.objects.filter(staff=staff_a).count() == 2
        assert PermissionGrant.objects.filter(staff=staff_a).count() == 2
        assert code_of(lambda: assign_role(staff_a, seller, side=side_a, by=None)) == "role.already_given"
        assert (
            code_of(lambda: grant_permission(staff_a, Permission.STOCK_COUNT, side=side_a, by=None))
            == "permission.already_given"
        )


def test_an_ended_role_on_every_side_is_given_again(shop_a: Shop, staff_a: StaffMember, seller: Role) -> None:
    # "Every side" is an empty side, and the once rules keep counting two empty sides as one (nulls_distinct=False):
    # ended, it is given again; open, a second is refused.
    with shop_context(shop_a):
        first = assign_role(staff_a, seller, side=None, by=None)
    end(first)
    with shop_context(shop_a):
        assign_role(staff_a, seller, side=None, by=None)
        assert code_of(lambda: assign_role(staff_a, seller, side=None, by=None)) == "role.already_given"


REASON = "Amehamia Vyakula"


@pytest.fixture
def baba(shop_a: Shop, staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    # The owner, who takes a role away: staff_a2, given the Owner role by the system, as a shop's first owner is.
    give_role(staff_a2, RoleTemplate.OWNER, None)
    return staff_a2


def take_away(row: RoleAssignment | PermissionGrant, *, by: StaffMember | None, reason: str = REASON) -> None:
    with shop_context(row.shop_id):
        if isinstance(row, RoleAssignment):
            end_role(row, reason=reason, by=by)
        else:
            end_permission(row, reason=reason, by=by)


def as_stored(row: RoleAssignment | PermissionGrant) -> RoleAssignment | PermissionGrant:
    with shop_context(row.shop_id):
        return type(row).objects.get(pk=row.pk)


def test_an_end_keeps_who_when_and_why(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role, baba: StaffMember
) -> None:
    # Baba takes Asha's Seller role and her extra key away: each row stays, ended, with who, when and why (02 §5), and
    # from that moment she holds none of it. The reason is kept trimmed, as audit() keeps one.
    before = timezone.now()
    for row in given(staff_a, seller, side_a):
        take_away(row, by=baba, reason="  Amehamia Vyakula ")
        stored = as_stored(row)
        assert (stored.ended_by_id, stored.end_reason) == (baba.pk, REASON)
        assert stored.ended_at is not None and before <= stored.ended_at <= timezone.now()
    with shop_context(shop_a):
        assert held_permissions(staff_a) == HeldPermissions()


def test_the_superuser_ends_one_naming_nobody(shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role) -> None:
    # `by` None: the superuser, who is nobody's staff, as for a suspension. The row says it ended, and why, with no one
    # named, which the rule of a whole end allows.
    for row in given(staff_a, seller, side_a):
        take_away(row, by=None)
        stored = as_stored(row)
        assert stored.ended_at is not None and stored.ended_by_id is None


def test_an_end_asks_why(shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role, baba: StaffMember) -> None:
    # Every end asks why (02 §5): spaces alone are no reason, and nothing is ended.
    for row in given(staff_a, seller, side_a):
        for reason in ("", "   "):
            with pytest.raises(ValidationError) as refused:
                take_away(row, by=baba, reason=reason)
            assert refused.value.code == "staff.reason_required"
        assert as_stored(row).ended_at is None


def test_an_ended_row_is_not_ended_again(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role, baba: StaffMember
) -> None:
    # Ended once, it stays as it was ended: a second end is refused with its code, and who, when and why stay the first.
    role, key = given(staff_a, seller, side_a)
    for row, code in ((role, "role.already_ended"), (key, "permission.already_ended")):
        take_away(row, by=baba)
        first = as_stored(row)
        with pytest.raises(ValidationError) as refused:
            take_away(row, by=None, reason="Tena")
        assert refused.value.code == code
        again = as_stored(row)
        assert (again.ended_at, again.ended_by_id, again.end_reason) == (first.ended_at, baba.pk, REASON)


def test_an_end_writes_the_persons_line(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role, baba: StaffMember
) -> None:
    # Her keys travel on her staff row (SYNC-15), so each end names her job in the change log: her laptop drops the key
    # at its next sync. The role and the key stay on the server, with no line of their own.
    for row in given(staff_a, seller, side_a):
        with shop_context(shop_a), lines_written(shop_a) as written:
            take_away(row, by=baba)
        assert written == [("staff", staff_a.pk, ChangeOp.UPSERT)]


def test_an_end_is_in_the_edit_history(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role, baba: StaffMember
) -> None:
    # The edit history's trigger writes the end, before and after, naming who ended it (ADR-0036): the one place, with
    # the row itself, that keeps it, as an end writes no audit line (PPL-7's card, default).
    role, key = given(staff_a, seller, side_a)
    rows: list[tuple[RoleAssignment | PermissionGrant, str]] = [(role, "role_assignment"), (key, "permission_grant")]
    for row, type_code in rows:
        take_away(row, by=baba)
        with shop_context(shop_a):
            [edit] = EditEvent.objects.filter(subject_type=type_code, subject_id=row.pk)
        assert edit.created_by_id == baba.pk
        assert edit.before == {"ended_at": None, "ended_by_id": None, "end_reason": ""}
        assert edit.after["ended_by_id"] == str(baba.pk)
        assert edit.after["end_reason"] == REASON


@pytest.mark.django_db(transaction=True)
def test_of_two_ends_at_once_the_second_hears_it_ended(
    shop_a: Shop, side_a: Side, staff_a: StaffMember, seller: Role, baba: StaffMember, staff_b: StaffMember
) -> None:
    # Baba and the superuser take Asha's role away in the same second. The first locks her job; the second waits for it,
    # then reads the row as the first left it, and hears it ended: one end, with the first one's who and why.
    role, _key = given(staff_a, seller, side_a)

    def second() -> object:
        with shop_context(shop_a):
            return end_role(role, reason="Tena", by=None)

    with shop_context(shop_a), transaction.atomic():
        end_role(role, reason=REASON, by=baba)
        thread, ended = in_another_transaction(second)
        wait_until_someone_waits_for_me()
    thread.join(timeout=5)
    [refused] = ended
    assert isinstance(refused, ValidationError) and refused.code == "role.already_ended"
    assert as_stored(role).ended_by_id == baba.pk
