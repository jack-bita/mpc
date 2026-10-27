"""apps/core/tests/test_settings_registry.py — tests for the list of rules a shop can set (D13, ADR-0013).

Every rule that changes over time is a setting: a key from this list, with the kind of value it takes, a
default, and a scope (one value for the whole shop, or one a side may override). A setting's value is
stored as text, in one form per kind, so these tests check both ways: text in, a value out, and back.

    kind        typed      value               stored
    Money       "1000"     Decimal("1000")     "1000.00"
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
    REGISTRY,
    Money,
    Percent,
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


def test_each_key_listed_once() -> None:
    # REGISTRY is built from KEYS by name. A key listed twice would keep only its last entry, and the
    # first one's kind, default or scope would be lost without a word.
    assert len(REGISTRY) == len(KEYS)


@pytest.mark.parametrize(
    ("kind", "text", "value", "stored"),
    [
        pytest.param(Money(), "1000", Decimal("1000"), "1000.00", id="money_whole_shillings"),
        pytest.param(Money(), "1500.5", Decimal("1500.5"), "1500.50", id="money_one_place"),
        pytest.param(Money(), "0", Decimal("0"), "0.00", id="money_zero"),
        pytest.param(Percent(), "2.5", Decimal("2.5"), "2.50", id="percent"),
        pytest.param(Percent(), "100", Decimal("100"), "100.00", id="percent_all"),
        pytest.param(Whole(), "90", 90, "90", id="whole"),
        pytest.param(Whole(), "090", 90, "90", id="whole_leading_zero"),
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
        # Money: an exact amount in plain digits, with at most two places (ADR-0024).
        pytest.param(Money(), "abc", id="money_not_a_number"),
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
        pytest.param(Percent(), "100.01", id="percent_above_100"),
        # Whole: plain digits only. Python's int() reads "+15" and "1_000" as numbers.
        pytest.param(Whole(), "15.5", id="whole_with_a_fraction"),
        pytest.param(Whole(), "+15", id="whole_with_a_sign"),
        pytest.param(Whole(), "1_000", id="whole_with_an_underscore"),
        pytest.param(Whole(minimum=1), "0", id="whole_below_its_minimum"),
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
        pytest.param(TimeOfDay(), time(7, 35, 30), id="time_with_seconds"),
    ],
)
def test_to_text_refuses_a_value_it_would_change(kind: ValueKind[Any], value: object) -> None:
    # A service or a seed may write a value with to_text() directly, without parse() first.
    with pytest.raises(ValueError):
        kind.to_text(value)
