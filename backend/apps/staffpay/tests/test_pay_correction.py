"""apps/staffpay/tests/test_pay_correction.py — a mistake found after a month's pay was approved, put right in a later
month's pay (WAGE-10; 02 §12, A3): the rules the table keeps on a row (PayCorrection, apps/staffpay/models.py).

    who    month     amount      reason                                 typed by  crossed out
    Juma   Desemba   +90,000.00  Novemba: siku ya 12/11 haikuhesabiwa   Baba      by Baba: "Kiasi kimekosewa"
    Juma   Desemba    +9,000.00  Novemba: siku ya 12/11 haikuhesabiwa   Baba
    Asha   Desemba    -5,000.00  Novemba: alilipwa zaidi                Baba

It changes what a worker is owed, so it is money, and a ledger (T2): a row is written once and never changed or
deleted, only crossed out once, with who, when and why, and typed again. Nobody types or crosses out their own (Jack,
WAGE-10: A). Typing one and crossing one out, with who may and in which month, are the services' (record_correction and
void_correction); these tests write rows straight in, as the table's rules hold whoever writes. The amounts are made
up: the repo is public (rule 10).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import AppendOnlyError
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.staffpay.models import PayCorrection

pytestmark = pytest.mark.django_db

DECEMBER = dt.date(2026, 12, 1)
REASON = "Novemba: siku ya 12/11 haikuhesabiwa"


def _row(
    shop: Shop,
    staff: StaffMember,
    by: StaffMember | None,
    amount: str = "9000.00",
    reason: str = REASON,
    month: dt.date = DECEMBER,
) -> PayCorrection:
    return PayCorrection(shop=shop, staff=staff, month=month, amount=Decimal(amount), reason=reason, created_by=by)


def _codes(refused: ValidationError) -> set[str | None]:
    return {error.code for errors in refused.error_dict.values() for error in errors}


@pytest.fixture
def typed(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> PayCorrection:
    # Juma's + 9,000 (staff_a), typed by Baba (staff_a2), as the table keeps it: checked by the model's own rules, then
    # saved, inside its shop.
    row = _row(shop_a, staff_a, staff_a2)
    with shop_context(shop_a):
        row.full_clean()
        row.save()
    return row


@pytest.mark.parametrize("amount", ["9000.00", "-5000.00", "10000000.00", "-10000000.00"])
def test_a_correction_adds_or_takes_off(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, amount: str) -> None:
    # Juma short 9,000 is + 9,000; Asha paid 5,000 too much is − 5,000. Ten million either way is the most, and kept.
    row = _row(shop_a, staff_a, staff_a2, amount)
    with shop_context(shop_a):
        row.full_clean()
        row.save()
        assert PayCorrection.objects.get(pk=row.pk).amount == Decimal(amount)


@pytest.mark.parametrize("amount", ["0.00", "9000.50", "-9000.50"])
def test_a_correction_is_whole_shillings_and_never_nothing(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, amount: str
) -> None:
    # A correction of 0 corrects nothing, and the shop's money has no cents (Jack, 16 Nov 2026): the model's check names
    # it, with the code the page translates.
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        _row(shop_a, staff_a, staff_a2, amount).full_clean()
    assert _codes(refused.value) == {"correction.amount_invalid"}


@pytest.mark.parametrize("amount", ["0.00", "9000.50", "-9000.50"])
def test_the_database_refuses_such_a_correction_too(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, amount: str
) -> None:
    # The same rules in PostgreSQL, whatever writes the row: a save that skips the model's checks still fails. FLOOR of
    # -9000.50 is -9001, so cents below 0 are caught as surely as above it.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_paycorrection_(not_zero|whole_shillings)"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, staff_a2, amount).save()


@pytest.mark.parametrize("amount", ["10000001.00", "-10000001.00"])
def test_a_correction_is_at_most_ten_million_either_way(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, amount: str
) -> None:
    # More than any month's pay, so a slip of the zeros, as an advance's rule says. Named with its own code by the
    # model's check; held in PostgreSQL too.
    row = _row(shop_a, staff_a, staff_a2, amount)
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            row.full_clean()
        assert _codes(refused.value) == {"correction.amount_too_big"}
        with pytest.raises(IntegrityError, match="staffpay_paycorrection_at_most"), transaction.atomic():
            row.save()


@pytest.mark.parametrize(("reason", "code"), [("", "blank"), ("   ", "correction.reason_missing")])
def test_a_correction_says_why(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, reason: str, code: str
) -> None:
    # A line on a payslip nobody can explain is a number the worker must take on trust. An empty box is the field's own
    # "blank"; spaces alone pass it, so the rule names them. The service trims and asks first, in its own words; the
    # database holds the rule for whatever writes past it.
    row = _row(shop_a, staff_a, staff_a2, reason=reason)
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            row.full_clean()
        assert _codes(refused.value) == {code}
        with pytest.raises(IntegrityError, match="staffpay_paycorrection_says_why"), transaction.atomic():
            row.save()


def test_a_month_is_its_first_day(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # One month, one way to write it, so a month's corrections are read with one equality, as a run's month is.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_paycorrection_month_first_day"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, staff_a2, month=dt.date(2026, 12, 3)).save()


def test_a_correction_says_who_typed_it(shop_a: Shop, staff_a: StaffMember) -> None:
    # It changes a worker's pay, so it never stands with nobody's name on it: not even the system types one.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_paycorrection_typed_by_someone"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, None).save()


def test_nobody_types_their_own(shop_a: Shop, staff_a: StaffMember) -> None:
    # Jack: A. Nobody raises their own pay on their own word. The table holds what one row can say, the job; that a
    # person hired again types none for their other job either is the service's check.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_paycorrection_typed_by_another"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, staff_a).save()


def test_nobody_crosses_out_their_own(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # Nor takes back a deduction from their own pay: Juma crossing out Juma's − 5,000 would be paid it after all.
    with shop_context(shop_a):
        taken = _row(shop_a, staff_a, staff_a2, "-5000.00")
        taken.save()
        with (
            pytest.raises(IntegrityError, match="staffpay_paycorrection_voided_by_another"),
            transaction.atomic(),
        ):
            PayCorrection.objects.filter(pk=taken.pk).update(
                voided_at=timezone.now(), voided_by=staff_a, void_reason="Si kweli"
            )


def test_a_worker_may_have_several(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, typed: PayCorrection
) -> None:
    # Two mistakes of November, the same amount even: nothing says two corrections differ. The month counts both.
    with shop_context(shop_a):
        second = _row(shop_a, staff_a, staff_a2)
        second.full_clean()
        second.save()
        assert PayCorrection.objects.filter(staff=staff_a, month=DECEMBER).count() == 2


def test_a_correction_is_never_changed_or_deleted(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, typed: PayCorrection
) -> None:
    # A ledger (rule 2, T2): a wrong one is crossed out and typed again, never changed. The model refuses first, with a
    # clear message; the trigger in the table's migration refuses in PostgreSQL, whatever sends the change.
    with shop_context(shop_a):
        typed.amount = Decimal("90000.00")
        with pytest.raises(AppendOnlyError):
            typed.save()
        with pytest.raises(AppendOnlyError):
            typed.delete()
        rows = PayCorrection.objects.filter(pk=typed.pk)
        for change in (
            {"amount": Decimal("90000.00")},
            {"month": dt.date(2027, 1, 1)},
            {"reason": "Sababu nyingine"},
            # Whose it is too: Juma's + 9,000 moved onto Baba's pay.
            {"staff": staff_a2},
            {"created_by": None},
        ):
            with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
                rows.update(**change)
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            rows.delete()
        kept = PayCorrection.objects.get(pk=typed.pk)
    assert (kept.amount, kept.staff_id, kept.reason) == (Decimal("9000.00"), staff_a.pk, REASON)


def test_a_correction_is_crossed_out_once(shop_a: Shop, staff_a2: StaffMember, typed: PayCorrection) -> None:
    # Stamped once with who, when and why, then frozen: nobody can later rewrite who crossed it out, or why, nor bring
    # it back (T2).
    with shop_context(shop_a):
        rows = PayCorrection.objects.filter(pk=typed.pk)
        rows.update(voided_at=timezone.now(), voided_by=staff_a2, void_reason="Kiasi kimekosewa")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(void_reason="Sababu nyingine")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(voided_at=None, voided_by=None, void_reason="")
        typed.refresh_from_db()
    assert (typed.voided_by_id, typed.void_reason) == (staff_a2.pk, "Kiasi kimekosewa")


@pytest.mark.parametrize(("who", "why"), [(False, "Kiasi kimekosewa"), (True, ""), (True, "  ")])
def test_a_crossing_out_says_who_and_why(
    shop_a: Shop, staff_a2: StaffMember, typed: PayCorrection, who: bool, why: str
) -> None:
    # T2: one crossed out with no person, or no reason but spaces, would hide what happened to the pay. The void rule
    # only checks that the stamp is filled once, so the table holds the rest itself (CORE-3's Watch out).
    stamp = {"voided_at": timezone.now(), "void_reason": why, **({"voided_by": staff_a2} if who else {})}
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_paycorrection_void_complete"),
        transaction.atomic(),
    ):
        PayCorrection.objects.filter(pk=typed.pk).update(**stamp)


def test_a_reason_alone_is_no_crossing_out(shop_a: Shop, typed: PayCorrection) -> None:
    # Half a stamp would leave the row counting while the page showed a reason: refused, by the trigger first.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="a void must fill voided_at"),
        transaction.atomic(),
    ):
        PayCorrection.objects.filter(pk=typed.pk).update(void_reason="Kiasi kimekosewa")
