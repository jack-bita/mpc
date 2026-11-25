"""apps/staffpay/tests/test_advance.py — money given to a worker before payday (WAGE-8; 02 §12): the rules the table
keeps on a row (Advance, apps/staffpay/models.py).

    who    date     amount     note          typed by   crossed out
    Juma   10 Nov   20,000.00  Ada ya shule  Meneja
    Juma   16 Nov  300,000.00                Meneja     by Baba: "Sifuri moja zaidi"
    Juma   16 Nov   30,000.00                Meneja                                    ← so Juma was given 50,000

It comes off the worker's pay, so it is money, and a ledger (T2): a row is written once and never changed or deleted,
only crossed out once, with who, when and why, and typed again. Nobody types or crosses out their own (Jack, WAGE-8: A).
Typing one and crossing one out, with who may, are the services' (record_advance and void_advance); these tests write
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
from apps.staffpay.models import Advance

pytestmark = pytest.mark.django_db

TENTH = dt.date(2026, 11, 10)


def _row(
    shop: Shop, staff: StaffMember, by: StaffMember | None, amount: str = "20000.00", note: str = "Ada ya shule"
) -> Advance:
    return Advance(shop=shop, staff=staff, date=TENTH, amount=Decimal(amount), note=note, created_by=by)


@pytest.fixture
def given(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> Advance:
    # Juma's 20,000 (staff_a), typed by Meneja (staff_a2), as the table keeps it: checked by the model's own rules, then
    # saved, inside its shop.
    row = _row(shop_a, staff_a, staff_a2)
    with shop_context(shop_a):
        row.full_clean()
        row.save()
    return row


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "20000.50"])
def test_an_advance_is_whole_shillings_above_nothing(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, amount: str
) -> None:
    # Money was given, so it is more than nothing, and the shop's money has no cents (Jack, 16 Nov 2026), so 20,000.50
    # is a typo: the model's check names it, with the code the page translates.
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        _row(shop_a, staff_a, staff_a2, amount).full_clean()
    codes = {error.code for errors in refused.value.error_dict.values() for error in errors}
    assert codes == {"advance.amount_invalid"}


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "20000.50"])
def test_the_database_refuses_such_an_advance_too(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, amount: str
) -> None:
    # The same two rules in PostgreSQL, whatever writes the row: a save that skips the model's checks still fails. One
    # below 0 would add to the worker's pay, and nobody would see why.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_advance_(above_zero|whole_shillings)"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, staff_a2, amount).save()


def test_an_advance_is_at_most_ten_million(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # More than any month's pay, so a slip of the zeros; and a few such rows could add up to more than a column of money
    # holds, and stop Mishahara from opening. Named with its own code by the model's check; held in PostgreSQL too.
    row = _row(shop_a, staff_a, staff_a2, "10000001.00")
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            row.full_clean()
        assert [error.code for error in refused.value.error_dict["__all__"]] == ["advance.amount_too_big"]
        with pytest.raises(IntegrityError, match="staffpay_advance_at_most"), transaction.atomic():
            row.save()
        _row(shop_a, staff_a, staff_a2, "10000000.00").save()


def test_an_advance_says_who_typed_it(shop_a: Shop, staff_a: StaffMember) -> None:
    # It comes off a worker's pay, so it never stands with nobody's name on it: not even the system types one.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_advance_typed_by_someone"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, None).save()


def test_nobody_types_their_own(shop_a: Shop, staff_a: StaffMember) -> None:
    # Jack: A. Nobody gives themself the shop's money on their own word. The table holds what one row can say, the job;
    # that a person hired again types none for their other job either is the service's check.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_advance_typed_by_another"),
        transaction.atomic(),
    ):
        _row(shop_a, staff_a, staff_a).save()


def test_nobody_crosses_out_their_own(shop_a: Shop, staff_a: StaffMember, given: Advance) -> None:
    # Nor erases what they took: Juma crossing out Juma's 20,000 would be paid it twice.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_advance_voided_by_another"),
        transaction.atomic(),
    ):
        Advance.objects.filter(pk=given.pk).update(
            voided_at=timezone.now(), voided_by=staff_a, void_reason="Sijachukua"
        )


def test_a_worker_may_be_given_several(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, given: Advance
) -> None:
    # Twice on one day, the same amount even: nothing says two gifts of money differ. The month's is their sum.
    with shop_context(shop_a):
        second = _row(shop_a, staff_a, staff_a2)
        second.full_clean()
        second.save()
        assert Advance.objects.filter(staff=staff_a, date=TENTH).count() == 2


def test_an_advance_is_never_changed_or_deleted(
    shop_a: Shop, staff_a2: StaffMember, given: Advance, staff_a: StaffMember
) -> None:
    # A ledger (rule 2, T2): a wrong one is crossed out and typed again, never changed. The model refuses first, with a
    # clear message; the trigger in the table's migration refuses in PostgreSQL, whatever sends the change.
    with shop_context(shop_a):
        given.amount = Decimal("500.00")
        with pytest.raises(AppendOnlyError):
            given.save()
        with pytest.raises(AppendOnlyError):
            given.delete()
        rows = Advance.objects.filter(pk=given.pk)
        for change in (
            {"amount": Decimal("500.00")},
            {"date": TENTH - dt.timedelta(days=1)},
            {"note": "Kodi"},
            # Whose it is too: Juma's 20,000 moved onto Meneja's pay.
            {"staff": staff_a2},
            {"created_by": None},
        ):
            with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
                rows.update(**change)
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            rows.delete()
        kept = Advance.objects.get(pk=given.pk)
    assert (kept.amount, kept.staff_id) == (Decimal("20000.00"), staff_a.pk)


def test_an_advance_is_crossed_out_once(shop_a: Shop, staff_a2: StaffMember, given: Advance) -> None:
    # Stamped once with who, when and why, then frozen: nobody can later rewrite who crossed it out, or why, nor bring
    # it back (T2).
    with shop_context(shop_a):
        rows = Advance.objects.filter(pk=given.pk)
        rows.update(voided_at=timezone.now(), voided_by=staff_a2, void_reason="Sifuri moja zaidi")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(void_reason="Sababu nyingine")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(voided_at=None, voided_by=None, void_reason="")
        given.refresh_from_db()
    assert (given.voided_by_id, given.void_reason) == (staff_a2.pk, "Sifuri moja zaidi")


@pytest.mark.parametrize(("who", "why"), [(False, "Sifuri moja zaidi"), (True, ""), (True, "  ")])
def test_a_crossing_out_says_who_and_why(
    shop_a: Shop, staff_a2: StaffMember, given: Advance, who: bool, why: str
) -> None:
    # T2: one crossed out with no person, or no reason but spaces, would hide what happened to the money. The void rule
    # only checks that the stamp is filled once, so the table holds the rest itself (CORE-3's Watch out).
    stamp = {"voided_at": timezone.now(), "void_reason": why, **({"voided_by": staff_a2} if who else {})}
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_advance_void_complete"),
        transaction.atomic(),
    ):
        Advance.objects.filter(pk=given.pk).update(**stamp)


def test_a_reason_alone_is_no_crossing_out(shop_a: Shop, given: Advance) -> None:
    # Half a stamp would leave the row counting while the page showed a reason: refused, by the trigger first.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="a void must fill voided_at"),
        transaction.atomic(),
    ):
        Advance.objects.filter(pk=given.pk).update(void_reason="Sifuri moja zaidi")
