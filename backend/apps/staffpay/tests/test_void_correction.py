"""apps/staffpay/tests/test_void_correction.py — a correction typed wrong, crossed out (WAGE-10; 02 §12, T2):
void_correction (apps/staffpay/services/correction.py).

    10:05  Baba types + 90,000 on Juma's December, "Novemba: siku ya 12/11 haikuhesabiwa", meaning 9,000
    10:20  Batilisha: "Kiasi kimekosewa"
           → the correction stays, struck through, with who, when and why, and counts for nothing; + 9,000 is typed

Never one's own, never stamped twice, never brought back, and never once its month's pay is approved, as its payslip
holds it then (A3). Only whoever approves pay crosses one out, as only they type one (Jack: A). Months are approved here
by writing their rows, as the approval's own tests are test_approve_month.py's. The amounts are made up: the repo is
public (rule 10).
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from pytest_django import Settings

from apps.core.models import Change
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import StaffMember
from apps.people.services import grant_permission, hire_again, mark_left
from apps.shops.models import Shop, Side
from apps.staffpay.models import PayCorrection, PayRate, PayRun
from apps.staffpay.services import (
    DEMO_CORRECTION_VOID_REASONS,
    ready_correction_void_reasons,
    record_correction,
    void_correction,
)
from apps.staffpay.tests.days import JAN_1, job
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER, DECEMBER = dt.date(2026, 11, 1), dt.date(2026, 12, 1)
WHY = "Kiasi kimekosewa"
THREE_KEYS = (Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE)


@pytest.fixture(autouse=True)
def third_of_december(monkeypatch: pytest.MonkeyPatch) -> None:
    # 10:20 on Thursday 3 December in Arusha: November is over, December runs.
    moment = dt.datetime(2026, 12, 3, 10, 20, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: moment)


def paid_by_day(staff: StaffMember) -> StaffMember:
    # A daily pay rate since January, a made-up 10,000, written past set_pay_rate, whose maker would need the keys.
    with shop_context(staff.shop_id):
        PayRate(shop_id=staff.shop_id, staff=staff, daily_rate=Decimal("10000.00"), effective_from=JAN_1).save()
    return staff


def holding(staff: StaffMember, keys: tuple[str, ...] = THREE_KEYS) -> StaffMember:
    # pay.approve and the two keys of pay, or some of them, on the whole shop.
    with shop_context(staff.shop_id):
        for key in keys:
            grant_permission(staff, key, side=None, by=None)
    return staff


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key, and no daily pay.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def mjomba(shop_a: Shop) -> StaffMember:
    # A second one who approves pay, while Baba is away.
    return holding(job(shop_a, "Mjomba"))


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    return paid_by_day(job(shop_a, "Juma"))


def correct(staff: StaffMember, by: StaffMember, amount: str = "90000.00", month: dt.date = DECEMBER) -> PayCorrection:
    with shop_context(staff.shop_id):
        return record_correction(
            staff,
            correction_id=uuid.uuid7(),
            month=month,
            amount=Decimal(amount),
            reason="Novemba: siku ya 12/11 haikuhesabiwa",
            by=by,
        )


@pytest.fixture
def wrong(juma: StaffMember, baba: StaffMember) -> PayCorrection:
    # Baba's + 90,000, meaning 9,000.
    return correct(juma, baba)


def cross_out(row: PayCorrection, by: StaffMember, reason: str = WHY) -> PayCorrection:
    with shop_context(row.shop_id):
        return void_correction(row, reason=reason, by=by)


def counted(staff: StaffMember) -> list[Decimal]:
    # The corrections of a worker's that still count, the rows not crossed out.
    with shop_context(staff.shop_id):
        return list(PayCorrection.objects.filter(staff=staff, voided_at__isnull=True).values_list("amount", flat=True))


def code_of(refused: pytest.ExceptionInfo[ValidationError]) -> str | None:
    (error,) = refused.value.error_list
    return error.code


def test_a_correction_crossed_out_stays_with_who_when_and_why(
    baba: StaffMember, juma: StaffMember, wrong: PayCorrection
) -> None:
    row = cross_out(wrong, baba, f"  {WHY} ")
    assert row.pk == wrong.pk
    assert (row.voided_by_id, row.void_reason) == (baba.pk, WHY)
    assert row.voided_at == timezone.now()
    # Kept, and counting for nothing: Juma's December takes no + 90,000.
    with shop_context(juma.shop_id):
        assert PayCorrection.objects.filter(pk=wrong.pk).exists()
    assert counted(juma) == []


def test_then_the_right_one_is_typed(baba: StaffMember, juma: StaffMember, wrong: PayCorrection) -> None:
    cross_out(wrong, baba)
    correct(juma, baba, "9000.00")
    assert counted(juma) == [Decimal("9000.00")]


def test_whoever_approves_pay_crosses_out_anyones(baba: StaffMember, mjomba: StaffMember, wrong: PayCorrection) -> None:
    # Baba typed it; Mjomba, who approves pay too, crosses it out: the keys decide, never who typed it.
    assert cross_out(wrong, mjomba).voided_by_id == mjomba.pk


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_crossing_out_says_why(baba: StaffMember, wrong: PayCorrection, reason: str) -> None:
    with pytest.raises(ValidationError) as refused:
        cross_out(wrong, baba, reason)
    assert {field: [e.code for e in errors] for field, errors in refused.value.error_dict.items()} == {
        "reason": ["correction.reason_missing"]
    }


def test_crossed_out_twice_is_stamped_once(baba: StaffMember, mjomba: StaffMember, wrong: PayCorrection) -> None:
    # Sent twice, or by Mjomba a moment after Baba: the first stamp stands, and the second is answered with it.
    first = cross_out(wrong, baba)
    second = cross_out(wrong, mjomba, "Sababu nyingine")
    assert (second.voided_by_id, second.void_reason, second.voided_at) == (baba.pk, WHY, first.voided_at)


def test_an_approved_months_correction_stays(shop_a: Shop, baba: StaffMember, juma: StaffMember) -> None:
    # Typed on 3 December into November, still open then (WAGE-10's default); November approved since: it is a line of
    # Juma's November payslip now, and stays (A3). The month after's still cross out.
    in_november = correct(juma, baba, "9000.00", month=NOVEMBER)
    in_december = correct(juma, baba)
    with shop_context(shop_a):
        PayRun.objects.create(shop=shop_a, month=NOVEMBER, created_by=baba)
    with pytest.raises(ValidationError) as refused:
        cross_out(in_november, baba)
    assert code_of(refused) == "pay.day_approved"
    cross_out(in_december, baba)
    assert counted(juma) == [Decimal("9000.00")]


def test_one_crossed_out_before_the_approval_is_answered_as_it_was(
    shop_a: Shop, baba: StaffMember, juma: StaffMember
) -> None:
    # Crossed out on the 3rd, the answer lost, sent again after November is approved: answered with its stamp, never
    # refused for a month that closed since, as nothing would change.
    row = correct(juma, baba, month=NOVEMBER)
    first = cross_out(row, baba)
    with shop_context(shop_a):
        PayRun.objects.create(shop=shop_a, month=NOVEMBER, created_by=baba)
    assert cross_out(row, baba).voided_at == first.voided_at


def test_nobody_crosses_out_their_own(shop_a: Shop, baba: StaffMember, mjomba: StaffMember) -> None:
    # Jack: A. Mjomba is paid by the day too, and Baba took 5,000 off his December: Mjomba never takes it back himself.
    paid_by_day(mjomba)
    taken = correct(mjomba, baba, "-5000.00")
    with pytest.raises(ValidationError) as refused:
        cross_out(taken, mjomba)
    assert code_of(refused) == "correction.own"
    assert counted(mjomba) == [Decimal("-5000.00")]


def test_ones_own_is_the_persons_not_the_jobs(shop_a: Shop, baba: StaffMember) -> None:
    # Mjomba left in October and was hired again on 1 November (PPL-11): his old job's correction is his own all the
    # same.
    with shop_context(shop_a):
        old = paid_by_day(job(shop_a, "Mjomba"))
        old = mark_left(old, left_on=dt.date(2026, 10, 31), by=None, reason="Amehama")
        new = holding(hire_again(old, display_name="Mjomba", started_on=NOVEMBER, by=None))
    taken = correct(old, baba, "-5000.00", month=dt.date(2026, 10, 1))
    with pytest.raises(ValidationError) as refused:
        cross_out(taken, new)
    assert code_of(refused) == "correction.own"


@pytest.mark.parametrize("missing", THREE_KEYS)
def test_without_each_key_nobody_crosses_out(
    shop_a: Shop, wrong: PayCorrection, juma: StaffMember, missing: str
) -> None:
    # Meneja, without pay.approve, the owner's own, crosses out none, as he types none (Jack: A); nor anyone without one
    # of the two keys of pay.
    other = holding(job(shop_a, "Hamisi"), tuple(key for key in THREE_KEYS if key != missing))
    with pytest.raises(PermissionDenied):
        cross_out(wrong, other)
    assert counted(juma) == [Decimal("90000.00")]


def test_a_manager_crosses_out_none(shop_a: Shop, give_role: GiveRole, wrong: PayCorrection, juma: StaffMember) -> None:
    meneja = job(shop_a, "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    with pytest.raises(PermissionDenied):
        cross_out(wrong, meneja)
    assert counted(juma) == [Decimal("90000.00")]


def test_on_the_demo_the_ready_reason(settings: Settings, baba: StaffMember, wrong: PayCorrection) -> None:
    # Every visitor is the same Meneja, so a reason typed would show to the next: Advansi's ready one, kept as its code.
    settings.DEMO_SEED = True
    assert ready_correction_void_reasons() == list(DEMO_CORRECTION_VOID_REASONS) == ["wrong_amount"]
    with pytest.raises(ValidationError) as refused:
        cross_out(wrong, baba)
    assert {field: [e.code for e in errors] for field, errors in refused.value.error_dict.items()} == {
        "reason": ["demo.ready_reasons"]
    }
    assert cross_out(wrong, baba, "wrong_amount").void_reason == "wrong_amount"


def test_anywhere_else_no_ready_reason(settings: Settings) -> None:
    settings.DEMO_SEED = False
    assert ready_correction_void_reasons() == []


def test_a_crossing_out_tells_no_laptop(shop_a: Shop, baba: StaffMember, wrong: PayCorrection) -> None:
    # Pay never sits on a shared device (03 §6.1): no line in the change log.
    with shop_context(shop_a):
        lines = Change.objects.count()
    cross_out(wrong, baba)
    with shop_context(shop_a):
        assert Change.objects.count() == lines


def test_a_person_of_another_shop_is_a_bug(wrong: PayCorrection, staff_b: StaffMember) -> None:
    with pytest.raises(ShopMismatch, match="void_correction"):
        cross_out(wrong, staff_b)


@pytest.mark.django_db(transaction=True)
def test_two_crossing_out_at_once_stamp_once(
    baba: StaffMember, mjomba: StaffMember, juma: StaffMember, wrong: PayCorrection
) -> None:
    # Baba and Mjomba both tap Batilisha on Juma's + 90,000 at the same moment: Mjomba waits for Juma's row, which
    # Baba holds, then finds it crossed out, and is answered with Baba's stamp. One stamp, never two.
    def crosses() -> object:
        return cross_out(wrong, mjomba, "Sababu nyingine").voided_by_id

    with shop_context(juma.shop_id), transaction.atomic():
        cross_out(wrong, baba)
        thread, ended = in_another_transaction(crosses)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == [baba.pk]
