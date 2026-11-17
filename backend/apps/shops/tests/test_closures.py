"""apps/shops/tests/test_closures.py — a closure holds the days the whole shop is closed (ATT-8, 02 §12).

A closure runs from its first day to its last, both closed: a public holiday is one day, a family funeral a few.

    20/11 – 24/11   Msiba wa bibi      active     → 20, 21, 22, 23 and 24 are closed
    25/12 – 26/12   Krismasi           cancelled  → open: a cancelled closure closes nothing

The database itself keeps the closures true, whoever writes them: a last day before the first, a blank name, and two
active closures of one shop that share a day are each refused. These tests write rows straight to the table, past the
services (ATT-8's later steps), so they prove the database's own rules; the services' checks have their own tests.

closed_days answers ATT-4's question: which days in this span was the shop closed?
"""

from datetime import date, datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.tenancy import ShopMismatch, shop_context, system_context
from apps.shops.models import Closure, ClosureStatus, Shop
from apps.shops.selectors import closed_days

pytestmark = pytest.mark.django_db


def nov(day: int) -> date:
    return date(2026, 11, day)


def checked(shop: Shop, first: date, last: date, *, name: str = "Msiba wa bibi", status: str = "active") -> Closure:
    # A closure checked the way a service checks one (full_clean: the fields, clean() and every rule in Meta), then
    # saved. The rules' codes come back as a ValidationError, before anything is written.
    with shop_context(shop):
        row = Closure(shop=shop, first_day=first, last_day=last, name=name, status=status)
        row.full_clean()
        row.save()
        return row


def saved_unchecked(shop: Shop, first: date, last: date, *, name: str = "Msiba wa bibi") -> None:
    # A closure saved with no check at all, as code that skips the services could: only the database stands in the way.
    # In its own savepoint, so the test's transaction lives on after the refusal.
    with shop_context(shop), transaction.atomic():
        Closure.objects.create(shop=shop, first_day=first, last_day=last, name=name)


def codes(refused: pytest.ExceptionInfo[ValidationError]) -> list[str | None]:
    # Every code the refusal carries, whichever field it is filed under.
    return [error.code for errors in refused.value.error_dict.values() for error in errors]


def test_closure_of_one_day_saved(shop_a: Shop) -> None:
    # Siku ya Uhuru: one day, its first and last day the same.
    row = checked(shop_a, date(2026, 12, 9), date(2026, 12, 9), name="Siku ya Uhuru")
    assert (row.first_day, row.last_day, row.status) == (date(2026, 12, 9), date(2026, 12, 9), ClosureStatus.ACTIVE)


def test_closure_ending_before_it_starts_refused(shop_a: Shop) -> None:
    # A typo: Hadi before Kuanzia. The check refuses it with its code, and the database refuses it too.
    with pytest.raises(ValidationError) as refused:
        checked(shop_a, nov(24), nov(20))
    assert codes(refused) == ["closure.ends_before_it_starts"]
    with pytest.raises(IntegrityError):
        saved_unchecked(shop_a, nov(24), nov(20))


def test_closure_name_blank_refused(shop_a: Shop) -> None:
    # Spaces alone are trimmed away by clean(), so the not-blank rule sees nothing and refuses it, with its code.
    with pytest.raises(ValidationError) as refused:
        checked(shop_a, nov(20), nov(24), name="   ")
    assert codes(refused) == ["closure.name_blank"]
    with pytest.raises(IntegrityError):
        saved_unchecked(shop_a, nov(20), nov(24), name="")


def test_closure_name_trimmed(shop_a: Shop) -> None:
    assert checked(shop_a, nov(20), nov(24), name="  Msiba wa bibi ").name == "Msiba wa bibi"


def test_unknown_status_refused(shop_a: Shop) -> None:
    with pytest.raises(ValidationError):
        checked(shop_a, nov(20), nov(24), status="postponed")


def test_database_refuses_closures_sharing_a_day(shop_a: Shop) -> None:
    # The funeral closes 20–24; a second closure that takes the 24th shares a day with it. The first and last days count
    # (both closed), so even one shared day at the edge is a clash. The check names it with its code, and the database's
    # own rule refuses it when the check is skipped.
    checked(shop_a, nov(20), nov(24))
    with pytest.raises(ValidationError) as refused:
        checked(shop_a, nov(24), nov(25), name="Siku ya mapumziko")
    assert codes(refused) == ["closure.overlaps"]
    for first, last in ((nov(24), nov(25)), (nov(18), nov(20)), (nov(21), nov(22)), (nov(1), nov(30))):
        with pytest.raises(IntegrityError):
            saved_unchecked(shop_a, first, last)


def test_database_refuses_to_delete_a_closure(shop_a: Shop) -> None:
    # Rule 7: a closure is cancelled, never deleted. Nothing links to one, so PROTECT can't stop a delete: the table's
    # own trigger does, whoever sends it, a row's delete() or a bulk one, and the funeral's days stay closed.
    row = checked(shop_a, nov(20), nov(24))
    with shop_context(shop_a):
        with pytest.raises(IntegrityError, match="never deleted"), transaction.atomic():
            row.delete()
        with pytest.raises(IntegrityError, match="never deleted"), transaction.atomic():
            Closure.objects.filter(pk=row.pk).delete()
        assert closed_days(shop_a, nov(20), nov(24)) == {nov(20), nov(21), nov(22), nov(23), nov(24)}


def test_closures_side_by_side_saved(shop_a: Shop) -> None:
    # 20–22, then 23–24: next to each other, no day shared.
    checked(shop_a, nov(20), nov(22))
    checked(shop_a, nov(23), nov(24), name="Siku ya mapumziko")


def test_cancelled_closure_frees_its_days(shop_a: Shop) -> None:
    # A cancelled closure closes nothing, so it blocks nothing: the owner can close the same days again.
    checked(shop_a, nov(20), nov(24), status=ClosureStatus.CANCELLED)
    checked(shop_a, nov(22), nov(23))


def test_another_shops_closure_never_clashes(shop_a: Shop, shop_b: Shop) -> None:
    # Each shop closes on its own days: shop B's funeral says nothing about shop A.
    checked(shop_b, nov(20), nov(24))
    checked(shop_a, nov(20), nov(24))


def test_closed_days_skips_cancelled_closures(shop_a: Shop, shop_b: Shop) -> None:
    # November's closed days: the funeral's three days and the 30th, which starts a closure running into December. Not
    # the cancelled closure's days, nor shop B's.
    checked(shop_a, nov(20), nov(22))
    checked(shop_a, nov(25), nov(26), name="Krismasi ya mfano", status=ClosureStatus.CANCELLED)
    checked(shop_a, nov(30), date(2026, 12, 2), name="Hesabu ya mwaka")
    checked(shop_b, nov(10), nov(12), name="Msiba wa jirani")
    with shop_context(shop_a):
        assert closed_days(shop_a, nov(1), nov(30)) == {nov(20), nov(21), nov(22), nov(30)}
        # A span that cuts a closure in half gets only its own part of it.
        assert closed_days(shop_a, nov(21), date(2026, 12, 1)) == {nov(21), nov(22), nov(30), date(2026, 12, 1)}
        assert closed_days(shop_a, nov(1), nov(19)) == set()


def test_closed_days_reads_only_its_own_shop_in_a_system_job(shop_a: Shop, shop_b: Shop) -> None:
    # A system job (a nightly one, ATT-7) has every shop open, so the guard lets every row through: closed_days names
    # its shop itself, and shop B's funeral never closes shop A.
    checked(shop_b, nov(10), nov(12), name="Msiba wa jirani")
    with system_context():
        assert closed_days(shop_a, nov(1), nov(30)) == set()


def test_closed_days_fails_closed(shop_a: Shop, shop_b: Shop) -> None:
    # Asked about shop A while shop B is open, the guard would hide A's closures and the answer would be "none": every
    # closed day paid, without a word. So it refuses instead (ADR-0022). And a moment is not a shop's day: 22:00 UTC on
    # 19 Nov is already the 20th in Arusha.
    checked(shop_a, nov(20), nov(24))
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        closed_days(shop_a, nov(1), nov(30))
    with shop_context(shop_a), pytest.raises(TypeError):
        closed_days(shop_a, datetime(2026, 11, 1), nov(30))
