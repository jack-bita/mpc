"""apps/staffpay/tests/test_day_rules.py — the rules a day is judged by, as they stood on its date (ATT-10, A1).

    on 30 Nov: late_fine 0.00, closing 18:40      the owner types 500 from 1 Dec, and closing 18:00
    on 1 Dec:  late_fine 500.00, closing 18:00

day_rules reads each of the nine rules of 02 §12 with get_setting on the day's own date; rules_as_text writes them as
the day keeps its copy (T4), and rules_from_text reads that copy back for a day decided late (ATT-6). The fine is the
demo's made-up 500 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from apps.core.settings_registry import CLOSING, LATE_FINE, SettingKey
from apps.core.tenancy import shop_context
from apps.shops.models import Setting, Shop
from apps.staffpay.calculations import DayRules
from apps.staffpay.selectors import day_rules, rules_as_text, rules_from_text

pytestmark = pytest.mark.django_db

NOV_30 = dt.date(2026, 11, 30)
DEC_1 = dt.date(2026, 12, 1)

# The owner's day as every shop starts with it (apps/core/settings_registry.py): MPC's times, and no fine.
DEFAULT_RULES = DayRules(
    on_time_until=dt.time(7, 35),
    second_fine_from=dt.time(8, 0),
    review_from=dt.time(8, 30),
    afternoon_from=dt.time(12, 0),
    midday=dt.time(13, 0),
    morning_leave_until=dt.time(13, 30),
    closing=dt.time(18, 40),
    late_fine=Decimal("0.00"),
    second_fine=Decimal("0.00"),
)


def _rule(shop: Shop, key: SettingKey[Any], value: str, effective_from: dt.date) -> None:
    # A row checked, then saved, as set_setting saves one (SHOP-3), but with no line and on any day, as
    # test_get_setting.py writes its rows: these tests read what a day is judged by, not how a rule is typed.
    with shop_context(shop):
        row = Setting(shop=shop, key=key.key, value=value, effective_from=effective_from)
        row.full_clean()
        row.save()


def test_day_rules_read_each_rule_on_its_date(shop_a: Shop) -> None:
    # The owner raises the first fine to 500 and closes at 18:00 from 1 December: 30 November keeps the rules it had,
    # and 1 December gets the new ones, a fine and a time alike. Every other rule is its default on both days.
    _rule(shop_a, LATE_FINE, "500.00", DEC_1)
    _rule(shop_a, CLOSING, "18:00", DEC_1)
    with shop_context(shop_a):
        assert day_rules(shop_a, NOV_30) == DEFAULT_RULES
        on_dec_1 = day_rules(shop_a, DEC_1)
    assert on_dec_1.late_fine == Decimal("500.00")
    assert on_dec_1.closing == dt.time(18, 0)
    assert on_dec_1.on_time_until == DEFAULT_RULES.on_time_until


def test_day_rules_read_only_the_shops_own(shop_a: Shop, shop_b: Shop) -> None:
    # Another shop's fine never judges this shop's day (T1): each shop's rules are its own.
    _rule(shop_b, LATE_FINE, "1500.00", NOV_30)
    with shop_context(shop_a):
        assert day_rules(shop_a, NOV_30).late_fine == Decimal("0.00")
    with shop_context(shop_b):
        assert day_rules(shop_b, NOV_30).late_fine == Decimal("1500.00")


def test_a_days_rules_are_kept_as_text() -> None:
    # The copy a day keeps (rules_used): every rule, in the settings' own text, so money never passes through a float
    # (rule 3) and a time keeps its minute.
    rules = replace(DEFAULT_RULES, late_fine=Decimal("500.00"), second_fine=Decimal("1500.00"))
    assert rules_as_text(rules) == {
        "on_time_until": "07:35",
        "second_fine_from": "08:00",
        "review_from": "08:30",
        "afternoon_from": "12:00",
        "midday": "13:00",
        "morning_leave_until": "13:30",
        "closing": "18:40",
        "late_fine": "500.00",
        "second_fine": "1500.00",
    }


def test_a_days_copy_reads_back_as_its_rules() -> None:
    # A day decided late reads its fine from its own copy (ATT-6, T4): the copy read back is the very rules it was
    # judged by, a time to its minute and a fine to its shilling, whatever the owner has typed since.
    rules = replace(DEFAULT_RULES, late_fine=Decimal("500.00"), second_fine=Decimal("1500.00"))
    assert rules_from_text(rules_as_text(rules)) == rules
