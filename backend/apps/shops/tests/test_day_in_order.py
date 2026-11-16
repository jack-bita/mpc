"""apps/shops/tests/test_day_in_order.py — set_setting keeps the attendance day's seven times in order (ATT-2, 02 §12).

The owner's day, as a new shop starts with it, each time strictly after the one before:

    on time until 07:35 < second fine from 08:00 < dharura from 08:30 < afternoon from 12:00
                        < midday 13:00 < morning leave until 13:30 < closing 18:40

A time that breaks the order would put one minute in two windows, and ATT-4 would pay that day two ways. So set_setting
refuses it (setting.out_of_order), and writes nothing, on the new value's own day and on each later day another of the
seven changes, up to the rule's own next row:

    today        next week
    08:30 → 08:15 from today        second fine 08:20 from next week   → refused: next week 08:20 ≥ 08:15
    08:30 → 08:15 from today        dharura 08:45 from next week too    → saved: next week is dharura's own new row

The other rules never meet the check.
"""

from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.core.settings_registry import (
    ATTENDANCE_ON,
    CLOSING,
    LATE_FINE,
    MIDDAY,
    ON_TIME_UNTIL,
    REVIEW_FROM,
    SECOND_FINE_FROM,
)
from apps.core.tenancy import shop_context
from apps.shops.models import Setting, Shop
from apps.shops.selectors import get_setting, shop_today
from apps.shops.services import set_setting

pytestmark = pytest.mark.django_db

OUT_OF_ORDER = {"value": ["setting.out_of_order"]}


def refusal_codes(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, list[str | None]]:
    # Each field's codes, as the API's error handler reads them (apps/core/api/errors.py).
    return {field: [error.code for error in errors] for field, errors in refused.value.error_dict.items()}


def rows_of(shop: Shop) -> list[tuple[str, str]]:
    with shop_context(shop):
        return list(Setting.objects.filter(shop=shop).order_by("key").values_list("key", "value"))


def test_a_time_out_of_order_refused(shop_a: Shop) -> None:
    # Before the time above it, on the same minute as it, and after the time below it: each refused, beside the value's
    # box, and nothing written.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as before_the_one_above:
            set_setting(shop_a, key=SECOND_FINE_FROM.key, value="07:30", effective_from=today, by=None)
        # 07:35 is on time by its own minute and would start the second fine on the same minute.
        with pytest.raises(ValidationError) as on_the_same_minute:
            set_setting(shop_a, key=SECOND_FINE_FROM.key, value="07:35", effective_from=today, by=None)
        with pytest.raises(ValidationError) as after_the_one_below:
            set_setting(shop_a, key=MIDDAY.key, value="18:45", effective_from=today, by=None)
    assert refusal_codes(before_the_one_above) == OUT_OF_ORDER
    assert refusal_codes(on_the_same_minute) == OUT_OF_ORDER
    assert refusal_codes(after_the_one_below) == OUT_OF_ORDER
    assert rows_of(shop_a) == []


def test_a_time_in_order_saved(shop_a: Shop) -> None:
    # Between its two neighbours, and the first and the last of the day, which have one neighbour each.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        set_setting(shop_a, key=SECOND_FINE_FROM.key, value="08:10", effective_from=today, by=None)
        set_setting(shop_a, key=ON_TIME_UNTIL.key, value="07:00", effective_from=today, by=None)
        set_setting(shop_a, key=CLOSING.key, value="19:00", effective_from=today, by=None)
        assert get_setting(SECOND_FINE_FROM, shop_a, on=today) == time(8, 10)
        assert get_setting(ON_TIME_UNTIL, shop_a, on=today) == time(7, 0)
        assert get_setting(CLOSING, shop_a, on=today) == time(19, 0)


def test_a_time_out_of_order_on_a_later_day_refused(shop_a: Shop) -> None:
    # The second fine already moves to 08:20 from next week. Dharura from 08:15, from today, is in order today, beside
    # the second fine's 08:00, but not next week, beside its 08:20: refused. From 08:25 it is in order on both days.
    today = shop_today(shop_a)
    next_week = today + timedelta(days=7)
    with shop_context(shop_a):
        set_setting(shop_a, key=SECOND_FINE_FROM.key, value="08:20", effective_from=next_week, by=None)
        with pytest.raises(ValidationError) as clashes_next_week:
            set_setting(shop_a, key=REVIEW_FROM.key, value="08:15", effective_from=today, by=None)
        assert refusal_codes(clashes_next_week) == OUT_OF_ORDER
        assert rows_of(shop_a) == [(SECOND_FINE_FROM.key, "08:20")]

        set_setting(shop_a, key=REVIEW_FROM.key, value="08:25", effective_from=today, by=None)
        assert get_setting(REVIEW_FROM, shop_a, on=next_week) == time(8, 25)


def test_a_later_row_of_the_same_rule_ends_the_check(shop_a: Shop) -> None:
    # Next week dharura moves to 08:45 and the second fine to 08:20, set already. Dharura from 08:15, from today, counts
    # only until its own row of next week, so next week's 08:20 never meets it: saved.
    today = shop_today(shop_a)
    next_week = today + timedelta(days=7)
    with shop_context(shop_a):
        set_setting(shop_a, key=REVIEW_FROM.key, value="08:45", effective_from=next_week, by=None)
        set_setting(shop_a, key=SECOND_FINE_FROM.key, value="08:20", effective_from=next_week, by=None)

        set_setting(shop_a, key=REVIEW_FROM.key, value="08:15", effective_from=today, by=None)
        assert get_setting(REVIEW_FROM, shop_a, on=today) == time(8, 15)
        assert get_setting(REVIEW_FROM, shop_a, on=next_week) == time(8, 45)


def test_other_rules_skip_the_order_check(shop_a: Shop) -> None:
    # Closing at 07:00 breaks the order, a row only code that skips set_setting could write. The fine and the switch are
    # not times of the day, so they are saved all the same: the check is the seven times' alone.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        Setting.objects.create(shop=shop_a, key=CLOSING.key, value="07:00", effective_from=today)
        set_setting(shop_a, key=LATE_FINE.key, value="500", effective_from=today, by=None)
        set_setting(shop_a, key=ATTENDANCE_ON.key, value="true", effective_from=today, by=None)
    # By key, as rows_of sorts them.
    assert rows_of(shop_a) == [
        (CLOSING.key, "07:00"),
        (ATTENDANCE_ON.key, "true"),
        (LATE_FINE.key, "500.00"),
    ]
