"""apps/staffpay/tests/test_set_pay_rate.py — setting a worker's daily pay rate (set_pay_rate, WAGE-1; 02 §5, §12):
who may, from which day, and what the amount may be.

Whoever sets a worker's rate sets their pay, so the rule is the PIN's (02 §5), asked by the people app's own lock and
check (lock_worker_for_a_change), with one key more, the one that changes the shop's rules and rates:

    the one acting                                           the answer
    holds staff.manage and settings.manage on the whole
    shop, and every key the worker was given                 done
    lacks either key                                         403
    sets their own rate                                      staff.own
    sets an owner's, or an admin person's                    staff.superuser_only
    the worker holds a key they lack                         staff.more_keys
    the worker has left                                      staff.left
    the system or the superuser                              done, for anyone who hasn't left

From any day of the job, gone by or to come, never before its first day. On the demo, where every visitor logs in as
Meneja, the seed's people keep their rates, and a visitor's note isn't kept. The amounts are made up: the repo is public
(rule 10).
"""

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from pytest_django import Settings

from apps.core.models import Change
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, grant_permission, mark_left
from apps.shops.models import Shop, Side
from apps.staffpay.models import PayRate
from apps.staffpay.selectors import rates_between
from apps.staffpay.services import set_pay_rate

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOV_1 = dt.date(2026, 11, 1)
NOV_10 = dt.date(2026, 11, 10)
NOV_30 = dt.date(2026, 11, 30)
DEC_1 = dt.date(2026, 12, 1)
TEN_THOUSAND = Decimal("10000.00")


def job(shop: Shop, name: str, *, started_on: dt.date = NOV_10, by: StaffMember | None = None) -> StaffMember:
    # A job made the way the app makes one: create_user, then the people service, inside the shop (PPL-2). `by`: who
    # added them; the seed adds its people as the system (None).
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, started_on=started_on, by=by)


def set_rate(
    staff: StaffMember,
    *,
    by: StaffMember | None,
    daily_rate: Decimal = TEN_THOUSAND,
    effective_from: dt.date = NOV_10,
    shares_meals: bool = True,
    note: str = "",
) -> PayRate:
    with shop_context(staff.shop_id):
        return set_pay_rate(
            staff,
            daily_rate=daily_rate,
            effective_from=effective_from,
            shares_meals=shares_meals,
            note=note,
            by=by,
        )


def codes_of(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, set[str]]:
    # Each box's codes, as the page shows them beside it.
    return {field: {error.code or "" for error in errors} for field, errors in refused.value.error_dict.items()}


def rates_of(staff: StaffMember) -> int:
    with shop_context(staff.shop_id):
        return PayRate.objects.filter(staff=staff).count()


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, on the whole shop.
    staff = job(shop_a, "Baba", started_on=NOV_1)
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager the owner has handed both keys, as the demo's Meneja holds them.
    staff = job(shop_a, "Meneja", started_on=NOV_1)
    give_role(staff, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(staff, Permission.STAFF_MANAGE, side=None, by=None)
        grant_permission(staff, Permission.SETTINGS_MANAGE, side=None, by=None)
    return staff


@pytest.fixture
def juma(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    # A seller who started on 10 Nov.
    staff = job(shop_a, "Juma")
    give_role(staff, RoleTemplate.SELLER, side_a)
    return staff


# The day a rate starts, and its amount.


def test_baba_sets_a_rate_from_the_first_day(baba: StaffMember, juma: StaffMember) -> None:
    # Juma started on 10 Nov; Baba types his rate on the 19th, from the 10th: a day gone by, so those days are paid.
    rate = set_rate(juma, by=baba, effective_from=NOV_10)
    with shop_context(juma.shop_id):
        saved = PayRate.objects.get(pk=rate.pk)
        rates = rates_between(juma.shop, NOV_1, NOV_30)
    assert (saved.daily_rate, saved.effective_from, saved.shares_meals) == (TEN_THOUSAND, NOV_10, True)
    # Who set it is the row's own `created_by`, as for a setting.
    assert saved.created_by_id == baba.pk
    assert rates[(juma.pk, NOV_10)] == saved


def test_a_raise_may_start_on_a_day_to_come(baba: StaffMember, juma: StaffMember) -> None:
    set_rate(juma, by=baba, effective_from=NOV_10)
    raise_ = set_rate(juma, by=baba, daily_rate=Decimal("12000"), effective_from=DEC_1, note="Ameongezewa")
    assert (raise_.effective_from, raise_.note) == (DEC_1, "Ameongezewa")
    assert rates_of(juma) == 2


def test_the_cooks_rate_shares_no_meals(baba: StaffMember, shop_a: Shop) -> None:
    neema = job(shop_a, "Neema")
    rate = set_rate(neema, by=baba, shares_meals=False)
    assert rate.shares_meals is False


def test_a_rate_never_starts_before_the_first_day(baba: StaffMember, juma: StaffMember) -> None:
    # The 9th is before Juma worked here: no day of his to pay.
    with pytest.raises(ValidationError) as refused:
        set_rate(juma, by=baba, effective_from=NOV_10 - dt.timedelta(days=1))
    assert codes_of(refused) == {"effective_from": {"pay_rate.before_first_day"}}
    assert rates_of(juma) == 0


@pytest.mark.parametrize("amount", ["0", "-500", "10000.50"])
def test_a_rate_is_whole_shillings_above_nothing(baba: StaffMember, juma: StaffMember, amount: str) -> None:
    with pytest.raises(ValidationError) as refused:
        set_rate(juma, by=baba, daily_rate=Decimal(amount))
    assert codes_of(refused) == {"daily_rate": {"pay_rate.amount_invalid"}}
    assert rates_of(juma) == 0


def test_every_mistake_comes_back_at_once(baba: StaffMember, juma: StaffMember) -> None:
    # Two boxes typed wrong: both are named, each beside its box, so Baba mends them in one go.
    with pytest.raises(ValidationError) as refused:
        set_rate(juma, by=baba, daily_rate=Decimal("0"), effective_from=NOV_1)
    assert codes_of(refused) == {
        "daily_rate": {"pay_rate.amount_invalid"},
        "effective_from": {"pay_rate.before_first_day"},
    }


def test_a_note_is_kept_without_its_spaces(baba: StaffMember, juma: StaffMember) -> None:
    rate = set_rate(juma, by=baba, note="  Ameongezewa  ")
    assert rate.note == "Ameongezewa"


def test_setting_a_rate_tells_no_laptop(baba: StaffMember, juma: StaffMember) -> None:
    # A worker's pay never sits on a shared device (03 §6.1): a rate writes no line in the change log, so no pull
    # ever carries one.
    with shop_context(juma.shop_id):
        lines = Change.objects.count()
    set_rate(juma, by=baba)
    with shop_context(juma.shop_id):
        assert Change.objects.count() == lines


# Who may.


def test_a_manager_with_both_keys_sets_a_workers_rate(meneja: StaffMember, juma: StaffMember) -> None:
    set_rate(juma, by=meneja)
    assert rates_of(juma) == 1


@pytest.mark.parametrize("key", [Permission.STAFF_MANAGE, Permission.SETTINGS_MANAGE])
def test_a_rate_needs_both_keys(shop_a: Shop, give_role: GiveRole, juma: StaffMember, key: Permission) -> None:
    # A manager handed staff.manage to reset PINs, or settings.manage to change the rules, holds only one of the two:
    # neither may change anyone's pay.
    one_key = job(shop_a, "Hamisi", started_on=NOV_1)
    give_role(one_key, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        grant_permission(one_key, key, side=None, by=None)
    with pytest.raises(PermissionDenied):
        set_rate(juma, by=one_key)
    assert rates_of(juma) == 0


def test_nobody_sets_their_own_rate(meneja: StaffMember) -> None:
    # A manager holding both keys could otherwise raise his own pay.
    with pytest.raises(ValidationError) as refused:
        set_rate(meneja, by=meneja, effective_from=NOV_1)
    assert refused.value.code == "staff.own"
    assert rates_of(meneja) == 0


def test_an_owners_rate_is_only_the_superusers(meneja: StaffMember, baba: StaffMember) -> None:
    with pytest.raises(ValidationError) as refused:
        set_rate(baba, by=meneja, effective_from=NOV_1)
    assert refused.value.code == "staff.superuser_only"
    # The superuser, who is nobody's staff, acts as the system.
    set_rate(baba, by=None, effective_from=NOV_1)
    assert rates_of(baba) == 1


def test_a_worker_holding_a_key_the_manager_lacks(meneja: StaffMember, juma: StaffMember) -> None:
    # Juma was handed the owner's own key to approve the pay: a manager without it can't set his rate.
    with shop_context(juma.shop_id):
        grant_permission(juma, Permission.PAY_APPROVE, side=None, by=None)
    with pytest.raises(ValidationError) as refused:
        set_rate(juma, by=meneja)
    assert refused.value.code == "staff.more_keys"


@pytest.mark.parametrize("by_the_system", [False, True])
def test_a_worker_who_left_gets_no_new_rate(baba: StaffMember, juma: StaffMember, by_the_system: bool) -> None:
    # A job that ended is history: what it said then stays as it was, for the system too.
    with shop_context(juma.shop_id):
        mark_left(juma, left_on=NOV_10, by=None, reason="Amehamia Moshi")
    with pytest.raises(ValidationError) as refused:
        set_rate(juma, by=None if by_the_system else baba)
    assert refused.value.code == "staff.left"
    assert rates_of(juma) == 0


def test_another_shops_worker_is_refused(baba: StaffMember, shop_b: Shop) -> None:
    # T1: inside shop A's visit, a job of shop B is never given a rate.
    stranger = job(shop_b, "Juma")
    with shop_context(baba.shop_id), pytest.raises(ValidationError) as refused:
        set_pay_rate(stranger, daily_rate=TEN_THOUSAND, effective_from=NOV_10, by=baba)
    assert refused.value.code == "staff.other_shop"


# The demo.


def test_on_the_demo_the_seeds_people_keep_their_rates(
    settings: Settings, meneja: StaffMember, juma: StaffMember
) -> None:
    # Juma was made by the seed (no one named as his adder): a visitor's rate for him would show to every visitor after,
    # until the morning's seed, so the seed's people stay as made, as their details do (demo.people_fixed).
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        set_rate(juma, by=meneja)
    assert refused.value.code == "demo.people_fixed"
    # The seed itself, as the system, still may.
    set_rate(juma, by=None)
    assert rates_of(juma) == 1


def test_on_the_demo_a_visitors_worker_gets_a_rate_with_no_note(
    settings: Settings, shop_a: Shop, meneja: StaffMember
) -> None:
    # A worker the visitor added can be given a rate, as trying that is the point; a note, which every visitor after
    # would read, signed by the shared manager, isn't kept (demo.no_note, as for a rule).
    settings.DEMO_SEED = True
    added = job(shop_a, "Zawadi", by=meneja)
    with pytest.raises(ValidationError) as refused:
        set_rate(added, by=meneja, note="Ameongezewa")
    assert codes_of(refused) == {"note": {"demo.no_note"}}
    set_rate(added, by=meneja)
    assert rates_of(added) == 1
