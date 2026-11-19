"""apps/staffpay/selectors.py — reads for attendance and pay: the rules a day is judged by (ATT-10).

    on 30 Nov: late_fine 0.00, closing 18:40      the owner types 500 from 1 Dec
    on 1 Dec:  late_fine 500.00, closing 18:40    so 30 Nov keeps its rules, and 1 Dec gets the new one

A day is judged by the rules of its own date (A1): each of the nine is a dated setting of the whole shop (02 §12), read
as get_setting answers it on that date. The book of days (apps/staffpay/services.py) reads a span's in one go
(day_rules_between), hands each day's to the day's rule (work_out_day), and keeps a copy of them with the day (T4), as
text.
"""

from datetime import date
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
from apps.shops.models import Shop
from apps.shops.selectors import shop_settings_between
from apps.staffpay.calculations import DayRules

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
