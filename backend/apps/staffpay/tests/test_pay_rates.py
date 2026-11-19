"""apps/staffpay/tests/test_pay_rates.py — a worker's daily pay rate, dated (WAGE-1; 02 §12): the rules the table keeps
on a rate (PayRate, apps/staffpay/models.py), and which rate is in force on each day of a span (rates_between,
apps/staffpay/selectors.py).

    who    from        rate        shares meals   note
    Juma   10 Nov      10,000.00   yes
    Juma   15 Nov      12,000.00   yes            Ameongezewa     ← from the 15th, the 10th's rate no longer counts
    Neema  01 Nov       8,000.00   no             the cook

A dated rule, so a ledger (rule 2): a rate is written once and never changed or deleted, and a mistake is mended by a
new row for the same day, the newest counting. Setting one, with who may, is set_pay_rate's (test_set_pay_rate.py);
these tests write rows straight in, as the table's rules hold whoever writes. The amounts are made up: the repo is
public (rule 10).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.core.models import AppendOnlyError
from apps.core.tenancy import ShopMismatch, shop_context, system_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, mark_left
from apps.shops.models import Shop
from apps.staffpay.models import PayRate
from apps.staffpay.selectors import rates_between

pytestmark = pytest.mark.django_db

NOV_1 = dt.date(2026, 11, 1)
NOV_10 = dt.date(2026, 11, 10)
NOV_15 = dt.date(2026, 11, 15)
NOV_30 = dt.date(2026, 11, 30)
DEC_1 = dt.date(2026, 12, 1)


def _worker(shop: Shop, name: str, started_on: dt.date = NOV_1) -> StaffMember:
    # Made the way the app makes one: create_user, then the people service, inside the shop (PPL-2).
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, started_on=started_on, by=None)


def _rate(
    staff: StaffMember, amount: str, effective_from: dt.date, *, shares_meals: bool = True, note: str = ""
) -> PayRate:
    # A rate as the table keeps it: checked by the model's own rules, then saved, inside the worker's shop.
    with shop_context(staff.shop):
        row = PayRate(
            shop=staff.shop,
            staff=staff,
            daily_rate=Decimal(amount),
            effective_from=effective_from,
            shares_meals=shares_meals,
            note=note,
        )
        row.full_clean()
        row.save()
        return row


def _days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]


# The table's rules.


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "10000.50"])
def test_a_rate_is_whole_shillings_above_nothing(shop_a: Shop, amount: str) -> None:
    # Pay for a day is more than nothing, and the shop's money has no cents (Jack, 16 Nov 2026), so 10,000.50 is a
    # typo: the model's check names it, with the code the page translates.
    juma = _worker(shop_a, "Juma")
    with pytest.raises(ValidationError) as refused:
        _rate(juma, amount, NOV_10)
    codes = {error.code for errors in refused.value.error_dict.values() for error in errors}
    assert codes == {"pay_rate.amount_invalid"}


@pytest.mark.parametrize("amount", ["0.00", "-500.00", "10000.50"])
def test_the_database_refuses_such_a_rate_too(shop_a: Shop, amount: str) -> None:
    # The same two rules in PostgreSQL, whatever writes the row: a save that skips the model's checks still fails.
    juma = _worker(shop_a, "Juma")
    with shop_context(shop_a):
        row = PayRate(shop=shop_a, staff=juma, daily_rate=Decimal(amount), effective_from=NOV_10)
        with pytest.raises(IntegrityError, match="staffpay_payrate_"), transaction.atomic():
            row.save()


def test_a_rate_shares_the_meals_unless_told_otherwise(shop_a: Shop) -> None:
    # Every worker pays their share of the meals but the cook (02 §12, WAGE-7): yes, unless the page says no.
    juma = _worker(shop_a, "Juma")
    with shop_context(shop_a):
        row = PayRate(shop=shop_a, staff=juma, daily_rate=Decimal("10000.00"), effective_from=NOV_10)
    assert row.shares_meals is True


def test_a_rate_is_never_changed_or_deleted(shop_a: Shop) -> None:
    # A dated rule is a ledger (rule 2, T2): a wrong rate is mended by a new row, never by changing this one. The model
    # refuses first, with a clear message; the trigger in the table's migration refuses in PostgreSQL, whatever sends.
    juma = _worker(shop_a, "Juma")
    row = _rate(juma, "10000.00", NOV_10)
    with shop_context(shop_a):
        row.daily_rate = Decimal("12000.00")
        with pytest.raises(AppendOnlyError):
            row.save()
        with pytest.raises(AppendOnlyError):
            row.delete()
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            PayRate.objects.filter(pk=row.pk).update(daily_rate=Decimal("12000.00"))
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            PayRate.objects.filter(pk=row.pk).delete()
        assert PayRate.objects.get(pk=row.pk).daily_rate == Decimal("10000.00")


# Which rate is in force on a day.


def test_a_rate_counts_from_its_day_on(shop_a: Shop) -> None:
    # Juma's 10,000 from 10 Nov: each day from the 10th has it; the days before have none, so no rate shows for them.
    juma = _worker(shop_a, "Juma")
    rate = _rate(juma, "10000.00", NOV_10)
    with shop_context(shop_a):
        rates = rates_between(shop_a, NOV_1, NOV_30)
    assert all((juma.pk, day) not in rates for day in _days(NOV_1, NOV_10 - dt.timedelta(days=1)))
    assert all(rates[(juma.pk, day)] == rate for day in _days(NOV_10, NOV_30))


def test_a_raise_mid_month_splits_the_days(shop_a: Shop) -> None:
    # A raise from the 15th: the 10th to the 14th keep the old rate, the 15th on take the new one, so WAGE-2 pays each
    # day at its own rate.
    juma = _worker(shop_a, "Juma")
    old = _rate(juma, "10000.00", NOV_10)
    new = _rate(juma, "12000.00", NOV_15, note="Ameongezewa")
    with shop_context(shop_a):
        rates = rates_between(shop_a, NOV_1, NOV_30)
    assert all(rates[(juma.pk, day)] == old for day in _days(NOV_10, NOV_15 - dt.timedelta(days=1)))
    assert all(rates[(juma.pk, day)] == new for day in _days(NOV_15, NOV_30))


def test_a_raise_to_come_leaves_this_month_as_it_is(shop_a: Shop) -> None:
    # Baba types on 19 Nov a raise from 1 Dec: November reads the old rate, December the new.
    juma = _worker(shop_a, "Juma")
    old = _rate(juma, "10000.00", NOV_10)
    new = _rate(juma, "12000.00", DEC_1)
    with shop_context(shop_a):
        november = rates_between(shop_a, NOV_1, NOV_30)
        december = rates_between(shop_a, DEC_1, DEC_1 + dt.timedelta(days=30))
    assert {rate for rate in november.values()} == {old}
    assert {rate for rate in december.values()} == {new}


def test_of_two_rates_on_one_day_the_newest_counts(shop_a: Shop) -> None:
    # Baba types 100,000 for Juma from the 10th, a slip for 10,000, and types the right one for the same day: the row
    # written last wins, as for a setting (02 §4), so the mistake counts on no day, and still stands in the history.
    juma = _worker(shop_a, "Juma")
    _rate(juma, "100000.00", NOV_10)
    mended = _rate(juma, "10000.00", NOV_10, note="Nilikosea")
    with shop_context(shop_a):
        rates = rates_between(shop_a, NOV_1, NOV_30)
        assert PayRate.objects.filter(staff=juma).count() == 2
    assert {rate for rate in rates.values()} == {mended}


def test_each_worker_has_their_own_rate(shop_a: Shop) -> None:
    # Juma's raise is Juma's: Neema, the cook, keeps her rate, and pays no share of the meals.
    juma = _worker(shop_a, "Juma")
    neema = _worker(shop_a, "Neema")
    _rate(juma, "10000.00", NOV_1)
    _rate(juma, "12000.00", NOV_15)
    cooks = _rate(neema, "8000.00", NOV_1, shares_meals=False)
    with shop_context(shop_a):
        rates = rates_between(shop_a, NOV_1, NOV_30)
    assert all(rates[(neema.pk, day)] == cooks for day in _days(NOV_1, NOV_30))
    assert rates[(neema.pk, NOV_15)].shares_meals is False
    assert rates[(juma.pk, NOV_15)].daily_rate == Decimal("12000.00")


def test_a_worker_with_no_rate_has_none_on_any_day(shop_a: Shop) -> None:
    # The owner has no daily rate, as he is paid no day: he is in the book of days (ATT-10) but in no answer here, which
    # is how the month page (ATT-5) and the pay (WAGE-2) leave him out.
    _worker(shop_a, "Baba")
    juma = _worker(shop_a, "Juma")
    _rate(juma, "10000.00", NOV_1)
    with shop_context(shop_a):
        rates = rates_between(shop_a, NOV_1, NOV_30)
    assert {job for job, _ in rates} == {juma.pk}


def test_a_rate_goes_on_after_a_jobs_last_day(shop_a: Shop) -> None:
    # Juma leaves on 15 Nov: his rate still answers every day after, as a tap after his last day can go to review and
    # the owner may decide that day is paid (ATT-11, ATT-6), which needs its rate. The selector reads no job's days, so
    # the month page (ATT-5) and the pay (WAGE-2) keep to the days the book answers, never to this answer alone.
    juma = _worker(shop_a, "Juma")
    rate = _rate(juma, "10000.00", NOV_1)
    with shop_context(shop_a):
        mark_left(juma, left_on=NOV_15, by=None, reason="Amehamia Moshi")
        rates = rates_between(shop_a, NOV_1, NOV_30)
    assert all(rates[(juma.pk, day)] == rate for day in _days(NOV_15 + dt.timedelta(days=1), NOV_30))


def test_only_the_shops_own_rates(shop_a: Shop, shop_b: Shop) -> None:
    # Shop B's worker and rate are never in shop A's answer (T1), in a visit of shop A's, where the guard hides shop B's
    # rows, and under a system job that opens every shop, as the night's job (ATT-7) and the pay (WAGE-2) may call it:
    # there the guard hides nothing, and only the selector's own `shop=` keeps shop B's rates out.
    juma = _worker(shop_a, "Juma")
    _rate(juma, "10000.00", NOV_1)
    _rate(_worker(shop_b, "Juma"), "15000.00", NOV_1)
    with shop_context(shop_a):
        in_the_visit = rates_between(shop_a, NOV_1, NOV_30)
    with system_context():
        in_a_system_job = rates_between(shop_a, NOV_1, NOV_30)
    assert {job for job, _ in in_the_visit} == {job for job, _ in in_a_system_job} == {juma.pk}


def test_a_month_is_one_read(shop_a: Shop) -> None:
    # The month page and the pay read a month of every worker's rates at once: one query, however many workers and
    # raises, never one per worker or per day.
    for name in ("Juma", "Neema", "Asha"):
        worker = _worker(shop_a, name)
        _rate(worker, "10000.00", NOV_1)
        _rate(worker, "12000.00", NOV_15)
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        rates_between(shop_a, NOV_1, NOV_30)
    assert len(queries) == 1


def test_rates_between_needs_the_shop_open(shop_a: Shop, shop_b: Shop) -> None:
    # As for the book and the settings (ADR-0022): asked inside another shop's visit, the guard would hide every row and
    # the answer would be "no rate" without a word, so it fails closed; and a moment is not the shop's day.
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        rates_between(shop_a, NOV_1, NOV_30)
    with shop_context(shop_a), pytest.raises(TypeError):
        rates_between(shop_a, dt.datetime(2026, 11, 1, tzinfo=dt.UTC), NOV_30)
