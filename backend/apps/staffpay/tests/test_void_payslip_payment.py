"""apps/staffpay/tests/test_void_payslip_payment.py — a payment marked by mistake, crossed out (WAGE-9; 02 §12, T2, A5):
void_payslip_payment (apps/staffpay/services/payment.py).

    08:10  Baba taps Lipa beside Juma, by M-Pesa, when he meant Baraka
    09:00  Batilisha: "Nilibonyeza mfanyakazi mwingine"
           → the payment stays, struck through, with who, when and why; Juma's payslip waits for Lipa again

Never one's own, never stamped twice, never brought back. The payslips are written straight in, as approving them is
WAGE-3's. The amounts are made up: the repo is public (rule 10).
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.control.models import Attachment, AttachmentKind
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import StaffMember
from apps.people.services import grant_permission, hire_again, mark_left
from apps.shops.models import Shop, Side
from apps.staffpay.models import PaymentMethod, Payslip, PayslipPayment
from apps.staffpay.services import (
    DEMO_PAYMENT_VOID_REASONS,
    PAYS,
    pay_payslip,
    ready_payment_void_reasons,
    void_payslip_payment,
)
from apps.staffpay.tests.days import job
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER = dt.date(2026, 11, 1)
WHY = "Nilibonyeza mfanyakazi mwingine"
DRAWING = b"\xff\xd8\xff\xe0" + b"Juma's signature, made up " * 20


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # The owner: every key.
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


@pytest.fixture
def meneja(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    # A manager with `pay.run` from his role and the two keys of pay from the owner.
    staff = job(shop_a, "Meneja")
    give_role(staff, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        for key in (Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE):
            grant_permission(staff, key, side=None, by=None)
    return staff


def slip(staff: StaffMember, by: StaffMember, total: str = "132000.00") -> Payslip:
    with shop_context(staff.shop_id):
        return Payslip.objects.create(
            shop_id=staff.shop_id, staff=staff, month=NOVEMBER, total=Decimal(total), created_by=by
        )


def paid(payslip: Payslip, by: StaffMember, number: str = "QK7H2M9XPL") -> PayslipPayment:
    with shop_context(payslip.shop_id):
        return pay_payslip(payslip, payment_id=uuid.uuid7(), method=PaymentMethod.MOBILE_MONEY, reference=number, by=by)


def cross_out(payment: PayslipPayment, by: StaffMember, reason: str = WHY) -> PayslipPayment:
    with shop_context(payment.shop_id):
        return void_payslip_payment(payment, reason=reason, by=by)


@pytest.fixture
def juma(shop_a: Shop, baba: StaffMember) -> Payslip:
    return slip(job(shop_a, "Juma"), baba)


@pytest.fixture
def wrong(juma: Payslip, baba: StaffMember) -> PayslipPayment:
    # Juma marked paid by mistake.
    return paid(juma, baba)


def test_a_payment_crossed_out_stays_with_who_when_and_why(
    juma: Payslip, baba: StaffMember, wrong: PayslipPayment
) -> None:
    # Struck through, never deleted: the page shows it as it was, and who crossed it out and why (T2).
    row = cross_out(wrong, baba, f"  {WHY}  ")
    assert (row.pk, row.voided_by_id, row.void_reason) == (wrong.pk, baba.pk, WHY)
    assert row.voided_at is not None
    assert (row.amount, row.reference, row.created_by_id) == (wrong.amount, wrong.reference, baba.pk)


def test_then_the_payslip_is_paid_again(juma: Payslip, baba: StaffMember, wrong: PayslipPayment) -> None:
    # Juma's payslip waits for its real payment, which the same number may now be, as the first counted for nothing.
    cross_out(wrong, baba)
    again = paid(juma, baba)
    with shop_context(juma.shop_id):
        counted = PayslipPayment.objects.filter(payslip=juma, voided_at__isnull=True)
        assert list(counted.values_list("pk", flat=True)) == [again.pk]


def test_a_signature_stays_with_its_payment(shop_a: Shop, baba: StaffMember, juma: Payslip) -> None:
    # Paid in cash, signed, then crossed out: the signature is kept, pinned to the struck payment, for good.
    with shop_context(shop_a):
        signed = pay_payslip(
            juma,
            payment_id=uuid.uuid7(),
            method=PaymentMethod.CASH,
            signature_id=uuid.uuid7(),
            signature=DRAWING,
            by=baba,
        )
    cross_out(signed, baba)
    with shop_context(shop_a):
        [kept] = Attachment.objects.filter(kind=AttachmentKind.SIGNATURE)
        assert (kept.subject_id, kept.file_removed_at) == (signed.pk, None)
        assert kept.file


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_crossing_out_says_why(baba: StaffMember, wrong: PayslipPayment, reason: str) -> None:
    # Said beside the reason's box (rule 7: always why).
    with pytest.raises(ValidationError) as refused:
        cross_out(wrong, baba, reason)
    assert [inner.code for inner in refused.value.error_dict["reason"]] == ["payment.reason_missing"]
    with shop_context(wrong.shop_id):
        assert PayslipPayment.objects.get(pk=wrong.pk).voided_at is None


def test_crossed_out_twice_is_stamped_once(
    juma: Payslip, baba: StaffMember, meneja: StaffMember, wrong: PayslipPayment
) -> None:
    # Sent twice, or by Meneja a moment after Baba: the first stamp stands, and the second is answered with it.
    first = cross_out(wrong, baba)
    second = cross_out(wrong, meneja, "Sababu nyingine")
    assert (second.voided_by_id, second.void_reason, second.voided_at) == (baba.pk, WHY, first.voided_at)


def test_nobody_crosses_out_their_own(shop_a: Shop, baba: StaffMember, meneja: StaffMember) -> None:
    # 02 A5: Meneja erasing that he was paid would let him be paid twice.
    own = paid(slip(meneja, baba, "250000.00"), baba)
    with pytest.raises(ValidationError) as refused:
        cross_out(own, meneja)
    assert refused.value.code == "payment.own"


def test_ones_own_is_the_persons_not_the_jobs(shop_a: Shop, give_role: GiveRole, baba: StaffMember) -> None:
    # Baraka left on the 14th and came back on the 16th as a manager (PPL-11): his old job's payment is his, all the
    # same.
    old = job(shop_a, "Baraka")
    with shop_context(shop_a):
        mark_left(old, left_on=dt.date(2026, 11, 14), by=None, reason="Ameacha kazi")
        new = hire_again(old, display_name="Baraka", started_on=dt.date(2026, 11, 16), by=None)
    give_role(new, RoleTemplate.OWNER, None)
    payment = paid(slip(old, baba, "62000.00"), baba)
    with pytest.raises(ValidationError) as refused:
        cross_out(payment, new)
    assert refused.value.code == "payment.own"


@pytest.mark.parametrize("missing", PAYS)
def test_without_each_key_nobody_crosses_out(
    shop_a: Shop, give_role: GiveRole, wrong: PayslipPayment, missing: Permission
) -> None:
    # The same keys as paying, on the whole shop.
    neema = job(shop_a, "Neema")
    give_role(neema, RoleTemplate.SELLER, None)
    with shop_context(shop_a):
        for key in PAYS:
            if key != missing:
                grant_permission(neema, key, side=None, by=None)
    with pytest.raises(PermissionDenied):
        cross_out(wrong, neema)
    with shop_context(shop_a):
        assert PayslipPayment.objects.get(pk=wrong.pk).voided_at is None
        grant_permission(neema, missing, side=None, by=None)
    assert cross_out(wrong, neema).voided_by_id == neema.pk


def test_on_the_demo_the_ready_reason(settings: Settings, baba: StaffMember, wrong: PayslipPayment) -> None:
    # Every demo visitor is the same Meneja (OPS-3): typed words would show to the next one, so the sheet offers a ready
    # reason, and only it is taken.
    assert ready_payment_void_reasons() == []
    settings.DEMO_SEED = True
    assert ready_payment_void_reasons() == ["marked_by_mistake"] == list(DEMO_PAYMENT_VOID_REASONS)
    with pytest.raises(ValidationError) as refused:
        cross_out(wrong, baba)
    assert [inner.code for inner in refused.value.error_dict["reason"]] == ["demo.ready_reasons"]
    assert cross_out(wrong, baba, "marked_by_mistake").void_reason == "marked_by_mistake"


def test_a_person_of_another_shop_is_a_bug(wrong: PayslipPayment, staff_b: StaffMember) -> None:
    with pytest.raises(ShopMismatch, match="void_payslip_payment"):
        cross_out(wrong, staff_b)


@pytest.mark.django_db(transaction=True)
def test_a_payment_beside_a_crossing_out_waits_for_it(
    juma: Payslip, baba: StaffMember, meneja: StaffMember, wrong: PayslipPayment
) -> None:
    # Baba crosses out Juma's wrong payment as Meneja taps Nimemlipa for Juma's real one: Meneja waits for the crossing
    # out, then pays, as the payslip is no longer paid. Neither is lost, and the payslip is paid once.
    def pays() -> str:
        try:
            paid(juma, meneja, "QK7H2N4ZTR")
        except ValidationError as refusal:
            return str(refusal.code)
        return "paid"

    with shop_context(juma.shop_id), transaction.atomic():
        cross_out(wrong, baba)
        thread, ended = in_another_transaction(pays)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["paid"]
    with shop_context(juma.shop_id):
        assert PayslipPayment.objects.filter(payslip=juma, voided_at__isnull=True).count() == 1
