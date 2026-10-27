"""apps/core/settings_registry.py — the list of rules a shop can set, and how each kind of value is stored (D13).

A rule that changes over time (the late fine, the on-time cut-off, a tolerance) is a setting: a row in
`shops.Setting` with a key from this list, a value as text, and the day it starts (ADR-0013). This file
owns the list. Each key has:
- a kind: what its value is (money, a percent, a whole number, a time of day, yes or no), how that value
  is read from text, and the one form it is stored in ("1000.00", "07:35", "true");
- a default: the value a shop gets until it adds a row, so a new shop works with no rows at all;
- a scope: one value for the whole shop, or a shop value that each side may override;
- a description, for developers. The words a screen shows live in sw.json and en.json (ADR-0032).

`core` is layer 0 and knows nothing of shops (ADR-0035): Setting.clean() (apps/shops/models.py) checks a
row against this list, and get_setting (apps/shops/selectors.py) reads the rows. A new rule is a new entry
here, with all four (03 §5.8); each later card adds the keys it reads.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import StrEnum
from typing import Any

# The shape of a key: an area and a name in small letters and underscores, joined by a dot
# ("attendance.late_fine"). The database holds the same rule (shops_setting_key_shape).
KEY_SHAPE = r"^[a-z_]+(\.[a-z_]+)+$"

# What typed text must look like, checked before Python reads it as a number or a time. [0-9], not \d:
# in Python \d also matches digits from other scripts ("١٠٠" is 100), and int() and Decimal() read them.
# Used with fullmatch(), so the whole text must match, not just its start.
_AMOUNT = re.compile(r"[0-9]+(\.[0-9]{1,2})?")
_DIGITS = re.compile(r"[0-9]+")
_HOURS_MINUTES = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


class ValueKind[T](ABC):
    # One kind of value. A setting's value is stored as text, so each kind says how text becomes a value
    # (parse) and how a value is written back (to_text). parse() refuses bad text with ValueError, which
    # Setting.clean() turns into the code `setting.value_invalid` (ADR-0032). T stands for what parse()
    # returns: a Decimal for money, an int for a count, and so on.

    @abstractmethod
    def parse(self, text: str) -> T: ...

    @abstractmethod
    def to_text(self, value: T) -> str: ...


def _amount(text: str) -> Decimal:
    # Money and percents. Checked as text first, because Decimal() also reads "1e3", "NaN", " 100" and
    # other scripts' digits, none of which a person types as an amount. A minus sign fails here too: no
    # rule in the list takes a negative amount.
    if not _AMOUNT.fullmatch(text):
        raise ValueError(f"{text!r} is not an amount with at most two places.")
    return Decimal(text)


# The kinds are frozen dataclasses: plain values that one key can't change under another, and that
# compare with ==, so Money() == Money().


@dataclass(frozen=True)
class Money(ValueKind[Decimal]):
    # An amount in the shop's currency: exact, never a float (ADR-0024), with at most two places, as every
    # amount is stored (03 §9).
    minimum: Decimal = Decimal("0")

    def parse(self, text: str) -> Decimal:
        value = _amount(text)
        if value < self.minimum:
            raise ValueError(f"{text!r} is below {self.minimum}.")
        return value

    def to_text(self, value: Decimal) -> str:
        # Always two places: "1000" and "1000.0" are both stored as "1000.00". A value parse() made has at
        # most two, so this only adds zeros and never rounds: rounding has one shared function (ADR-0024).
        return f"{value:.2f}"


@dataclass(frozen=True)
class Percent(ValueKind[Decimal]):
    # A share from 0 to 100, exact like money: "2.5" means 2.5 %.

    def parse(self, text: str) -> Decimal:
        value = _amount(text)
        if value > 100:
            raise ValueError(f"{text!r} is above 100.")
        return value

    def to_text(self, value: Decimal) -> str:
        return f"{value:.2f}"


@dataclass(frozen=True)
class Whole(ValueKind[int]):
    # A count of days or minutes, in plain digits: int() alone would also read "+15", " 15" and "1_000".
    minimum: int = 0

    def parse(self, text: str) -> int:
        if not _DIGITS.fullmatch(text):
            raise ValueError(f"{text!r} is not a whole number.")
        value = int(text)
        if value < self.minimum:
            raise ValueError(f"{text!r} is below {self.minimum}.")
        return value

    def to_text(self, value: int) -> str:
        return str(value)


@dataclass(frozen=True)
class TimeOfDay(ValueKind[time]):
    # A time on the shop's clock, such as the on-time cut-off: hours and minutes, two digits each
    # ("07:35"), as a browser's time box sends them. No timezone: it is read against the shop's own day.

    def parse(self, text: str) -> time:
        match = _HOURS_MINUTES.fullmatch(text)
        if match is None:
            raise ValueError(f"{text!r} is not a time written as HH:MM.")
        return time(int(match[1]), int(match[2]))

    def to_text(self, value: time) -> str:
        return value.strftime("%H:%M")


@dataclass(frozen=True)
class YesNo(ValueKind[bool]):
    # On or off. Only "true" and "false", the way JSON writes them, so screens and devices read one form.

    def parse(self, text: str) -> bool:
        if text == "true":
            return True
        if text == "false":
            return False
        raise ValueError(f"{text!r} is not true or false.")

    def to_text(self, value: bool) -> str:
        return "true" if value else "false"


class Scope(StrEnum):
    # Where a rule's value may be set. SHOP: one value for the whole shop. SIDE: a shop value that each
    # side may override with a row of its own; a side's row beats the shop's (02 §4).
    SHOP = "shop"
    SIDE = "side"


@dataclass(frozen=True)
class SettingKey[T]:
    # One rule in the list. Generic in T, the type its kind gives: get_setting(LATE_FINE, ...) returns a
    # Decimal and get_setting(ON_TIME_UNTIL, ...) a time, and mypy knows which, so no caller guesses.
    key: str
    kind: ValueKind[T]
    default: T
    scope: Scope
    description: str


# --- The rules R1 and R1b read first (04 CORE-4).

# Attendance belongs to the shop, not a side: staff work for the shop (02 §5), so both rules are SHOP.
ON_TIME_UNTIL = SettingKey(
    key="attendance.on_time_until",
    kind=TimeOfDay(),
    default=time(7, 35),
    scope=Scope.SHOP,
    description="Arriving by this time is on time; after it, late (spec §8.1).",
)
LATE_FINE = SettingKey(
    key="attendance.late_fine",
    kind=Money(),
    default=Decimal("1000.00"),
    scope=Scope.SHOP,
    description="Taken off a late day's pay (spec §8.1).",
)
# Prices are shared by the sides (ADR-0001), so their rounding is too. At least 1: a step of 0 would
# leave nothing to round to.
ROUNDING_STEP = SettingKey(
    key="money.rounding_step",
    kind=Money(minimum=Decimal("1")),
    default=Decimal("1.00"),
    scope=Scope.SHOP,
    description="Line totals are rounded half-up to a multiple of this (03 §8).",
)
# At least 1: an idle lock of 0 minutes would lock a counter screen at once.
IDLE_MINUTES = SettingKey(
    key="session.idle_minutes",
    kind=Whole(minimum=1),
    default=15,
    scope=Scope.SHOP,
    description="Minutes without use before a counter screen locks (03 §5.9).",
)

# Each side has its own drawer and its own stock (ADR-0001), so these four may differ per side. The two
# tolerances are 0 until the owner agrees values (02 §20, item 2): every difference is flagged.
CASH_TOLERANCE = SettingKey(
    key="cash.tolerance",
    kind=Money(),
    default=Decimal("0.00"),
    scope=Scope.SIDE,
    description="A drawer may be off by this much before a Flag is raised.",
)
COUNT_TOLERANCE_PCT = SettingKey(
    key="count.tolerance_pct",
    kind=Percent(),
    default=Decimal("0.00"),
    scope=Scope.SIDE,
    description="A stock count may be off by this percent before a Flag is raised.",
)
EXPIRY_ALERT_DAYS = SettingKey(
    key="expiry.alert_days",
    kind=Whole(),
    default=90,
    scope=Scope.SIDE,
    description="A batch shows an expiry alert this many days before it expires (02 §15, item 12).",
)
BLOCK_NEGATIVE_STOCK = SettingKey(
    key="stock.block_negative",
    kind=YesNo(),
    default=False,
    scope=Scope.SIDE,
    description="Off: a sale may take stock below zero, with a warning and a Flag (ADR-0010).",
)

# Every key, in one place. Any: the keys hold values of different types, so the list can't name one.
KEYS: tuple[SettingKey[Any], ...] = (
    ON_TIME_UNTIL,
    LATE_FINE,
    ROUNDING_STEP,
    IDLE_MINUTES,
    CASH_TOLERANCE,
    COUNT_TOLERANCE_PCT,
    EXPIRY_ALERT_DAYS,
    BLOCK_NEGATIVE_STOCK,
)

# A key found by its name, as a row or a screen names it ("attendance.late_fine").
# test_each_key_listed_once checks that no name is listed twice: here the last one would win silently.
REGISTRY: dict[str, SettingKey[Any]] = {key.key: key for key in KEYS}
