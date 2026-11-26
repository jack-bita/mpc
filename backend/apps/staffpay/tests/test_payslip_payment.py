"""apps/staffpay/tests/test_payslip_payment.py — a payslip handed out, as the database keeps it (WAGE-9; 02 §12, A5):
the rules the table holds on a payment (PayslipPayment, apps/staffpay/models.py).

    payslip         amount      how           number      paid by  crossed out
    Juma, Novemba   132,000.00  mobile_money  QK7H2M9XPL  Baba     by Baba: "Nilibonyeza mfanyakazi mwingine"
    Juma, Novemba   132,000.00  cash          —           Baba                       ← with Juma's signature

Money, so a ledger (T2): a row is written once and never changed or deleted, only crossed out once, with who, when and
why, and the payslip paid again. Paying, with who may, the signature and the lock, is the service's (pay_payslip); these
tests write rows straight in, as the table's rules hold whoever writes. The amounts are made up: the repo is public
(rule 10).
"""

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import AppendOnlyError
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.staffpay.models import NoSignature, PaymentMethod, Payslip, PayslipPayment
from apps.staffpay.tests.days import job

pytestmark = pytest.mark.django_db

NOVEMBER = dt.date(2026, 11, 1)
CASH, MOBILE, BANK = PaymentMethod.CASH, PaymentMethod.MOBILE_MONEY, PaymentMethod.BANK
NUMBER = "QK7H2M9XPL"


def _slip(shop: Shop, staff: StaffMember, by: StaffMember) -> Payslip:
    # Juma's November, approved alone (no run), as the table needs no more of it.
    row = Payslip(shop=shop, staff=staff, month=NOVEMBER, total=Decimal("132000.00"), created_by=by)
    with shop_context(shop):
        row.full_clean()
        row.save()
    return row


def _payment(slip: Payslip, by: StaffMember | None, **other: Any) -> PayslipPayment:
    facts = {
        "shop": slip.shop,
        "payslip": slip,
        "staff": slip.staff,
        "amount": slip.total,
        "method": MOBILE,
        "reference": NUMBER,
    }
    return PayslipPayment(**(facts | other), created_by=by)


def _kept(row: PayslipPayment) -> PayslipPayment:
    # Checked by the model's own rules, then saved, inside its shop, as the service does.
    with shop_context(row.shop):
        row.full_clean()
        row.save()
    return row


@pytest.fixture
def slip(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> Payslip:
    # Juma (staff_a), approved by Baba (staff_a2).
    return _slip(shop_a, staff_a, staff_a2)


@pytest.fixture
def paid(slip: Payslip, staff_a2: StaffMember) -> PayslipPayment:
    # Juma's November, by M-Pesa, marked by Baba.
    return _kept(_payment(slip, staff_a2))


def _void(row: PayslipPayment, by: StaffMember, why: str = "Nilibonyeza mfanyakazi mwingine") -> None:
    with shop_context(row.shop):
        PayslipPayment.objects.filter(pk=row.pk).update(voided_at=timezone.now(), voided_by=by, void_reason=why)


def test_a_payslip_is_paid_once(slip: Payslip, staff_a2: StaffMember, paid: PayslipPayment) -> None:
    # Nobody is paid a month twice: a second payment of the same payslip is refused, in the model's own words first,
    # with the code the page translates, then by the database, whatever writes past the model.
    second = _payment(slip, staff_a2, method=CASH, reference="")
    with shop_context(slip.shop):
        with pytest.raises(ValidationError) as refused:
            second.full_clean()
        assert refused.value.error_dict["__all__"][0].code == "payment.already_paid"
        with pytest.raises(IntegrityError, match="staffpay_payslippayment_one_counted"), transaction.atomic():
            second.save()


def test_one_crossed_out_lets_it_be_paid_again(slip: Payslip, staff_a2: StaffMember, paid: PayslipPayment) -> None:
    # A payment marked by mistake counts for nothing once crossed out: the payslip waits for its real one, and both rows
    # stay, the wrong one struck through.
    _void(paid, staff_a2)
    again = _kept(_payment(slip, staff_a2, reference="QK7H2N4ZTR"))
    with shop_context(slip.shop):
        assert set(PayslipPayment.objects.filter(payslip=slip).values_list("pk", flat=True)) == {paid.pk, again.pk}


def test_a_number_proves_one_payment(
    shop_a: Shop, staff_a2: StaffMember, slip: Payslip, paid: PayslipPayment, juma2: StaffMember
) -> None:
    # The same M-Pesa code on two payslips would let one real payment stand for two (01 §7.5): refused, with its code.
    other = _payment(_slip(shop_a, juma2, staff_a2), staff_a2)
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            other.full_clean()
        assert refused.value.error_dict["__all__"][0].code == "payment.reference_used"
        with pytest.raises(IntegrityError, match="staffpay_payslippayment_number_counted_once"), transaction.atomic():
            other.save()


def test_a_number_is_counted_by_its_way_and_shop(
    shop_a: Shop, shop_b: Shop, staff_a2: StaffMember, staff_b: StaffMember, paid: PayslipPayment, juma2: StaffMember
) -> None:
    # A bank numbers its transfers, M-Pesa its own: the same letters by each are two payments. Another shop's books are
    # its own (T1). And once the first is crossed out, its number is free for the payment it really was.
    _kept(_payment(_slip(shop_a, juma2, staff_a2), staff_a2, method=BANK))
    _kept(_payment(_slip(shop_b, job(shop_b, "Neema"), staff_b), staff_b))
    _void(paid, staff_a2)
    _kept(_payment(paid.payslip, staff_a2))


def test_nothing_handed_over_is_no_payment(slip: Payslip, staff_a2: StaffMember) -> None:
    # A payslip of 0 is paid by nobody (WAGE-9), and money handed over is never below 0.
    for amount in ("0.00", "-500.00"):
        with (
            shop_context(slip.shop),
            pytest.raises(IntegrityError, match="staffpay_payslippayment_above_zero"),
            transaction.atomic(),
        ):
            _payment(slip, staff_a2, amount=Decimal(amount)).save()


def test_cash_has_no_number(slip: Payslip, staff_a2: StaffMember) -> None:
    # In cash the proof is the signature; and on the demo, the word that none is kept.
    _kept(_payment(slip, staff_a2, method=CASH, reference="", no_signature=NoSignature.DEMO))
    with shop_context(slip.shop):
        PayslipPayment.objects.filter(payslip=slip).update(
            voided_at=timezone.now(), voided_by=staff_a2, void_reason="Kosa"
        )
        with (
            pytest.raises(IntegrityError, match="staffpay_payslippayment_proof_fits_its_way"),
            transaction.atomic(),
        ):
            _payment(slip, staff_a2, method=CASH).save()


@pytest.mark.parametrize("method", [MOBILE, BANK])
@pytest.mark.parametrize(("number", "no_signature"), [("", ""), ("   ", ""), (NUMBER, NoSignature.DEMO)])
def test_mpesa_and_a_bank_have_a_number_and_no_signature(
    slip: Payslip, staff_a2: StaffMember, method: str, number: str, no_signature: str
) -> None:
    # Their proof is the number the owner finds on his statement; no signature was ever theirs to keep or skip.
    with (
        shop_context(slip.shop),
        pytest.raises(IntegrityError, match="staffpay_payslippayment_proof_fits_its_way"),
        transaction.atomic(),
    ):
        _payment(slip, staff_a2, method=method, reference=number, no_signature=no_signature).save()


def test_a_payment_says_who_handed_it_out(slip: Payslip) -> None:
    # Handing out pay is somebody's word, never nobody's.
    with (
        shop_context(slip.shop),
        pytest.raises(IntegrityError, match="staffpay_payslippayment_paid_by_someone"),
        transaction.atomic(),
    ):
        _payment(slip, None).save()


def test_nobody_marks_their_own_pay_paid(slip: Payslip, staff_a: StaffMember) -> None:
    # 02 A5: Juma marking his own November paid would prove nothing, signature or not.
    with (
        shop_context(slip.shop),
        pytest.raises(IntegrityError, match="staffpay_payslippayment_paid_by_another"),
        transaction.atomic(),
    ):
        _payment(slip, staff_a).save()


def test_nobody_crosses_out_their_own(slip: Payslip, staff_a: StaffMember, paid: PayslipPayment) -> None:
    # Nor erasing that he was paid, to be paid twice.
    with (
        shop_context(slip.shop),
        pytest.raises(IntegrityError, match="staffpay_payslippayment_voided_by_another"),
        transaction.atomic(),
    ):
        _void(paid, staff_a)


def test_a_payment_is_never_changed_or_deleted(
    slip: Payslip, staff_a: StaffMember, staff_a2: StaffMember, paid: PayslipPayment
) -> None:
    # A ledger (rule 2, T2): a wrong one is crossed out and made again, never changed. The model refuses first, with a
    # clear message; the trigger in the table's migration refuses in PostgreSQL, whatever sends the change.
    with shop_context(slip.shop):
        paid.amount = Decimal("1000.00")
        with pytest.raises(AppendOnlyError):
            paid.save()
        with pytest.raises(AppendOnlyError):
            paid.delete()
        rows = PayslipPayment.objects.filter(pk=paid.pk)
        for change in (
            {"amount": Decimal("1000.00")},
            {"method": CASH, "reference": ""},
            {"reference": "QK7H2N4ZTR"},
            {"no_signature": NoSignature.DEMO},
            # Who handed it out, and to whom: Juma's pay moved onto Baba's name.
            {"created_by": staff_a},
            {"staff": staff_a2},
        ):
            with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
                rows.update(**change)
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            rows.delete()
        kept = PayslipPayment.objects.get(pk=paid.pk)
    assert (kept.amount, kept.reference, kept.created_by_id) == (Decimal("132000.00"), NUMBER, staff_a2.pk)


def test_a_payment_is_crossed_out_once(slip: Payslip, staff_a2: StaffMember, paid: PayslipPayment) -> None:
    # Stamped once with who, when and why, then frozen: nobody can later rewrite who crossed it out, or why, nor bring
    # it back beside the payment made in its place (T2).
    _void(paid, staff_a2)
    with shop_context(slip.shop):
        rows = PayslipPayment.objects.filter(pk=paid.pk)
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(void_reason="Sababu nyingine")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(voided_at=None, voided_by=None, void_reason="")
        paid.refresh_from_db()
    assert (paid.voided_by_id, paid.void_reason) == (staff_a2.pk, "Nilibonyeza mfanyakazi mwingine")


@pytest.mark.parametrize(("who", "why"), [(False, "Kosa"), (True, ""), (True, "  ")])
def test_a_crossing_out_says_who_and_why(
    slip: Payslip, staff_a2: StaffMember, paid: PayslipPayment, who: bool, why: str
) -> None:
    # T2: one crossed out with no person, or no reason but spaces, would hide what happened to the money. The void rule
    # only checks that the stamp is filled once, so the table holds the rest itself.
    stamp = {"voided_at": timezone.now(), "void_reason": why, **({"voided_by": staff_a2} if who else {})}
    with (
        shop_context(slip.shop),
        pytest.raises(IntegrityError, match="staffpay_payslippayment_void_complete"),
        transaction.atomic(),
    ):
        PayslipPayment.objects.filter(pk=paid.pk).update(**stamp)


@pytest.fixture
def juma2(shop_a: Shop) -> StaffMember:
    # A second worker of shop A, with a payslip of his own.
    return job(shop_a, "Baraka")
