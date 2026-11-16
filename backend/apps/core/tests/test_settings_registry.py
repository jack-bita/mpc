"""apps/core/tests/test_settings_registry.py — tests for the list of rules a shop can set (D13, ADR-0013).

Every rule that changes over time is a setting: a key from this list, with the kind of value it takes, a
default, and a scope (one value for the whole shop, or one a side may override). A setting's value is
stored as text, in one form per kind, so these tests check both ways: text in, a value out, and back.

    kind        typed      value               stored
    Money       "1000"     Decimal("1000")     "1000.00"    (whole shillings only)
    TimeOfDay   "07:35"    time(7, 35)         "07:35"
    YesNo       "false"    False               "false"

The rows themselves live in `shops` (apps/shops/tests/test_setting_rows.py): `core` is layer 0 and may
not import it, not even in its tests (ADR-0035).
"""

import re
from datetime import time
from decimal import Decimal
from typing import Any

import pytest

from apps.core.settings_registry import (
    KEY_SHAPE,
    KEYS,
    KINDS,
    REGISTRY,
    Money,
    Percent,
    Scope,
    SettingKey,
    TimeOfDay,
    ValueKind,
    Whole,
    YesNo,
)


@pytest.mark.parametrize("key", KEYS, ids=lambda key: key.key)
def test_every_default_is_a_valid_value(key: SettingKey[Any]) -> None:
    # The default is what a shop gets until it adds a row, so it must be a value its own kind accepts.
    # Written as text and read back, it must come out the same: it is stored, sent and shown one way.
    assert key.kind.parse(key.kind.to_text(key.default)) == key.default
    # The key's shape is also a rule in the database (shops_setting_key_shape): a key that breaks it
    # could never get a row.
    assert re.fullmatch(KEY_SHAPE, key.key)


def test_each_kind_has_a_name_of_its_own() -> None:
    # A device reads a rule's stored text by its kind's name ("time" → "07:35"), sent with the rule's default
    # (SYNC-2), so each kind has one name, no two kinds share one, and every key's kind is on the list.
    assert [kind.code for kind in KINDS] == ["money", "percent", "whole", "time", "yes_no"]
    assert {type(key.kind) for key in KEYS} <= set(KINDS)


def test_each_key_listed_once() -> None:
    # REGISTRY is built from KEYS by name. A key listed twice would keep only its last entry, and the
    # first one's kind, default or scope would be lost without a word.
    assert len(REGISTRY) == len(KEYS)


@pytest.mark.parametrize(
    ("kind", "text", "value", "stored"),
    [
        pytest.param(Money(), "1000", Decimal("1000"), "1000.00", id="money_whole_shillings"),
        # Whole shillings with places that are zeros are still whole: "1500.00" is 1,500.
        pytest.param(Money(), "1500.00", Decimal("1500.00"), "1500.00", id="money_zero_cents"),
        pytest.param(Money(), "0", Decimal("0"), "0.00", id="money_zero"),
        # The largest whole amount a numeric(14,2) column holds (03 §9).
        pytest.param(Money(), "999999999999", Decimal("999999999999"), "999999999999.00", id="money_largest"),
        pytest.param(Percent(), "2.5", Decimal("2.5"), "2.50", id="percent"),
        pytest.param(Percent(), "100", Decimal("100"), "100.00", id="percent_all"),
        pytest.param(Whole(maximum=1000), "90", 90, "90", id="whole"),
        pytest.param(Whole(maximum=1000), "090", 90, "90", id="whole_leading_zero"),
        pytest.param(TimeOfDay(), "07:35", time(7, 35), "07:35", id="time"),
        pytest.param(TimeOfDay(), "23:59", time(23, 59), "23:59", id="time_last_minute"),
        pytest.param(YesNo(), "true", True, "true", id="yes"),
        pytest.param(YesNo(), "false", False, "false", id="no"),
    ],
)
def test_value_kinds_read_and_write_text(kind: ValueKind[Any], text: str, value: object, stored: str) -> None:
    parsed = kind.parse(text)
    assert parsed == value
    # The type too, not only the value: Python says Decimal("1000") == 1000.0 and 1 == True, so a float
    # (ADR-0024) or a number posing as yes/no would pass the line above.
    assert type(parsed) is type(value)
    assert kind.to_text(parsed) == stored


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        # Money: an exact amount in plain digits, in whole shillings (ADR-0024; Jack, 16 Nov 2026).
        pytest.param(Money(), "abc", id="money_not_a_number"),
        # Cents: the shop's money has none, and a rule with them would stop every screen that writes money
        # (formatMoney refuses cents): a rounding step of 2.50, a late fine of 1,000.50.
        pytest.param(Money(), "1500.5", id="money_with_cents"),
        pytest.param(Money(), "0.50", id="money_half_a_shilling"),
        pytest.param(Money(), "1,000", id="money_with_a_comma"),
        pytest.param(Money(), "10.005", id="money_three_places"),
        pytest.param(Money(), "-500", id="money_below_zero"),
        # Python's Decimal() reads these three, so the kind must check the text before it.
        pytest.param(Money(), "1e3", id="money_with_an_exponent"),
        pytest.param(Money(), "NaN", id="money_not_a_number_word"),
        pytest.param(Money(), " 100", id="money_with_a_space"),
        # ١٠٠: 100 in Arabic-Indic digits. Python's int() and Decimal() read digits from other scripts
        # too, so the kinds accept only plain 0 to 9.
        pytest.param(Money(), "١٠٠", id="money_other_script_digits"),
        pytest.param(Money(), "", id="money_empty"),
        pytest.param(Money(minimum=Decimal("1")), "0", id="money_below_its_minimum"),
        # 13 digits before the point: too big for any amount column (numeric(14,2), 03 §9).
        pytest.param(Money(), "1000000000000", id="money_thirteen_digits"),
        pytest.param(Percent(), "100.01", id="percent_above_100"),
        # Whole: plain digits only. Python's int() reads "+15" and "1_000" as numbers.
        pytest.param(Whole(maximum=1000), "15.5", id="whole_with_a_fraction"),
        pytest.param(Whole(maximum=1000), "+15", id="whole_with_a_sign"),
        pytest.param(Whole(maximum=1000), "1_000", id="whole_with_an_underscore"),
        pytest.param(Whole(minimum=1, maximum=1000), "0", id="whole_below_its_minimum"),
        # A mistyped 999999999999 days would crash the card that adds it to a date.
        pytest.param(Whole(maximum=1000), "1001", id="whole_above_its_maximum"),
        pytest.param(Whole(maximum=1000), "999999999999", id="whole_far_above_its_maximum"),
        # TimeOfDay: hours and minutes, two digits each, as a browser's time box sends them.
        pytest.param(TimeOfDay(), "25:00", id="time_past_midnight"),
        pytest.param(TimeOfDay(), "7:35", id="time_one_digit_hour"),
        pytest.param(TimeOfDay(), "07:35:00", id="time_with_seconds"),
        pytest.param(TimeOfDay(), "half past seven", id="time_in_words"),
        pytest.param(YesNo(), "yes", id="yesno_word"),
        pytest.param(YesNo(), "True", id="yesno_capital"),
    ],
)
def test_value_kinds_refuse_bad_text(kind: ValueKind[Any], text: str) -> None:
    # A bad value is refused when it is typed, not when a later card reads it: a late fine of "abc"
    # would stop every attendance day that needs it.
    with pytest.raises(ValueError):
        kind.parse(text)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        # Written with two places, the third would be rounded away, half to even (1.005 → "1.00"): not
        # the one shared rounding function (ADR-0024).
        pytest.param(Money(), Decimal("1.005"), id="money_three_places"),
        pytest.param(Percent(), Decimal("2.125"), id="percent_three_places"),
        # A value parse() refuses can't be written either, or it would be stored all the same.
        pytest.param(Money(), Decimal("-500"), id="money_below_zero"),
        pytest.param(Money(), Decimal("Infinity"), id="money_infinite"),
        pytest.param(Money(), Decimal("1500.50"), id="money_with_cents"),
        pytest.param(TimeOfDay(), time(7, 35, 30), id="time_with_seconds"),
    ],
)
def test_to_text_refuses_a_value_it_would_change(kind: ValueKind[Any], value: object) -> None:
    # A service or a seed may write a value with to_text() directly, without parse() first.
    with pytest.raises(ValueError):
        kind.to_text(value)


def test_attendance_rules_have_the_owners_times() -> None:
    # The owner's rules (OWN-7, 02 §12), as a new shop starts with them: the day's seven times in the day's
    # order, and attendance off until the shop switches it on (ADR-0033). The fines have a test of their own
    # (test_fines_start_at_nothing).
    times = {key.key: key.default for key in KEYS if isinstance(key.kind, TimeOfDay)}
    assert times == {
        "attendance.on_time_until": time(7, 35),
        "attendance.second_fine_from": time(8, 0),
        "attendance.review_from": time(8, 30),
        "attendance.afternoon_from": time(12, 0),
        "attendance.midday": time(13, 0),
        "attendance.morning_leave_until": time(13, 30),
        "attendance.closing": time(18, 40),
    }
    # Listed in the day's order too, as the settings page shows them in the registry's order (SHOP-5).
    assert list(times.values()) == sorted(times.values())
    assert REGISTRY["attendance.enabled"].default is False
    # Staff work for the shop, not a side (02 §5): every attendance rule has one value for the whole shop.
    attendance = [key for key in KEYS if key.key.startswith("attendance.")]
    assert len(attendance) == 10
    assert {key.scope for key in attendance} == {Scope.SHOP}


def test_fines_start_at_nothing() -> None:
    # A shop has no fine until its owner types one: this public repo names no real amount (rule 10, Jack, ATT-2),
    # and another shop may fine nobody. The demo types made-up ones (apps/demo/services.py, DEMO_RULES).
    assert REGISTRY["attendance.late_fine"].default == Decimal("0.00")
    assert REGISTRY["attendance.second_fine"].default == Decimal("0.00")
