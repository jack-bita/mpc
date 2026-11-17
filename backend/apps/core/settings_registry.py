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

Once a key has rows, its kind and its limits never get stricter. get_setting reads old rows too (a day in
March, for a pay run), so a row that no longer parses would break every read of its days. A stricter rule
is a new key, with rows of its own. Looser is safe: every old row still parses.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

# The shape of a key: an area and a name in small letters and underscores, joined by a dot
# ("attendance.late_fine"). The database holds the same rule (shops_setting_key_shape).
KEY_SHAPE = r"^[a-z_]+(\.[a-z_]+)+$"

# What typed text must look like, checked before Python reads it as a number or a time. [0-9], not \d:
# in Python \d also matches digits from other scripts ("١٠٠" is 100), and int() and Decimal() read them.
# Used with fullmatch(), so the whole text must match, not just its start.
# At most 12 digits before the point: every amount column is numeric(14,2) (03 §9), so a later card that
# copies a rule's value onto a record (T4) can always store it.
_AMOUNT = re.compile(r"[0-9]{1,12}(\.[0-9]{1,2})?")
_DIGITS = re.compile(r"[0-9]+")
_HOURS_MINUTES = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


class ValueKind[T](ABC):
    # One kind of value. A setting's value is stored as text, so each kind says how text becomes a value
    # (parse) and how a value is written back (to_text). parse() refuses bad text with ValueError, which
    # Setting.clean() turns into the code `setting.value_invalid` (ADR-0032). T stands for what parse()
    # returns: a Decimal for money, an int for a count, and so on.

    # The kind's own name, as a device reads it: the bootstrap sends it with each rule's default (SYNC-2), so a
    # device knows to read "07:35" as a time and "true" as yes. Fixed once sent, as a device's code reads by it.
    code: ClassVar[str]

    @abstractmethod
    def parse(self, text: str) -> T: ...

    @abstractmethod
    def _write(self, value: T) -> str: ...

    def to_text(self, value: T) -> str:
        # Each kind writes its own form (_write); this checks that the text reads back as the very same
        # value. Otherwise money written with two places would round a third one away, half to even
        # (1.005 → "1.00"), past the one shared rounding function (ADR-0024), and a value parse() refuses
        # (a negative amount, a time with seconds) would be stored all the same. A service or a seed may
        # call this directly, without parse() first.
        text = self._write(value)
        if self.parse(text) != value:
            raise ValueError(f"{value!r} can't be stored as {text!r} without changing it.")
        return text


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
    # An amount in the shop's currency: exact, never a float (ADR-0024), in whole shillings (Jack, 16 Nov 2026). It is
    # stored with two places, as every amount is (03 §9), but those are always zeros: the shop's money has no cents,
    # and every screen writes money with formatMoney, which refuses cents, so a rule with them (a rounding step of
    # 2.50, a late fine of 1,000.50) would stop each screen that shows an amount it made (04 §20, item 25).
    code: ClassVar[str] = "money"
    minimum: Decimal = Decimal("0")

    def parse(self, text: str) -> Decimal:
        value = _amount(text)
        if value < self.minimum:
            raise ValueError(f"{text!r} is below {self.minimum}.")
        # "1500.00" is whole; "1500.50" isn't. to_integral_value() drops the places without rounding the check away.
        if value != value.to_integral_value():
            raise ValueError(f"{text!r} has cents: a money rule is whole shillings.")
        return value

    def _write(self, value: Decimal) -> str:
        # Always two places: "1000" and "1000.0" are both stored as "1000.00". It only adds zeros:
        # to_text() refuses a value this would round.
        return f"{value:.2f}"


@dataclass(frozen=True)
class Percent(ValueKind[Decimal]):
    # A share from 0 to 100, exact like money: "2.5" means 2.5 %.
    code: ClassVar[str] = "percent"

    def parse(self, text: str) -> Decimal:
        value = _amount(text)
        if value > 100:
            raise ValueError(f"{text!r} is above 100.")
        return value

    def _write(self, value: Decimal) -> str:
        return f"{value:.2f}"


# kw_only: Whole(maximum=1440) names each limit, and `maximum` can be required although `minimum` has a
# default (in a plain dataclass, a field with no default can't follow one with a default).
@dataclass(frozen=True, kw_only=True)
class Whole(ValueKind[int]):
    # A count of days or minutes, in plain digits: int() alone would also read "+15", " 15" and "1_000".
    # Every key names its own maximum: a mistyped 999999999999 days would pass today and crash the card
    # that adds it to a date (OverflowError), so it is refused when it is typed.
    code: ClassVar[str] = "whole"
    maximum: int
    minimum: int = 0

    def parse(self, text: str) -> int:
        if not _DIGITS.fullmatch(text):
            raise ValueError(f"{text!r} is not a whole number.")
        value = int(text)
        if value < self.minimum:
            raise ValueError(f"{text!r} is below {self.minimum}.")
        if value > self.maximum:
            raise ValueError(f"{text!r} is above {self.maximum}.")
        return value

    def _write(self, value: int) -> str:
        return str(value)


@dataclass(frozen=True)
class TimeOfDay(ValueKind[time]):
    # A time on the shop's clock, such as the on-time cut-off: hours and minutes, two digits each
    # ("07:35"), as a browser's time box sends them. No timezone: it is read against the shop's own day.
    code: ClassVar[str] = "time"

    def parse(self, text: str) -> time:
        match = _HOURS_MINUTES.fullmatch(text)
        if match is None:
            raise ValueError(f"{text!r} is not a time written as HH:MM.")
        return time(int(match[1]), int(match[2]))

    def _write(self, value: time) -> str:
        return value.strftime("%H:%M")


@dataclass(frozen=True)
class YesNo(ValueKind[bool]):
    # On or off. Only "true" and "false", the way JSON writes them, so screens and devices read one form.
    code: ClassVar[str] = "yes_no"

    def parse(self, text: str) -> bool:
        if text == "true":
            return True
        if text == "false":
            return False
        raise ValueError(f"{text!r} is not true or false.")

    def _write(self, value: bool) -> str:
        return "true" if value else "false"


# Every kind, in one place: the names a device may meet (the bootstrap's choices for a rule's kind, SYNC-2).
# test_each_kind_has_a_name_of_its_own holds that each has a name of its own and that every key's kind is here.
KINDS: tuple[type[ValueKind[Any]], ...] = (Money, Percent, Whole, TimeOfDay, YesNo)


class Scope(StrEnum):
    # Where a rule's value may be set. SHOP: one value for the whole shop. SIDE: one value for each side,
    # set one side at a time (Jack, SHOP-3): set_setting writes no whole-shop row for it. get_setting still
    # reads one, behind the side's own row (02 §4), which only code that skips set_setting could write.
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


# --- The attendance day: the owner's rules (OWN-7, 16 Nov 2026; 02 §12, the day's rules). CORE-4 put the first
# two here, the on-time cut-off and the late fine; ATT-2 added the rest.
#
# Attendance belongs to the shop, not a side: staff work for the shop (02 §5), so every rule here is SHOP.
# Each time is a minute on the shop's clock, as the counter shows it ("07:35"): a clock-in at 07:35:40 shows
# 07:35, so it is on time. "By" and "from" take their own minute; "before" and "after" don't. The windows
# follow one another through the day, with the owner's times:
#
#   arrives   by 07:35 on time · before 08:00 first fine · before 08:30 second fine · before 12:00 dharura
#             · 12:00 to 13:00 the afternoon's half day · after 13:00 dharura
#   leaves    before 13:00 dharura · 13:00 to 13:30 the morning's half day · before 18:40 dharura
#             · from 18:40 the full day
#
# Dharura is the owner's word for a day that needs review: a manager or the owner decides it. The times are
# MPC's, as a new shop starts with them until its owner types its own. These keys only say the rules: ATT-4
# works out each day from them.

# The switch for the whole part (ADR-0033): attendance starts on the day the owner chooses, so it is off until
# a shop switches it on. A dated rule, so "on from 1 December" waits for its day by itself. While it is off,
# the counter shows no Mahudhurio; the server still takes a clock-in that comes, as a laptop that hadn't heard
# of the switch yet would otherwise see its taps refused.
ATTENDANCE_ON = SettingKey(
    key="attendance.enabled",
    kind=YesNo(),
    default=False,
    scope=Scope.SHOP,
    description="On: the counter shows Mahudhurio, and days count from the day it is on (ADR-0033).",
)
ON_TIME_UNTIL = SettingKey(
    key="attendance.on_time_until",
    kind=TimeOfDay(),
    default=time(7, 35),
    scope=Scope.SHOP,
    description="Arriving by this minute is on time; after it, and before second_fine_from, late with the first fine.",
)
# Both fines start at 0, so a shop has no fine until its owner types one: this public repo names no real amount
# (rule 10, Jack, 16 Nov 2026), and another shop may fine nobody. The first fine had an amount as its default until
# ATT-2: a default is not a limit, so lowering it leaves every old row readable (see the top of this file), and no
# real shop had rows yet.
LATE_FINE = SettingKey(
    key="attendance.late_fine",
    kind=Money(),
    default=Decimal("0.00"),
    scope=Scope.SHOP,
    description="The first fine: taken off the pay of a day that arrived after on_time_until, before second_fine_from.",
)
SECOND_FINE_FROM = SettingKey(
    key="attendance.second_fine_from",
    kind=TimeOfDay(),
    default=time(8, 0),
    scope=Scope.SHOP,
    description="Arriving from this minute, and before review_from, is late with the second fine.",
)
SECOND_FINE = SettingKey(
    key="attendance.second_fine",
    kind=Money(),
    default=Decimal("0.00"),
    scope=Scope.SHOP,
    description="The second fine: taken off the pay of a day that arrived from second_fine_from, before review_from.",
)
REVIEW_FROM = SettingKey(
    key="attendance.review_from",
    kind=TimeOfDay(),
    default=time(8, 30),
    scope=Scope.SHOP,
    description="Arriving from this minute, and before afternoon_from, makes the day need review (dharura).",
)
AFTERNOON_FROM = SettingKey(
    key="attendance.afternoon_from",
    kind=TimeOfDay(),
    default=time(12, 0),
    scope=Scope.SHOP,
    description="Arriving from this minute to midday, and leaving from closing, is the afternoon's half day.",
)
MIDDAY = SettingKey(
    key="attendance.midday",
    kind=TimeOfDay(),
    default=time(13, 0),
    scope=Scope.SHOP,
    description="The morning's half ends and the afternoon's starts: arriving after it, or leaving before it, "
    "needs review.",
)
MORNING_LEAVE_UNTIL = SettingKey(
    key="attendance.morning_leave_until",
    kind=TimeOfDay(),
    default=time(13, 30),
    scope=Scope.SHOP,
    description="Leaving from midday to this minute, after a morning arrival, is the morning's half day; "
    "after it, and before closing, the day needs review.",
)
CLOSING = SettingKey(
    key="attendance.closing",
    kind=TimeOfDay(),
    default=time(18, 40),
    scope=Scope.SHOP,
    description="Leaving from this minute is the full day; the afternoon's half day stays until it.",
)

# The day's seven times in the day's order. Each is after the one before it, strictly, on every day, so no minute lands
# in two windows: an on-time cut-off of 08:00 beside a second fine from 08:00 would make a clock-in at 08:00 both on
# time and late, and ATT-4 would pay that day two ways. set_setting refuses a time that isn't after the one before it
# and before the one after it, on its start day and on each later day one of those two changes (setting.out_of_order,
# apps/shops/services.py).
DAY_IN_ORDER: tuple[SettingKey[time], ...] = (
    ON_TIME_UNTIL,
    SECOND_FINE_FROM,
    REVIEW_FROM,
    AFTERNOON_FROM,
    MIDDAY,
    MORNING_LEAVE_UNTIL,
    CLOSING,
)

# --- The other rules R1 reads first (04 CORE-4).

# Prices are shared by the sides (ADR-0001), so their rounding is too. At least 1: a step of 0 would
# leave nothing to round to.
ROUNDING_STEP = SettingKey(
    key="money.rounding_step",
    kind=Money(minimum=Decimal("1")),
    default=Decimal("1.00"),
    scope=Scope.SHOP,
    description="Line totals are rounded half-up to a multiple of this (03 §8).",
)
# At least 1: an idle lock of 0 minutes would lock a counter screen at once. At most 1,440, one day: a
# longer one is no lock at all on a shared counter device.
IDLE_MINUTES = SettingKey(
    key="session.idle_minutes",
    kind=Whole(minimum=1, maximum=1440),
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
# At most 3,650 days, ten years: an alert further ahead would flag every batch on the shelf.
EXPIRY_ALERT_DAYS = SettingKey(
    key="expiry.alert_days",
    kind=Whole(maximum=3650),
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
# Each area in the order the settings page shows it (SHOP-5): the attendance day's rules in the day's order,
# its switch first.
KEYS: tuple[SettingKey[Any], ...] = (
    ATTENDANCE_ON,
    ON_TIME_UNTIL,
    LATE_FINE,
    SECOND_FINE_FROM,
    SECOND_FINE,
    REVIEW_FROM,
    AFTERNOON_FROM,
    MIDDAY,
    MORNING_LEAVE_UNTIL,
    CLOSING,
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
