"""apps/staffpay/tests/test_record_meal_money.py — typing the day's meal money (record_meal_money) and crossing out a
wrong one (void_meal_money): WAGE-7, 02 §12.

Asha, a seller the owner has given the key, types Monday's flour, 5,000, and its meat, 30,000 by mistake. Baba crosses
out the 30,000, "Sifuri moja zaidi", and she types 3,000: Monday's money is 8,000.

    the one typing, or crossing out             the answer
    Baba, the owner; whoever he gave the key    the row, with who typed it; or its stamp, with who, when and why
    a manager or a seller without the key       403
    the key on one side alone                   403: the meals are the whole shop's
    0, a minus, cents, or over ten million      meal_money.amount_invalid, meal_money.amount_too_big
    a day to come                               meal_money.in_future
    a Sunday, or a day attendance was off       meal_money.not_working_day
    no reason                                   meal_money.reason_missing
    on the demo, a note or a typed reason       demo.no_note, demo.ready_reasons

What the table refuses by itself is test_meal_money.py's, and what the book makes of the money,
test_attendance_book.py's. The amounts are made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from pytest_django import Settings

from apps.core.models import Change
from apps.core.permissions import Permission, RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import StaffMember
from apps.people.services import grant_permission, suspend
from apps.shops.models import Closure, Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.models import MealMoney
from apps.staffpay.selectors import meal_money_by_date
from apps.staffpay.services import record_meal_money, void_meal_money
from apps.staffpay.tests.days import JAN_1, MONDAY, SUNDAY, job, rule, switch_on

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture(autouse=True)
def the_shops_day(shop_a: Shop) -> None:
    # The shop switched attendance on in January (days.py).
    switch_on(shop_a)


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, on the whole shop, this one too.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def asha(shop_a: Shop, side_a: Side, give_role: GiveRole) -> StaffMember:
    # A seller on one side, whom the owner has given the key to the meal money, on every side (Jack, 15 Nov 2026).
    staff = job(shop_a, "Asha")
    give_role(staff, RoleTemplate.SELLER, side_a)
    with shop_context(shop_a):
        grant_permission(staff, Permission.MEALS_RECORD, side=None, by=None)
    return staff


def type_money(by: StaffMember, amount: str = "5000.00", day: dt.date = MONDAY, **changes: Any) -> MealMoney:
    facts: dict[str, Any] = {"money_id": uuid.uuid7(), "note": "Unga na maharage", **changes}
    with shop_context(by.shop_id):
        shop = Shop.objects.get(pk=by.shop_id)
        return record_meal_money(shop, date=day, amount=Decimal(amount), by=by, **facts)


def cross_out(row: MealMoney, by: StaffMember, reason: str = "Sifuri moja zaidi") -> MealMoney:
    with shop_context(row.shop_id):
        return void_meal_money(row, reason=reason, by=by)


def mondays_money(shop: Shop) -> Decimal | None:
    with shop_context(shop):
        return meal_money_by_date(shop, MONDAY, MONDAY).get(MONDAY)


def codes_of(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, set[str]]:
    # Each box's codes, as the page shows them beside it.
    return {field: {error.code or "" for error in errors} for field, errors in refused.value.error_dict.items()}


def rows_of(shop: Shop) -> int:
    with shop_context(shop):
        return MealMoney.objects.count()


# Typing the day's money.


def test_asha_types_mondays_money(shop_a: Shop, asha: StaffMember) -> None:
    money_id = uuid.uuid7()
    row = type_money(asha, money_id=money_id, note="  Unga na maharage ")
    with shop_context(shop_a):
        kept = MealMoney.objects.get(pk=money_id)
    assert row.pk == kept.pk
    assert (kept.date, kept.amount, kept.created_by_id) == (MONDAY, Decimal("5000.00"), asha.pk)
    # Spaces around a note say nothing.
    assert kept.note == "Unga na maharage"
    assert kept.voided_at is None


def test_several_a_day_add_up(shop_a: Shop, asha: StaffMember, baba: StaffMember) -> None:
    # Flour in the morning, typed by Asha, and meat at noon, typed by Baba: Monday's money is both.
    type_money(asha, "5000.00")
    type_money(baba, "3000.00", note="")
    assert mondays_money(shop_a) == Decimal("8000.00")


def test_today_and_a_day_gone_by_take_money_and_a_day_to_come_does_not(shop_a: Shop, asha: StaffMember) -> None:
    # Typed each day, and a forgotten day later. Tomorrow's meals aren't cooked yet: a wrong date, so it is refused
    # beside its box. The shop's own today, never UTC's. Whole days either side, so no Sunday is in the way.
    with shop_context(shop_a):
        today = shop_today(shop_a)
    to_come = today + dt.timedelta(days=1 if today.weekday() != 5 else 2)
    with pytest.raises(ValidationError) as refused:
        type_money(asha, day=to_come)
    assert codes_of(refused) == {"date": {"meal_money.in_future"}}
    if today.weekday() != 6:
        type_money(asha, day=today)
    type_money(asha, day=MONDAY)
    assert rows_of(shop_a) == (2 if today.weekday() != 6 else 1)


def test_a_sunday_takes_no_money(shop_a: Shop, asha: StaffMember) -> None:
    # The shop is shut and nobody is paid (01 §8.1): money typed there would be shared by nobody, a slip of the date.
    with pytest.raises(ValidationError) as refused:
        type_money(asha, day=SUNDAY)
    assert codes_of(refused) == {"date": {"meal_money.not_working_day"}}
    assert rows_of(shop_a) == 0


def test_a_day_attendance_was_off_takes_no_money(shop_a: Shop, asha: StaffMember) -> None:
    # The book keeps no day while attendance is off (ADR-0033), so nobody could share it: the owner switched it off from
    # Monday on.
    rule(shop_a, ATTENDANCE_ON, False, MONDAY)
    with pytest.raises(ValidationError) as refused:
        type_money(asha, day=MONDAY)
    assert codes_of(refused) == {"date": {"meal_money.not_working_day"}}
    type_money(asha, day=MONDAY - dt.timedelta(days=3))
    assert rows_of(shop_a) == 1


def test_a_closed_day_takes_money(shop_a: Shop, asha: StaffMember) -> None:
    # The morning of a funeral: breakfast was cooked before the shop closed at 10:00. Who shares it is each day's
    # decision (ATT-10), so the money may be typed.
    with shop_context(shop_a):
        Closure(shop=shop_a, name="Msiba", first_day=MONDAY, last_day=MONDAY).save()
    type_money(asha)
    assert rows_of(shop_a) == 1


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "5000.50"])
def test_money_is_whole_shillings_above_nothing(asha: StaffMember, amount: str) -> None:
    with pytest.raises(ValidationError) as refused:
        type_money(asha, amount)
    assert codes_of(refused) == {"amount": {"meal_money.amount_invalid"}}


def test_an_amount_with_zeros_too_many_is_refused(shop_a: Shop, asha: StaffMember) -> None:
    # Ten million is more than any day's meals: a slip of the zeros. Ten million itself is taken.
    with pytest.raises(ValidationError) as refused:
        type_money(asha, "10000001.00")
    assert codes_of(refused) == {"amount": {"meal_money.amount_too_big"}}
    type_money(asha, "10000000.00")
    assert rows_of(shop_a) == 1


def test_every_mistake_comes_back_at_once(asha: StaffMember) -> None:
    # Two wrong boxes: each said beside its own, so a person mends both in one go (ADR-0040).
    with pytest.raises(ValidationError) as refused:
        type_money(asha, "0.00", SUNDAY)
    assert codes_of(refused) == {"amount": {"meal_money.amount_invalid"}, "date": {"meal_money.not_working_day"}}


def test_a_note_too_long_is_refused(asha: StaffMember) -> None:
    with pytest.raises(ValidationError) as refused:
        type_money(asha, note="u" * 201)
    assert set(codes_of(refused)) == {"note"}


def test_an_id_another_row_holds_never_writes_over_it(shop_a: Shop, asha: StaffMember) -> None:
    # The route answers a request sent twice with the row it made (CreateOnceMixin); the service itself never turns a
    # second call with the same id into a change of the first (03 §5.4).
    row = type_money(asha)
    with pytest.raises(ValidationError):
        type_money(asha, "9000.00", money_id=row.pk)
    assert mondays_money(shop_a) == Decimal("5000.00")


def test_meal_money_tells_no_laptop(shop_a: Shop, asha: StaffMember, baba: StaffMember) -> None:
    # What a worker pays for meals is part of their pay, which never sits on a shared device (03 §6.1): typing and
    # crossing out write no line in the change log, so no pull ever carries one.
    with shop_context(shop_a):
        lines = Change.objects.count()
    cross_out(type_money(asha), baba)
    with shop_context(shop_a):
        assert Change.objects.count() == lines


# Who may.


def test_the_owner_types_money(baba: StaffMember, shop_a: Shop) -> None:
    type_money(baba)
    assert rows_of(shop_a) == 1


@pytest.mark.parametrize("template", [RoleTemplate.MANAGER, RoleTemplate.SELLER])
def test_without_the_key_nobody_types_or_crosses_out(
    shop_a: Shop, give_role: GiveRole, asha: StaffMember, template: RoleTemplate
) -> None:
    # A manager too: it is the owner's to give (Jack, 15 Nov 2026), and he hasn't given it to this one.
    row = type_money(asha)
    other = job(shop_a, "Hamisi")
    give_role(other, template, None)
    with pytest.raises(PermissionDenied):
        type_money(other)
    with pytest.raises(PermissionDenied):
        cross_out(row, other)
    assert mondays_money(shop_a) == Decimal("5000.00")


def test_the_key_on_one_side_types_nothing(shop_a: Shop, side_a: Side, asha: StaffMember) -> None:
    # The meals are the whole shop's: a key given on Dawa alone opens nothing of it (02 §5).
    other = job(shop_a, "Hamisi")
    with shop_context(shop_a):
        grant_permission(other, Permission.MEALS_RECORD, side=side_a, by=None)
    with pytest.raises(PermissionDenied):
        type_money(other)
    with pytest.raises(PermissionDenied):
        cross_out(type_money(asha), other)


def test_one_suspended_types_and_crosses_out_nothing(shop_a: Shop, asha: StaffMember) -> None:
    # Suspended this morning, in a tab still open from before: no key counts (X2), read afresh.
    row = type_money(asha)
    with shop_context(shop_a):
        suspend(asha, by=None, reason="Uchunguzi")
    with pytest.raises(PermissionDenied):
        type_money(asha)
    with pytest.raises(PermissionDenied):
        cross_out(row, asha)
    assert rows_of(shop_a) == 1


def test_a_person_of_another_shop_is_a_bug(shop_a: Shop, asha: StaffMember, staff_b: StaffMember) -> None:
    # T1: the route finds both in the one shop open, so another shop's person here is our code's mistake: a server
    # error, before anything is read.
    row = type_money(asha)
    with shop_context(shop_a):
        with pytest.raises(ShopMismatch, match="record_meal_money"):
            record_meal_money(
                shop_a, money_id=uuid.uuid7(), date=MONDAY, amount=Decimal("5000.00"), note="", by=staff_b
            )
        with pytest.raises(ShopMismatch, match="void_meal_money"):
            void_meal_money(row, reason="Sifuri moja zaidi", by=staff_b)


# Crossing one out.


def test_baba_crosses_out_ashas_mistake(shop_a: Shop, asha: StaffMember, baba: StaffMember) -> None:
    # The whole of the story above: 5,000, and 30,000 crossed out, and 3,000.
    type_money(asha, "5000.00")
    wrong = type_money(asha, "30000.00", note="Nyama")
    assert mondays_money(shop_a) == Decimal("35000.00")
    crossed = cross_out(wrong, baba, "  Sifuri moja zaidi ")
    assert (crossed.voided_by_id, crossed.void_reason) == (baba.pk, "Sifuri moja zaidi")
    assert crossed.voided_at is not None
    assert mondays_money(shop_a) == Decimal("5000.00")
    type_money(asha, "3000.00", note="Nyama")
    assert mondays_money(shop_a) == Decimal("8000.00")
    # What was typed stays: the row is crossed out, never gone (T2).
    assert rows_of(shop_a) == 3


def test_whoever_typed_it_may_cross_it_out(shop_a: Shop, asha: StaffMember) -> None:
    # Anyone with the key, on any row, their own too: with her name, when and why on it (the plan Jack approved).
    cross_out(type_money(asha), asha)
    assert mondays_money(shop_a) is None


def test_the_same_crossing_out_sent_twice_is_done_once(shop_a: Shop, asha: StaffMember, baba: StaffMember) -> None:
    # The answer was lost on the way and the request came again: the first stamp is answered, never written again.
    row = type_money(asha)
    first = cross_out(row, baba)
    again = cross_out(row, baba, "Sababu nyingine")
    assert (again.voided_at, again.void_reason) == (first.voided_at, "Sifuri moja zaidi")


def test_one_crossed_out_first_by_someone_else_answers_theirs(
    shop_a: Shop, asha: StaffMember, baba: StaffMember
) -> None:
    row = type_money(asha)
    cross_out(row, baba)
    answered = cross_out(row, asha, "Sababu yangu")
    assert (answered.voided_by_id, answered.void_reason) == (baba.pk, "Sifuri moja zaidi")


@pytest.mark.parametrize("reason", ["", "   "])
def test_crossing_out_says_why(shop_a: Shop, asha: StaffMember, reason: str) -> None:
    row = type_money(asha)
    with pytest.raises(ValidationError) as refused:
        cross_out(row, asha, reason)
    assert codes_of(refused) == {"reason": {"meal_money.reason_missing"}}
    assert mondays_money(shop_a) == Decimal("5000.00")


# On the demo, where every visitor shares Meneja's login (OPS-3).


def test_on_the_demo_money_takes_no_note(settings: Settings, shop_a: Shop, asha: StaffMember) -> None:
    # A typed note would show to every visitor after, signed by the shared manager (demo.no_note, as for a rule).
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        type_money(asha)
    assert codes_of(refused) == {"note": {"demo.no_note"}}
    type_money(asha, note="")
    assert rows_of(shop_a) == 1


def test_on_the_demo_a_reason_is_the_ready_one(settings: Settings, shop_a: Shop, asha: StaffMember) -> None:
    row = type_money(asha)
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        cross_out(row, asha, "Sifuri moja zaidi")
    assert codes_of(refused) == {"reason": {"demo.ready_reasons"}}
    assert cross_out(row, asha, "wrong_amount").void_reason == "wrong_amount"


def test_money_of_a_span_is_read_inside_its_own_shop(shop_a: Shop, shop_b: Shop, asha: StaffMember) -> None:
    # meal_money_by_date's own guards: another shop open would answer "no money" without a word (ADR-0022), and a
    # datetime is a moment, not the shop's day.
    type_money(asha)
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        meal_money_by_date(shop_a, JAN_1, MONDAY)
    moment = dt.datetime(2026, 11, 16, tzinfo=dt.UTC)
    with shop_context(shop_a), pytest.raises(TypeError):
        meal_money_by_date(shop_a, moment, moment)
