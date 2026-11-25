"""apps/staffpay/tests/test_record_advance.py — typing money given to a worker before payday (record_advance) and
crossing out a wrong one (void_advance): WAGE-8, 02 §12.

Juma asks for 20,000 on the 10th while Baba is away: Meneja gives it and types it. On the 16th Meneja types 300,000 for
30,000; Baba crosses it out, "Sifuri moja zaidi", and the 30,000 is typed. Juma was given 50,000.

    the one typing, or crossing out             the answer
    Baba, the owner; Meneja, a manager          the row, with who typed it; or its stamp, with who, when and why
    a seller, without the key                   403
    the key on one side alone                   403: a worker belongs to the whole shop
    one's own, on any of one's jobs             advance.own
    0, a minus, cents, or over ten million      advance.amount_invalid, advance.amount_too_big
    a day to come                               advance.in_future
    before the job's first day, after its last  advance.outside_job
    a worker with no daily pay, as the owner    advance.not_paid_by_day
    no reason                                   advance.reason_missing
    on the demo, a note or a typed reason       demo.no_note, demo.ready_reasons

What the table refuses by itself is test_advance.py's, and what the pay makes of it, test_pay_month.py's. The amounts
are made up (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.utils import timezone
from pytest_django import Settings

from apps.core.models import Change
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import StaffMember
from apps.people.services import grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.models import Advance, PayRate
from apps.staffpay.services import advances_month, pay_month, record_advance, void_advance
from apps.staffpay.tests.days import JAN_1, MONDAY, SUNDAY, job

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

TENTH = dt.date(2026, 11, 10)


def paid_by_day(staff: StaffMember, since: dt.date = JAN_1) -> StaffMember:
    # A daily pay rate, a made-up 10,000, written past set_pay_rate, whose maker would need the keys of pay.
    with shop_context(staff.shop_id):
        PayRate(shop_id=staff.shop_id, staff=staff, daily_rate=Decimal("10000.00"), effective_from=since).save()
    return staff


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    # Paid by the day since January.
    return paid_by_day(job(shop_a, "Juma"))


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, on the whole shop, and no daily pay.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager of the whole shop: money.advance is in the manager's own role (Jack: A). Paid by the day too.
    staff = paid_by_day(job(shop_a, "Meneja"))
    give_role(staff, RoleTemplate.MANAGER, None)
    return staff


def give(staff: StaffMember, by: StaffMember, amount: str = "20000.00", day: dt.date = TENTH, **more: Any) -> Advance:
    facts: dict[str, Any] = {"advance_id": uuid.uuid7(), "note": "Ada ya shule", **more}
    with shop_context(staff.shop_id):
        return record_advance(staff, date=day, amount=Decimal(amount), by=by, **facts)


def cross_out(row: Advance, by: StaffMember, reason: str = "Sifuri moja zaidi") -> Advance:
    with shop_context(row.shop_id):
        return void_advance(row, reason=reason, by=by)


def given_to(staff: StaffMember) -> Decimal:
    # What a worker was given: the rows not crossed out.
    with shop_context(staff.shop_id):
        rows = Advance.objects.filter(staff=staff, voided_at__isnull=True)
        return rows.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


def codes_of(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, set[str]]:
    # Each box's codes, as the page shows them beside it.
    return {field: {error.code or "" for error in errors} for field, errors in refused.value.error_dict.items()}


def rows_of(shop: Shop) -> int:
    with shop_context(shop):
        return Advance.objects.count()


# Typing one.


def test_meneja_types_jumas_advance(shop_a: Shop, meneja: StaffMember, juma: StaffMember) -> None:
    advance_id = uuid.uuid7()
    row = give(juma, meneja, advance_id=advance_id, note="  Ada ya shule ")
    with shop_context(shop_a):
        kept = Advance.objects.get(pk=advance_id)
    assert row.pk == kept.pk
    assert (kept.staff_id, kept.date, kept.amount) == (juma.pk, TENTH, Decimal("20000.00"))
    assert kept.created_by_id == meneja.pk
    # Spaces around a note say nothing.
    assert kept.note == "Ada ya shule"
    assert kept.voided_at is None


def test_several_add_up(baba: StaffMember, meneja: StaffMember, juma: StaffMember) -> None:
    # Twice in one month, once on the same day even: each is money given.
    rows = [give(juma, baba, "30000.00", note=""), give(juma, meneja, "20000.00")]
    assert given_to(juma) == Decimal("50000.00")
    # Each with its own maker's name.
    assert [row.created_by_id for row in rows] == [baba.pk, meneja.pk]


def test_today_and_a_day_gone_by_are_taken_and_a_day_to_come_is_not(
    shop_a: Shop, meneja: StaffMember, juma: StaffMember
) -> None:
    # Typed the day it is given, and a forgotten one later. Tomorrow's isn't given yet: a wrong date, refused beside its
    # box.
    with shop_context(shop_a):
        today = shop_today(shop_a)
    with pytest.raises(ValidationError) as refused:
        give(juma, meneja, day=today + dt.timedelta(days=1))
    assert codes_of(refused) == {"date": {"advance.in_future"}}
    give(juma, meneja, day=today)
    give(juma, meneja, day=TENTH)
    assert rows_of(shop_a) == 2


def test_today_is_the_shops_own(
    shop_a: Shop, meneja: StaffMember, juma: StaffMember, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 01:30 on Tuesday 1 December in Arusha, when UTC still says Monday 30 November: money given after midnight is
    # December's, never refused as of a day to come, and the 2nd is (the review). Baba is called out of bed for it.
    moment = dt.datetime(2026, 12, 1, 1, 30, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: moment)
    first = dt.date(2026, 12, 1)
    with pytest.raises(ValidationError) as refused:
        give(juma, meneja, day=first + dt.timedelta(days=1))
    assert codes_of(refused) == {"date": {"advance.in_future"}}
    give(juma, meneja, day=first)
    with shop_context(shop_a):
        assert advances_month(shop_a, first, viewer=meneja).today == first
        (line,) = pay_month(shop_a, first).workers
    assert (line.display_name, line.pay.advances) == ("Juma", Decimal("20000.00"))


def test_a_sunday_is_taken(shop_a: Shop, meneja: StaffMember, juma: StaffMember) -> None:
    # Money is asked for on any day: a child is sick on Sunday. Unlike the meals, it is no working day's.
    give(juma, meneja, day=SUNDAY)
    assert rows_of(shop_a) == 1


def test_only_within_the_jobs_days(shop_a: Shop, meneja: StaffMember) -> None:
    # Neema worked from 5 to 14 November: her first and last days take one, the days around them none. Nobody gives an
    # advance on pay to one who doesn't work there.
    first, last = dt.date(2026, 11, 5), dt.date(2026, 11, 14)
    with shop_context(shop_a):
        neema = job(shop_a, "Neema")
        StaffMember.objects.filter(pk=neema.pk).update(started_on=first)
        neema.refresh_from_db()
        paid_by_day(neema, first)
        mark_left(neema, left_on=last, by=None, reason="Ameacha kazi")
    for day in (first - dt.timedelta(days=1), last + dt.timedelta(days=1)):
        with pytest.raises(ValidationError) as refused:
            give(neema, meneja, day=day)
        assert codes_of(refused) == {"date": {"advance.outside_job"}}, day
    give(neema, meneja, day=first)
    # One who left, for a day they worked: a forgotten one can still be typed, so the last pay is right.
    give(neema, meneja, day=last)
    assert rows_of(shop_a) == 2


def test_one_suspended_may_be_given_money(shop_a: Shop, meneja: StaffMember, juma: StaffMember) -> None:
    # Suspended this morning, given 20,000 yesterday: the money was given all the same.
    with shop_context(shop_a):
        suspend(juma, by=None, reason="Uchunguzi")
    give(juma, meneja)
    assert given_to(juma) == Decimal("20000.00")


def test_only_a_worker_paid_by_the_day(shop_a: Shop, baba: StaffMember, meneja: StaffMember) -> None:
    # The owner has no daily pay: what he takes is a withdrawal, the drawer's (02 §10), never an advance on pay. One
    # whose first rate starts later in the month is paid by the day.
    with pytest.raises(ValidationError) as refused:
        give(baba, meneja)
    assert codes_of(refused) == {"staff": {"advance.not_paid_by_day"}}
    give(paid_by_day(job(shop_a, "Amani"), MONDAY), meneja, day=TENTH)
    assert rows_of(shop_a) == 1


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "20000.50"])
def test_an_advance_is_whole_shillings_above_nothing(meneja: StaffMember, juma: StaffMember, amount: str) -> None:
    with pytest.raises(ValidationError) as refused:
        give(juma, meneja, amount)
    assert codes_of(refused) == {"amount": {"advance.amount_invalid"}}


def test_an_amount_with_zeros_too_many_is_refused(shop_a: Shop, meneja: StaffMember, juma: StaffMember) -> None:
    # Ten million is more than any month's pay: a slip of the zeros. Ten million itself is taken.
    with pytest.raises(ValidationError) as refused:
        give(juma, meneja, "10000001.00")
    assert codes_of(refused) == {"amount": {"advance.amount_too_big"}}
    give(juma, meneja, "10000000.00")
    assert rows_of(shop_a) == 1


def test_one_bigger_than_the_pay_so_far_is_taken(meneja: StaffMember, juma: StaffMember) -> None:
    # Juma earned nothing yet and took 500,000: the money was given, so the system keeps it, and the pay shows its minus
    # (WAGE-2). Whether to give it is the giver's to choose, before they type.
    give(juma, meneja, "500000.00")
    assert given_to(juma) == Decimal("500000.00")


def test_every_mistake_comes_back_at_once(shop_a: Shop, baba: StaffMember, meneja: StaffMember) -> None:
    # Three wrong boxes: each said beside its own, so a person mends all in one go (ADR-0040).
    with shop_context(shop_a):
        tomorrow = shop_today(shop_a) + dt.timedelta(days=1)
    with pytest.raises(ValidationError) as refused:
        give(baba, meneja, "0.00", tomorrow)
    assert codes_of(refused) == {
        "staff": {"advance.not_paid_by_day"},
        "amount": {"advance.amount_invalid"},
        "date": {"advance.in_future"},
    }


def test_a_note_too_long_is_refused(meneja: StaffMember, juma: StaffMember) -> None:
    with pytest.raises(ValidationError) as refused:
        give(juma, meneja, note="u" * 201)
    assert set(codes_of(refused)) == {"note"}


def test_an_id_another_row_holds_never_writes_over_it(meneja: StaffMember, juma: StaffMember) -> None:
    # The route answers a request sent twice with the row it made (CreateOnceMixin); the service itself never turns a
    # second call with the same id into a change of the first (03 §5.4).
    row = give(juma, meneja)
    with pytest.raises(ValidationError):
        give(juma, meneja, "90000.00", advance_id=row.pk)
    assert given_to(juma) == Decimal("20000.00")


def test_an_advance_tells_no_laptop(shop_a: Shop, baba: StaffMember, meneja: StaffMember, juma: StaffMember) -> None:
    # What a worker took comes off their pay, which never sits on a shared device (03 §6.1): typing and crossing out
    # write no line in the change log, so no pull ever carries one.
    with shop_context(shop_a):
        lines = Change.objects.count()
    cross_out(give(juma, meneja), baba)
    with shop_context(shop_a):
        assert Change.objects.count() == lines


# Who may.


def test_the_owner_types_one(baba: StaffMember, juma: StaffMember) -> None:
    give(juma, baba)
    assert given_to(juma) == Decimal("20000.00")


@pytest.mark.parametrize("template", [RoleTemplate.SELLER, RoleTemplate.CASHIER, RoleTemplate.WORKER])
def test_without_the_key_nobody_types_or_crosses_out(
    shop_a: Shop, give_role: GiveRole, meneja: StaffMember, juma: StaffMember, template: RoleTemplate
) -> None:
    row = give(juma, meneja)
    other = job(shop_a, "Hamisi")
    give_role(other, template, None)
    with pytest.raises(PermissionDenied):
        give(juma, other)
    with pytest.raises(PermissionDenied):
        cross_out(row, other)
    assert given_to(juma) == Decimal("20000.00")


def test_the_key_on_one_side_types_and_crosses_out_nothing(
    shop_a: Shop, side_a: Side, meneja: StaffMember, juma: StaffMember
) -> None:
    # A worker's pay is the whole shop's: a key given on Dawa alone opens nothing of it (02 §5).
    other = job(shop_a, "Hamisi")
    with shop_context(shop_a):
        grant_permission(other, Permission.MONEY_ADVANCE, side=side_a, by=None)
    with pytest.raises(PermissionDenied):
        give(juma, other)
    with pytest.raises(PermissionDenied):
        cross_out(give(juma, meneja), other)


def test_one_suspended_types_and_crosses_out_nothing(shop_a: Shop, meneja: StaffMember, juma: StaffMember) -> None:
    # Meneja is suspended this morning, in a tab still open from before: no key counts (X2), read afresh.
    row = give(juma, meneja)
    with shop_context(shop_a):
        suspend(meneja, by=None, reason="Uchunguzi")
    with pytest.raises(PermissionDenied):
        give(juma, meneja)
    with pytest.raises(PermissionDenied):
        cross_out(row, meneja)
    assert rows_of(shop_a) == 1


def test_one_who_left_types_and_crosses_out_nothing(shop_a: Shop, meneja: StaffMember, juma: StaffMember) -> None:
    # Left this morning, in a tab still open from before: a job that ended holds no key (X2).
    row = give(juma, meneja)
    with shop_context(shop_a):
        mark_left(meneja, left_on=shop_today(shop_a), by=None, reason="Ameacha kazi")
    with pytest.raises(PermissionDenied):
        give(juma, meneja)
    with pytest.raises(PermissionDenied):
        cross_out(row, meneja)
    assert given_to(juma) == Decimal("20000.00")


def test_nobody_types_their_own(baba: StaffMember, meneja: StaffMember) -> None:
    # Meneja takes 50,000: Baba types it, never Meneja alone (Jack: A), as for one's own day and daily rate.
    with pytest.raises(ValidationError) as refused:
        give(meneja, meneja)
    assert refused.value.code == "advance.own"
    give(meneja, baba, "50000.00")
    assert given_to(meneja) == Decimal("50000.00")


def test_nobody_crosses_out_their_own(baba: StaffMember, meneja: StaffMember) -> None:
    # Nor erases what they took, or Meneja would be paid the 50,000 twice.
    row = give(meneja, baba, "50000.00")
    with pytest.raises(ValidationError) as refused:
        cross_out(row, meneja)
    assert refused.value.code == "advance.own"
    assert given_to(meneja) == Decimal("50000.00")


def test_ones_own_is_the_persons_not_the_jobs(shop_a: Shop, give_role: GiveRole, baba: StaffMember) -> None:
    # Baraka sold until the 14th and came back on the 16th as a manager (PPL-11): one person, two jobs. The old job's
    # advance is theirs all the same, to type or to cross out.
    old = paid_by_day(job(shop_a, "Baraka"))
    row = give(old, baba)
    with shop_context(shop_a):
        mark_left(old, left_on=dt.date(2026, 11, 14), by=None, reason="Ameacha kazi")
        new = hire_again(old, display_name="Baraka", started_on=MONDAY, by=None)
    give_role(new, RoleTemplate.MANAGER, None)
    with pytest.raises(ValidationError) as refused:
        give(old, new)
    assert refused.value.code == "advance.own"
    with pytest.raises(ValidationError) as refused:
        cross_out(row, new)
    assert refused.value.code == "advance.own"
    assert given_to(old) == Decimal("20000.00")


def test_a_person_of_another_shop_is_a_bug(meneja: StaffMember, juma: StaffMember, staff_b: StaffMember) -> None:
    # T1: the route finds both in the one shop open, so another shop's person here is our code's mistake: a server
    # error, before anything is read.
    row = give(juma, meneja)
    with shop_context(juma.shop_id):
        with pytest.raises(ShopMismatch, match="record_advance"):
            record_advance(juma, advance_id=uuid.uuid7(), date=TENTH, amount=Decimal("20000.00"), by=staff_b)
        with pytest.raises(ShopMismatch, match="void_advance"):
            void_advance(row, reason="Sifuri moja zaidi", by=staff_b)


# Crossing one out.


def test_baba_crosses_out_menejas_slip(shop_a: Shop, baba: StaffMember, meneja: StaffMember, juma: StaffMember) -> None:
    # The whole of the story above: 20,000, and 300,000 crossed out, and 30,000.
    give(juma, meneja, "20000.00")
    wrong = give(juma, meneja, "300000.00", MONDAY, note="")
    assert given_to(juma) == Decimal("320000.00")
    crossed = cross_out(wrong, baba, "  Sifuri moja zaidi ")
    assert (crossed.voided_by_id, crossed.void_reason) == (baba.pk, "Sifuri moja zaidi")
    assert crossed.voided_at is not None
    assert given_to(juma) == Decimal("20000.00")
    give(juma, meneja, "30000.00", MONDAY, note="")
    assert given_to(juma) == Decimal("50000.00")
    # What was typed stays: the row is crossed out, never gone (T2).
    assert rows_of(shop_a) == 3


def test_whoever_typed_it_may_cross_it_out(meneja: StaffMember, juma: StaffMember) -> None:
    # Meneja's own slip of the hand on Juma's: with Meneja's name, when and why on it. Only one's own money is barred.
    cross_out(give(juma, meneja), meneja)
    assert given_to(juma) == Decimal("0.00")


def test_the_same_crossing_out_sent_twice_is_done_once(
    baba: StaffMember, meneja: StaffMember, juma: StaffMember
) -> None:
    # The answer was lost on the way and the request came again: the first stamp is answered, never written again.
    row = give(juma, meneja)
    first = cross_out(row, baba)
    again = cross_out(row, baba, "Sababu nyingine")
    assert (again.voided_at, again.void_reason) == (first.voided_at, "Sifuri moja zaidi")


def test_one_crossed_out_first_by_someone_else_answers_theirs(
    baba: StaffMember, meneja: StaffMember, juma: StaffMember
) -> None:
    row = give(juma, meneja)
    cross_out(row, baba)
    answered = cross_out(row, meneja, "Sababu yangu")
    assert (answered.voided_by_id, answered.void_reason) == (baba.pk, "Sifuri moja zaidi")


@pytest.mark.parametrize("reason", ["", "   "])
def test_crossing_out_says_why(meneja: StaffMember, juma: StaffMember, reason: str) -> None:
    row = give(juma, meneja)
    with pytest.raises(ValidationError) as refused:
        cross_out(row, meneja, reason)
    assert codes_of(refused) == {"reason": {"advance.reason_missing"}}
    assert given_to(juma) == Decimal("20000.00")


# On the demo, where every visitor shares Meneja's login (OPS-3).


def test_on_the_demo_an_advance_takes_no_note(
    settings: Settings, shop_a: Shop, meneja: StaffMember, juma: StaffMember
) -> None:
    # A typed note would show to every visitor after, signed by the shared manager (demo.no_note, as for a rule).
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        give(juma, meneja)
    assert codes_of(refused) == {"note": {"demo.no_note"}}
    give(juma, meneja, note="")
    assert rows_of(shop_a) == 1


def test_on_the_demo_a_reason_is_the_ready_one(settings: Settings, meneja: StaffMember, juma: StaffMember) -> None:
    row = give(juma, meneja)
    settings.DEMO_SEED = True
    with pytest.raises(ValidationError) as refused:
        cross_out(row, meneja, "Sifuri moja zaidi")
    assert codes_of(refused) == {"reason": {"demo.ready_reasons"}}
    assert cross_out(row, meneja, "wrong_amount").void_reason == "wrong_amount"
