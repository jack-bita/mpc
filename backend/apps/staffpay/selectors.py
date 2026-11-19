"""apps/staffpay/selectors.py — reads for attendance and pay: the rules a day is judged by (ATT-10).

    on 30 Nov: late_fine 0.00, closing 18:40      the owner types 500 from 1 Dec
    on 1 Dec:  late_fine 500.00, closing 18:40    so 30 Nov keeps its rules, and 1 Dec gets the new one

A day is judged by the rules of its own date (A1): each of the nine is a dated setting of the whole shop (02 §12), read
as get_setting answers it on that date. The book of days (apps/staffpay/services.py) reads a span's in one go
(day_rules_between), hands each day's to the day's rule (work_out_day), and keeps a copy of them with the day (T4), as
text.

And each worker's pay rate on each day of a span (rates_between, WAGE-1), read the same way, as a rate is a dated rule:

    Juma  from 10 Nov 10,000   from 15 Nov 12,000      so 10–14 Nov: 10,000 a day, 15–30 Nov: 12,000
"""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

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
from apps.shops.models import Shop
from apps.shops.selectors import shop_settings_between
from apps.staffpay.calculations import DayRules
from apps.staffpay.models import PayRate

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


def rates_between(shop: Shop, first: date, last: date) -> dict[tuple[uuid.UUID, date], PayRate]:
    """Each job's pay rate on each day from `first` to `last`, both counted: {(job id, day): the rate in force}. A job
    with no rate on a day, as before its first rate, or the owner, who is paid no day, has no key for that day. One
    read for the span, for every job of the shop: the month page (ATT-5) lists only the jobs it names, and the pay
    (WAGE-2) pays each day at its own rate."""
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
    for rate in PayRate.objects.filter(shop=shop, effective_from__lte=last).order_by(
        "staff", "-effective_from", "-created_at", "-id"
    ):
        newest_first[rate.staff_id].append(rate)
    answer: dict[tuple[uuid.UUID, date], PayRate] = {}
    for job, rates in newest_first.items():
        day = first
        while day <= last:
            # The job's first rate, newest first, that has started by this day; none, and the day has no key.
            in_force = next((rate for rate in rates if rate.effective_from <= day), None)
            if in_force is not None:
                answer[(job, day)] = in_force
            day += timedelta(days=1)
    return answer
