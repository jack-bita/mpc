"""apps/staffpay/selectors.py — reads for attendance and pay: the rules a day is judged by (ATT-10), and read back from
a day's own copy for a day decided late (ATT-6).

    on 30 Nov: late_fine 0.00, closing 18:40      the owner types 500 from 1 Dec
    on 1 Dec:  late_fine 500.00, closing 18:40    so 30 Nov keeps its rules, and 1 Dec gets the new one

A day is judged by the rules of its own date (A1): each of the nine is a dated setting of the whole shop (02 §12), read
as get_setting answers it on that date. The book of days (apps/staffpay/services/book.py) reads a span's in one go
(day_rules_between), hands each day's to the day's rule (work_out_day), and keeps a copy of them with the day (T4), as
text.

And each worker's pay rate on each day of a span (rates_between, WAGE-1), read the same way, as a rate is a dated rule:

    Juma  from 10 Nov 10,000   from 15 Nov 12,000      so 10–14 Nov: 10,000 a day, 15–30 Nov: 12,000

And each date's meal money (meal_money_by_date, WAGE-7), the sum of what was typed for it and not crossed out:

    23 Nov  5,000 + 3,000, and 30,000 crossed out      so 23 Nov: 8,000

And what each job was given before payday over a span (advances_between, WAGE-8), the same way:

    Juma  10 Nov 20,000   16 Nov 30,000, and 300,000 crossed out      so November: 50,000

And the laptops that have sent nothing since a moment (quiet_laptops, WAGE-3), as taps of the month may still be inside:

    Laptop ya Vyakula, last sent on 28 Nov, asked on 1 Dec of November's end

And whether the pay of a day is approved (is_closed, WAGE-3), so nothing it is made of may change any more:

    November approved:   30 Nov and every day before it, for everyone        Neema approved alone: her days alone

And the corrections of a month (WAGE-10): mistakes found after an earlier month's approval, put right in this one, by
job (corrections_by_job), and one worker's, crossed out ones too, for their page (corrections_of); and why a month
takes none for a job (why_no_correction):

    Juma  Desemba  + 9,000 "Novemba: siku ya 12/11 haikuhesabiwa", + 90,000 crossed out      so December: + 9,000
"""

import uuid
from calendar import monthrange
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Max, Q, Sum

from apps.core.settings_registry import (
    AFTERNOON_FROM,
    CLOSING,
    LATE_FINE,
    MIDDAY,
    MORNING_LEAVE_UNTIL,
    ON_TIME_UNTIL,
    REVIEW_FROM,
    SECOND_FINE,
    SECOND_FINE_FROM,
    SettingKey,
)
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import Device, DeviceStatus, StaffMember
from apps.shops.models import Shop
from apps.shops.selectors import shop_settings_between, shop_today
from apps.staffpay.calculations import DayRules
from apps.staffpay.models import Advance, MealMoney, PayCorrection, PayRate, PayRun, Payslip

# Each part of a day's rules, by its name in DayRules, and the setting it is read from: one list, so the rules read and
# the copy a day keeps always name the same nine, and a rule added to DayRules without its setting fails at once
# (DayRules takes every part, and only those). Whole-shop settings: attendance belongs to the whole shop, as a funeral
# closes both sides.
DAY_RULE_SETTINGS: dict[str, SettingKey[Any]] = {
    "on_time_until": ON_TIME_UNTIL,
    "second_fine_from": SECOND_FINE_FROM,
    "review_from": REVIEW_FROM,
    "afternoon_from": AFTERNOON_FROM,
    "midday": MIDDAY,
    "morning_leave_until": MORNING_LEAVE_UNTIL,
    "closing": CLOSING,
    "late_fine": LATE_FINE,
    "second_fine": SECOND_FINE,
}


def day_rules_between(shop: Shop, first: date, last: date) -> dict[date, DayRules]:
    """The rules each day from `first` to `last`, both counted, is judged by: each as `get_setting` answers it on that
    date (A1), the key's default where the shop has typed nothing. One read for the whole span (shop_settings_between),
    never nine per day, nor nine per worker. The shop must be open, and the days dates on the shop's calendar."""
    # shop_settings_between's own checks stand: a datetime, which Python counts as a date, is refused there (a moment,
    # not the shop's day), as is a shop that is not the one open.
    values = shop_settings_between(list(DAY_RULE_SETTINGS.values()), shop, first, last)
    return {
        day: DayRules(**{part: on_day[key.key] for part, key in DAY_RULE_SETTINGS.items()})
        for day, on_day in values.items()
    }


def day_rules(shop: Shop, day: date) -> DayRules:
    """The rules one day is judged by, as day_rules_between answers them for a span of that day alone."""
    return day_rules_between(shop, day, day)[day]


def rules_as_text(rules: DayRules) -> dict[str, str]:
    """A day's rules as the day keeps them (`rules_used`, T4): each written by its own setting's kind, as the settings
    store it, "07:35" and "500.00", so no amount ever passes through a float (rule 3), and each reads back as itself."""
    return {part: key.kind.to_text(getattr(rules, part)) for part, key in DAY_RULE_SETTINGS.items()}


def rules_from_text(kept: dict[str, str]) -> DayRules:
    """A day's own copy of its rules (`rules_used`), read back as the rules the day was judged by, for the fine of a
    day decided late (ATT-6, T4): the rules of that day, never today's, which the owner may have changed since. Each
    read by its own setting's kind, as rules_as_text wrote it. Never on an off day, which keeps no copy: a missing part
    is a KeyError, a bug in our code. Today the book writes a day's copy afresh each time it works the day out, so a
    copy always holds every rule there is. Once WAGE-3 locks an approved month, its days keep their copies as they
    were: a tenth day rule added after would be missing from them, and this would fail on every locked day, so that
    card decides what an old copy's missing rule reads as (ATT-6's review)."""
    return DayRules(**{part: key.kind.parse(kept[part]) for part, key in DAY_RULE_SETTINGS.items()})


# A job's rates, newest first, as a setting's rows are read (02 §4): the latest day first; on one day the row written
# last, as a mistake is mended by a new row (T2); then the id, for two rows saved at the very same moment. Every read of
# the rates orders them so, and rate_in_force reads them in this order.
NEWEST_FIRST = ("-effective_from", "-created_at", "-id")


def rates_between(shop: Shop, first: date, last: date) -> dict[tuple[uuid.UUID, date], PayRate]:
    """Each job's pay rate on each day from `first` to `last`, both counted: {(job id, day): the rate in force}. A job
    with no rate on a day, as before its first rate, or the owner, who is paid no day, has no key for that day. One
    read for the span, for every job of the shop: the month page (ATT-5) lists only the jobs it names, and the pay
    (WAGE-2) pays each day at its own rate. It reads no job's first or last day: no rate starts before a first day
    (set_pay_rate refuses one), but a rate goes on after a last, as a tap after it goes to review and the owner may
    decide that day is paid (ATT-11, ATT-6), which needs its rate. So a caller keeps to the days the book answers
    (work_out_days): Juma, gone since 15 Nov, still has a rate here every day after, and is listed by his days."""
    # The same checks as the book's and the settings', for the same reasons (ADR-0022): asked inside another shop's
    # visit, the guard would hide every row, and the answer would be "no rate" for everyone, without a word. And a
    # datetime is a kind of date in Python, but a moment, not the shop's day.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("rates_between was given a shop that is not the one open.")
    if isinstance(first, datetime) or isinstance(last, datetime):
        raise TypeError("rates_between needs the shop's business dates, not datetimes.")
    # Every rate of the shop that has started by the span's last day, each job's newest first, in a setting's order: on
    # one day the row written last wins, as a mistake is mended by a new row (T2), then the id for two rows saved at the
    # very same moment. A rate from before the span still counts on its first days, so no `effective_from >= first`.
    # A shop keeps a few rates a worker a year, so reading them all, and walking the days here, is cheaper than asking
    # the database a question per day.
    newest_first: dict[uuid.UUID, list[PayRate]] = defaultdict(list)
    for rate in PayRate.objects.filter(shop=shop, effective_from__lte=last).order_by("staff", *NEWEST_FIRST):
        newest_first[rate.staff_id].append(rate)
    answer: dict[tuple[uuid.UUID, date], PayRate] = {}
    for job, rates in newest_first.items():
        day = first
        while day <= last:
            # None, and the day has no key.
            in_force = rate_in_force(rates, day)
            if in_force is not None:
                answer[(job, day)] = in_force
            day += timedelta(days=1)
    return answer


def rate_in_force(newest_first: Sequence[PayRate], day: date) -> PayRate | None:
    """Of one job's rates, in NEWEST_FIRST's order, the one in force on `day`: the first that has started by then. None
    before the job's first rate. One rule, for a span (rates_between) and for the worker's page (its `in_force`)."""
    return next((rate for rate in newest_first if rate.effective_from <= day), None)


def meal_money_by_date(shop: Shop, first: date, last: date) -> dict[date, Decimal]:
    """Each date's meal money from `first` to `last`, both counted: {the shop's date: the sum of its rows not voided}
    (WAGE-7, 02 §12). A date with no row that counts, never typed or all crossed out, has no key. One read for the
    span."""
    # The same checks as the rates', for the same reasons (ADR-0022): asked inside another shop's visit, the guard would
    # hide every row, and the answer would be "no money" without a word.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("meal_money_by_date was given a shop that is not the one open.")
    if isinstance(first, datetime) or isinstance(last, datetime):
        raise TypeError("meal_money_by_date needs the shop's business dates, not datetimes.")
    # Added up by the database, exactly: numeric(14,2) sums to numeric, never through a float (rule 3). order_by() drops
    # any order of the rows' own, which would split the groups.
    return dict(
        MealMoney.objects.filter(shop=shop, date__range=(first, last), voided_at__isnull=True)
        .order_by()
        .values("date")
        .annotate(total=Sum("amount"))
        .values_list("date", "total")
    )


def advances_by_job(shop: Shop, first: date, last: date) -> dict[uuid.UUID, list[tuple[date, Decimal]]]:
    """Each advance that counts from `first` to `last`, both counted, by the job it was given to, in the order they were
    given: its day and its amount (WAGE-3). What a payslip copies line by line, where advances_between sums them."""
    # The same check as the sum's, for the same reason (ADR-0022): a payslip with no advance on it would pay the worker
    # money they already have, without a word.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("advances_by_job was given a shop that is not the one open.")
    given: dict[uuid.UUID, list[tuple[date, Decimal]]] = defaultdict(list)
    for staff_id, day, amount in (
        Advance.objects.filter(shop=shop, date__range=(first, last), voided_at__isnull=True)
        # By their day, then as they were typed; the id last, for two typed at the very same moment.
        .order_by("date", "created_at", "id")
        .values_list("staff_id", "date", "amount")
    ):
        given[staff_id].append((day, amount))
    return given


def advances_between(shop: Shop, first: date, last: date) -> dict[uuid.UUID, Decimal]:
    """What each job was given before payday from `first` to `last`, both counted: {job id: the sum of its advances not
    voided} (WAGE-8, 02 §12). A job given none, or whose every one is crossed out, has no key. One read for the span,
    for every job of the shop, as the pay of a month asks it (pay_month)."""
    # The same checks as the rates', for the same reasons (ADR-0022): asked inside another shop's visit, the guard would
    # hide every row, and everyone would be paid money they already have, without a word.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("advances_between was given a shop that is not the one open.")
    if isinstance(first, datetime) or isinstance(last, datetime):
        raise TypeError("advances_between needs the shop's business dates, not datetimes.")
    # Added up by the database, exactly, as the meal money is (meal_money_by_date).
    return dict(
        Advance.objects.filter(shop=shop, date__range=(first, last), voided_at__isnull=True)
        .order_by()
        .values("staff_id")
        .annotate(total=Sum("amount"))
        .values_list("staff_id", "total")
    )


def is_closed(shop: Shop, day: date, job: uuid.UUID | None = None) -> bool:
    """Whether the pay of `day` is approved (WAGE-3, A3), so nothing it is made of may be added, decided or crossed out
    any more: its month is approved, or a later one, as months are approved in order, so whatever an earlier month holds
    would be on nobody's pay; or, for a job, its own pay up to then is, approved alone as it left. With no job: the
    shop's own, its meal money, which one worker approved alone doesn't lock. Asked under the lock the approval takes
    (lock_jobs), or the job's own row: before it, an approval a moment later would not be seen."""
    # The same checks as the other reads', for the same reasons (ADR-0022): asked inside another shop's visit, the guard
    # would hide the approval, and a closed month would take a change without a word.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("is_closed was given a shop that is not the one open.")
    if isinstance(day, datetime):
        raise TypeError("is_closed needs the shop's business date, not a datetime.")
    month = day.replace(day=1)
    if PayRun.objects.filter(shop=shop, month__gte=month).exists():
        return True
    return job is not None and Payslip.objects.filter(shop=shop, staff_id=job, month__gte=month).exists()


def corrections_by_job(shop: Shop, month: date) -> dict[uuid.UUID, list[tuple[Decimal, str]]]:
    """Each correction that counts in the pay of the month of `month`, any day of it, by the job it corrects, in the
    order typed: what it adds or takes off, and why (WAGE-10). The month's draft adds them up, and its payslip copies
    them line by line, from the one read."""
    # The same check as the advances', for the same reason (ADR-0022): a pay with no correction on it would leave Juma
    # 9,000 short a second time, without a word.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("corrections_by_job was given a shop that is not the one open.")
    typed: dict[uuid.UUID, list[tuple[Decimal, str]]] = defaultdict(list)
    for staff_id, amount, reason in (
        PayCorrection.objects.filter(shop=shop, month=month.replace(day=1), voided_at__isnull=True)
        # As they were typed; the id last, for two typed at the very same moment.
        .order_by("created_at", "id")
        .values_list("staff_id", "amount", "reason")
    ):
        typed[staff_id].append((amount, reason))
    return typed


def corrections_of(shop: Shop, job: uuid.UUID, month: date) -> list[PayCorrection]:
    """One job's corrections in the pay of the month of `month`, crossed out ones too, in the order typed, with who
    typed and who crossed out each (WAGE-10): what the worker's page lists, as a payslip's foot lists its payments."""
    return list(
        PayCorrection.objects.filter(shop=shop, staff_id=job, month=month.replace(day=1))
        .select_related("created_by", "voided_by")
        .order_by("created_at", "id")
    )


def why_no_correction(shop: Shop, job: StaffMember, month: date) -> str | None:
    """Why the pay of the month of `month` takes no correction for `job` (WAGE-10), as its code, the first that holds;
    or None when it takes one. The one rule for the page, which offers Ongeza marekebisho only then, and for
    record_correction, which refuses with the code. Asked under the job's lock there, as an approval a moment later
    closes the month."""
    first = month.replace(day=1)
    last = _months_end(first)
    # One who left, whose pay is approved, first: no later pay of theirs will be made, so whatever month is asked, there
    # is none to put it in (Jack: A). Paid alone the evening they left, or with the month: either closes their last day.
    if job.left_on is not None and is_closed(shop, job.left_on, job.pk):
        return "correction.left_paid"
    # A month to come has no pay yet, so it is a slip: today's month is the latest a pay is worked out for.
    if first > shop_today(shop):
        return "correction.month_to_come"
    # A month the job didn't run in is in no pay of it: before its first day, or after its last.
    if job.started_on > last or (job.left_on is not None and job.left_on < first):
        return "correction.outside_job"
    # Only a worker the shop pays by the day in that month, from any day of it: a rate in force on one of its days, as
    # the month's pay lists them. The owner, who has no rate, has no pay to put it in.
    if not PayRate.objects.filter(shop=shop, staff=job, effective_from__lte=last).exists():
        return "correction.not_paid_by_day"
    # The month's pay is final (A3): it would be in no payslip. A later month takes it.
    if is_closed(shop, first, job.pk):
        return "pay.day_approved"
    return None


def closed_to(shop: Shop) -> date | None:
    """The last day of the last month approved, or None while none is (WAGE-3): up to it, the shop's own pay is closed
    (is_closed), so the meal money's page offers no change of those days."""
    month = PayRun.objects.filter(shop=shop).aggregate(last=Max("month"))["last"]
    return None if month is None else _months_end(month)


@dataclass(frozen=True)
class ClosedPay:
    # What of the shop's pay is approved, read once for a page of many days (is_closed asks of one): up to `to`, the
    # last day of the last month approved, for everyone; and each job approved alone, up to the last day of its month.
    to: date | None
    alone: dict[uuid.UUID, date]

    def holds(self, job: uuid.UUID, day: date) -> bool:
        return (self.to is not None and day <= self.to) or day <= self.alone.get(job, date.min)


def closed_pay(shop: Shop) -> ClosedPay:
    """What of the shop's pay is approved (WAGE-3), in two reads: the last month approved for everyone, and the last one
    each job was approved alone in. The same rule as is_closed, for a page that asks it of every day it shows."""
    alone = (
        Payslip.objects.filter(shop=shop, pay_run__isnull=True)
        .order_by()
        .values("staff_id")
        .annotate(last=Max("month"))
        .values_list("staff_id", "last")
    )
    return ClosedPay(to=closed_to(shop), alone={job: _months_end(month) for job, month in alone})


def _months_end(month: date) -> date:
    return month.replace(day=monthrange(month.year, month.month)[1])


@dataclass(frozen=True)
class QuietLaptop:
    # A laptop that has sent nothing since a moment, by its name, and when it last did, or None for one that never has.
    name: str
    last_synced_at: datetime | None


def quiet_laptops(shop: Shop, since: datetime) -> list[QuietLaptop]:
    """The shop's active laptops that have sent nothing since `since`, by name (WAGE-3): with no internet since the
    28th, Laptop ya Vyakula may hold taps of the month that nobody has seen. Not a blocked one, whose records come only
    by a person's doing; nor one paired after `since`, which can hold nothing from before it."""
    rows = (
        Device.objects.filter(shop=shop, status=DeviceStatus.ACTIVE, created_at__lt=since)
        .filter(Q(last_synced_at__isnull=True) | Q(last_synced_at__lt=since))
        .order_by("name", "pk")
        .values_list("name", "last_synced_at")
    )
    return [QuietLaptop(name, last_synced_at) for name, last_synced_at in rows]
