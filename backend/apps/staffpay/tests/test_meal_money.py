"""apps/staffpay/tests/test_meal_money.py — the day's meal money (WAGE-7; 02 §12): the rules the table keeps on a row
(MealMoney, apps/staffpay/models.py).

    date    amount     note              typed by   crossed out
    23 Nov   5,000.00  Unga na maharage  Asha
    23 Nov  30,000.00  Nyama             Asha       by Baba: "Sifuri moja zaidi"
    23 Nov   3,000.00  Nyama             Asha                                      ← so Monday's money is 8,000

What the shop spends on the workers' meals on one day; they pay for it out of their pay. Money, so a ledger (T2): a row
is written once and never changed or deleted, only crossed out once, with who, when and why, and typed again. Typing
one and crossing one out, with who may, are the services' (record_meal_money and void_meal_money); these tests write
rows straight in, as the table's rules hold whoever writes. The amounts are made up: the repo is public (rule 10).
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
from apps.staffpay.models import MealMoney

pytestmark = pytest.mark.django_db

MONDAY = dt.date(2026, 11, 23)


def _row(shop: Shop, by: StaffMember | None, amount: str = "5000.00", note: str = "Unga na maharage") -> MealMoney:
    return MealMoney(shop=shop, date=MONDAY, amount=Decimal(amount), note=note, created_by=by)


@pytest.fixture
def typed(shop_a: Shop, staff_a: StaffMember) -> MealMoney:
    # Monday's flour, as the table keeps it: checked by the model's own rules, then saved, inside its shop.
    row = _row(shop_a, staff_a)
    with shop_context(shop_a):
        row.full_clean()
        row.save()
    return row


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "5000.50"])
def test_meal_money_is_whole_shillings_above_nothing(shop_a: Shop, staff_a: StaffMember, amount: str) -> None:
    # A day's meals cost more than nothing, and the shop's money has no cents (Jack, 16 Nov 2026), so 5,000.50 is a
    # typo: the model's check names it, with the code the page translates.
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        _row(shop_a, staff_a, amount).full_clean()
    codes = {error.code for errors in refused.value.error_dict.values() for error in errors}
    assert codes == {"meal_money.amount_invalid"}


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "5000.50"])
def test_the_database_refuses_such_money_too(shop_a: Shop, staff_a: StaffMember, amount: str) -> None:
    # The same two rules in PostgreSQL, whatever writes the row: a save that skips the model's checks still fails. A
    # negative row would give the workers money back, and nobody would see why.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_mealmoney_(above_zero|whole_shillings)"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, amount).save()


def test_meal_money_says_who_typed_it(shop_a: Shop) -> None:
    # Every worker pays a share of it, so it never stands with nobody's name on it: not even the system types one.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_mealmoney_typed_by_someone"),
        transaction.atomic(),
    ):
        _row(shop_a, None).save()


def test_a_day_may_have_several(shop_a: Shop, staff_a: StaffMember, typed: MealMoney) -> None:
    # Flour in the morning, meat at noon: two rows of one day, the same amount even, as nothing says two meals' money
    # differ. The day's money is their sum (02 §12).
    with shop_context(shop_a):
        second = _row(shop_a, staff_a, note="Nyama")
        second.full_clean()
        second.save()
        assert MealMoney.objects.filter(date=MONDAY).count() == 2


def test_meal_money_is_never_changed_or_deleted(shop_a: Shop, typed: MealMoney) -> None:
    # A ledger (rule 2, T2): a wrong amount is crossed out and typed again, never changed. The model refuses first, with
    # a clear message; the trigger in the table's migration refuses in PostgreSQL, whatever sends the change.
    with shop_context(shop_a):
        typed.amount = Decimal("500.00")
        with pytest.raises(AppendOnlyError):
            typed.save()
        with pytest.raises(AppendOnlyError):
            typed.delete()
        rows = MealMoney.objects.filter(pk=typed.pk)
        for change in (
            {"amount": Decimal("500.00")},
            {"date": MONDAY - dt.timedelta(days=1)},
            {"note": "Nyama"},
            {"created_by": None},
        ):
            with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
                rows.update(**change)
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            rows.delete()
        assert MealMoney.objects.get(pk=typed.pk).amount == Decimal("5000.00")


def test_meal_money_is_crossed_out_once(shop_a: Shop, staff_a2: StaffMember, typed: MealMoney) -> None:
    # Stamped once with who, when and why, then frozen: nobody can later rewrite who crossed it out, or why, nor bring
    # it back (T2).
    with shop_context(shop_a):
        rows = MealMoney.objects.filter(pk=typed.pk)
        rows.update(voided_at=timezone.now(), voided_by=staff_a2, void_reason="Sifuri moja zaidi")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(void_reason="Sababu nyingine")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(voided_at=None, voided_by=None, void_reason="")
        typed.refresh_from_db()
    assert (typed.voided_by_id, typed.void_reason) == (staff_a2.pk, "Sifuri moja zaidi")


@pytest.mark.parametrize(("who", "why"), [(False, "Sifuri moja zaidi"), (True, ""), (True, "  ")])
def test_a_crossing_out_says_who_and_why(
    shop_a: Shop, staff_a2: StaffMember, typed: MealMoney, who: bool, why: str
) -> None:
    # T2: money crossed out with no person, or no reason but spaces, would hide what happened to it. The void rule only
    # checks that the stamp is filled once, so the table holds the rest itself (CORE-3's Watch out).
    stamp = {"voided_at": timezone.now(), "void_reason": why, **({"voided_by": staff_a2} if who else {})}
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_mealmoney_void_complete"),
        transaction.atomic(),
    ):
        MealMoney.objects.filter(pk=typed.pk).update(**stamp)


def test_a_reason_alone_is_no_crossing_out(shop_a: Shop, typed: MealMoney) -> None:
    # Half a stamp would leave the row counting while the page showed a reason: refused, by the trigger first.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="a void must fill voided_at"),
        transaction.atomic(),
    ):
        MealMoney.objects.filter(pk=typed.pk).update(void_reason="Sifuri moja zaidi")
