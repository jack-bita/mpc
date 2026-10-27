"""apps/people/tests/test_staff.py — the rules of a staff member: a person's job at one shop (02 §5, D12).

One person (a User) can hold a job in several shops, and each job is its own row, with its own nickname,
status and PIN. A job is never deleted: a worker who leaves keeps their row, and one who comes back gets
a new one, so the old row keeps its history (old sales, attendance):

    shop      person      nickname   status
    MFANO     Asha Demo   Asha       left      <- her first job, kept for its history
    MFANO     Asha Demo   Asha       active    <- she came back
    JINGINE   Asha Demo   Asha       active    <- the same person, in another shop

The status moves active ⇄ suspended → left, and left is final. Suspending someone or marking them as left
needs a reason (rule 7); CTRL-2 will write it to the audit trail.

StaffMember is the first real ShopScoped table (CORE-2). The services create rows and check the rules
through the guarded `objects`, so every test works inside `shop_context(shop)`, as a visit will.
`by=None` means the change was made by the system or the superuser, who is nobody's staff.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, StaffStatus, User
from apps.people.services import add_staff, mark_left, set_pin, suspend, unsuspend
from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

# Fake data only: the repo is public (03 §10). Dates in the past: a leaving date can't be in the future.
START = date(2026, 3, 2)


@pytest.fixture
def asha() -> User:
    # People are created only through create_user: it cleans and checks every field first (PPL-1).
    return User.objects.create_user(full_name="Asha Demo")


@pytest.fixture
def other_asha() -> User:
    # A second person with the same first name: the case the nickname rule is for.
    return User.objects.create_user(full_name="Asha Mfano")


@pytest.fixture
def juma() -> User:
    return User.objects.create_user(full_name="Juma Demo")


def test_one_user_staff_in_two_shops(asha: User, shop_a: Shop, shop_b: Shop) -> None:
    # D12: one person is one User, with a job in each shop. Each job is its own row.
    with shop_context(shop_a):
        in_a = add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
    with shop_context(shop_b):
        in_b = add_staff(shop=shop_b, user=asha, display_name="Asha", by=None)

    assert in_a.pk != in_b.pk
    assert in_a.user_id == in_b.user_id == asha.pk
    # Each shop sees only its own job: the guard (CORE-2) at work.
    with shop_context(shop_a):
        assert list(StaffMember.objects.filter(user=asha)) == [in_a]


def test_same_person_twice_in_one_shop_refused(asha: User, shop_a: Shop) -> None:
    with shop_context(shop_a):
        add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
        # Another nickname, so only the one-job-per-shop rule is broken.
        with pytest.raises(ValidationError) as refused:
            add_staff(shop=shop_a, user=asha, display_name="Asha K", by=None)

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["staff.already_member"]


def test_rehired_after_leaving_gets_a_new_row(asha: User, shop_a: Shop) -> None:
    # Her first job is never reopened: its history stays as it was, and the new job has its own start.
    with shop_context(shop_a):
        first = add_staff(shop=shop_a, user=asha, display_name="Asha", started_on=START, by=None)
        mark_left(first, left_on=date(2026, 6, 15), by=None, reason="Moved to another town")
        second = add_staff(shop=shop_a, user=asha, display_name="Asha", started_on=date(2026, 9, 1), by=None)

        statuses = {row.pk: row.status for row in StaffMember.objects.filter(user=asha)}

    assert statuses == {first.pk: StaffStatus.LEFT, second.pk: StaffStatus.ACTIVE}


def test_nickname_taken_in_shop_refused(asha: User, other_asha: User, shop_a: Shop) -> None:
    # The login screen and the receipts name staff by nickname, so two current staff of one shop can't
    # share one, in any letter case: the second Asha becomes "Asha M".
    with shop_context(shop_a):
        add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
        with pytest.raises(ValidationError) as refused:
            add_staff(shop=shop_a, user=other_asha, display_name="asha", by=None)

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["staff.display_name_taken"]


def test_nickname_free_in_another_shop_and_after_leaving(
    asha: User, other_asha: User, shop_a: Shop, shop_b: Shop
) -> None:
    with shop_context(shop_a):
        first = add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
    # Another shop has its own staff list.
    with shop_context(shop_b):
        add_staff(shop=shop_b, user=other_asha, display_name="Asha", by=None)
    # A person who left is no longer on the login screen, so her nickname is free again.
    with shop_context(shop_a):
        mark_left(first, left_on=first.started_on, by=None, reason="Left on her first day")
        second = add_staff(shop=shop_a, user=other_asha, display_name="Asha", by=None)

    assert second.display_name == "Asha"


def test_new_staff_starts_active_today(asha: User, shop_a: Shop, monkeypatch: pytest.MonkeyPatch) -> None:
    # The clock says 22:30 UTC on 1 March: in Arusha (UTC+3) it is already 01:30 on 2 March. The start
    # date is the shop's date (02 §1: business dates are in shop time), so 2 March; the server's UTC
    # date would say 1 March. At this hour the two differ, so the test can tell them apart.
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 3, 1, 22, 30, tzinfo=UTC))
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", job_title="Seller", by=None)
        staff.refresh_from_db()

    assert staff.started_on == date(2026, 3, 2)
    assert staff.status == StaffStatus.ACTIVE
    assert staff.left_on is None
    # No PIN yet: set_pin gives one (test_pins.py).
    assert staff.pin_hash == ""
    assert staff.pin_changed_at is None


def test_suspend_and_bring_back(asha: User, shop_a: Shop) -> None:
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
        staff = suspend(staff, by=None, reason="Late five times this month")
        assert staff.status == StaffStatus.SUSPENDED

        staff = unsuspend(staff, by=None, reason="The week is over")
        # Read it back from the database: this is what was really stored.
        staff.refresh_from_db()

    assert staff.status == StaffStatus.ACTIVE


def test_left_is_final(asha: User, shop_a: Shop) -> None:
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
        mark_left(staff, left_on=staff.started_on, by=None, reason="Moved to another town")

        # `staff` in memory still says active. Each service reads the row again from the database
        # before changing it, so the stored `left` is what counts, as it would be for a second manager
        # whose screen still shows Asha as active.
        with pytest.raises(ValidationError) as suspending:
            suspend(staff, by=None, reason="Late")
        with pytest.raises(ValidationError) as bringing_back:
            unsuspend(staff, by=None, reason="Back")
        with pytest.raises(ValidationError) as leaving_again:
            mark_left(staff, left_on=staff.started_on, by=None, reason="Again")
        staff.refresh_from_db()

    assert suspending.value.code == "staff.not_active"
    assert bringing_back.value.code == "staff.not_suspended"
    assert leaving_again.value.code == "staff.left"
    assert staff.status == StaffStatus.LEFT


def test_left_on_not_before_started_on(asha: User, shop_a: Shop) -> None:
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", started_on=START, by=None)
        with pytest.raises(ValidationError) as refused:
            mark_left(staff, left_on=date(2026, 3, 1), by=None, reason="Typed the wrong date")
        staff.refresh_from_db()

    assert [error.code for error in refused.value.error_dict["__all__"]] == ["staff.left_before_start"]
    # Refused means nothing changed.
    assert staff.status == StaffStatus.ACTIVE


def test_left_on_not_in_the_future(asha: User, shop_a: Shop) -> None:
    # Jack, 27 Oct: a person is marked as left on their last day or after. `left` takes effect at once,
    # so a date ahead would stop their PIN before they really leave.
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
        with pytest.raises(ValidationError) as refused:
            mark_left(staff, left_on=staff.started_on + timedelta(days=1), by=None, reason="Leaves tomorrow")
        staff.refresh_from_db()

    assert refused.value.code == "staff.left_in_future"
    assert staff.status == StaffStatus.ACTIVE


def test_staff_of_another_shop_refused(asha: User, juma: User, other_asha: User, shop_a: Shop, shop_b: Shop) -> None:
    # T1: a manager acts only in their own shop. The guard watches reads, not writes, so it can't stop a
    # row of shop B being named here: the services check it themselves.
    with shop_context(shop_b):
        manager_b = add_staff(shop=shop_b, user=juma, display_name="Juma", by=None)

    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
        with pytest.raises(ValidationError) as suspending:
            suspend(staff, by=manager_b, reason="Late")
        with pytest.raises(ValidationError) as adding:
            add_staff(shop=shop_a, user=other_asha, display_name="Asha M", by=manager_b)
        staff.refresh_from_db()

    assert suspending.value.code == adding.value.code == "staff.other_shop"
    assert staff.status == StaffStatus.ACTIVE


def test_action_outside_the_open_shop_refused(asha: User, juma: User, shop_a: Shop, shop_b: Shop) -> None:
    # T1: a visit works for one shop. Inside shop A's visit, code can't add a job in shop B or change shop
    # B's staff, not even as the system (by=None).
    with shop_context(shop_b):
        staff_b = add_staff(shop=shop_b, user=juma, display_name="Juma", by=None)

    with shop_context(shop_a):
        with pytest.raises(ValidationError) as adding:
            add_staff(shop=shop_b, user=asha, display_name="Asha", by=None)
        with pytest.raises(ValidationError) as suspending:
            suspend(staff_b, by=None, reason="Late")
        with pytest.raises(ValidationError) as giving_pin:
            set_pin(staff_b, "4829", by=None)

    assert adding.value.code == suspending.value.code == giving_pin.value.code == "staff.other_shop"
    # Nothing changed in shop B.
    with shop_context(shop_b):
        staff_b.refresh_from_db()
        assert not StaffMember.objects.filter(user=asha).exists()
    assert staff_b.status == StaffStatus.ACTIVE
    assert staff_b.pin_hash == ""


def test_added_by_names_who_added_them(asha: User, juma: User, shop_a: Shop) -> None:
    # 02 §1: every shop record says who made it. The owner, the shop's first staff member, is added by
    # the system (by=None), so nobody is named; then the owner adds Asha, and her row names the owner.
    with shop_context(shop_a):
        owner = add_staff(shop=shop_a, user=juma, display_name="Juma", by=None)
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", by=owner)
        owner.refresh_from_db()
        staff.refresh_from_db()

    assert owner.created_by is None
    assert staff.created_by == owner


@pytest.mark.parametrize("reason", ["", "   "])
def test_reason_required(asha: User, shop_a: Shop, reason: str) -> None:
    # Rule 7: suspending someone or marking them as left is always done with who, when and why.
    with shop_context(shop_a):
        staff = add_staff(shop=shop_a, user=asha, display_name="Asha", by=None)
        with pytest.raises(ValidationError) as suspending:
            suspend(staff, by=None, reason=reason)
        with pytest.raises(ValidationError) as leaving:
            mark_left(staff, left_on=staff.started_on, by=None, reason=reason)

    assert suspending.value.code == leaving.value.code == "staff.reason_required"
