"""apps/staffpay/tests/test_attendance_day.py — the day's rule (ATT-4; spec §8.1, 02 §12), test by test: what one
worker's day was, from that day's taps and that day's rules (work_out_day, apps/staffpay/calculations.py).

Each row of the owner's table in spec §8.1 is a test named after it, so the code says exactly what he said:

    arrives   by 07:35 on time · before 08:00 the first fine · before 08:30 the second fine · before 12:00 dharura
              · 12:00 to 13:00 the afternoon's half day · after 13:00 dharura
    leaves    before 13:00 dharura · 13:00 to 13:30 the morning's half day, a late arrival's fine kept
              · before 18:40 dharura · from 18:40 the full day, or the late one with its fine · never: dharura
    no tap    absent · a tap whose time can't be trusted, or a Toka with no Ingia: dharura
    Toka      ends the day: the first one after the first Ingia counts, and no tap after it (no lunch Toka at MPC)

Every window is a minute on the shop's clock, as the counter shows it (SYNC-11): a tap's seconds never count, and the
server's UTC is never the shop's time; shop_minute turns a tap's time into that minute. Pure: no database, no clock of
its own. The fines are the demo's made-up 500 and 1,500: the repo is public, so no real amount (rule 10).
"""

import dataclasses
import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.staffpay.calculations import NO_FINE, DayResult, DayRules, Tap, shop_minute, work_out_day
from apps.staffpay.models import ClockKind, DayStatus

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")
FIRST_FINE = Decimal("500.00")
SECOND_FINE = Decimal("1500.00")

# The owner's day (OWN-7, ATT-2), with the demo's made-up fines.
OWNERS_DAY = DayRules(
    on_time_until=dt.time(7, 35),
    second_fine_from=dt.time(8, 0),
    review_from=dt.time(8, 30),
    afternoon_from=dt.time(12, 0),
    midday=dt.time(13, 0),
    morning_leave_until=dt.time(13, 30),
    closing=dt.time(18, 40),
    late_fine=FIRST_FINE,
    second_fine=SECOND_FINE,
)
CLOSING = "18:40"


def at(minute: str) -> dt.time:
    # "07:50" as the minute it names on the shop's clock.
    hour, rest = minute.split(":")
    return dt.time(int(hour), int(rest))


def day(arrives: str | None, leaves: str | None = None, rules: DayRules = OWNERS_DAY) -> DayResult:
    # One worker's day as the owner's table says it: in at "07:50", out at "18:40"; None for a tap never made.
    taps = []
    if arrives is not None:
        taps.append(Tap(ClockKind.IN, at(arrives)))
    if leaves is not None:
        taps.append(Tap(ClockKind.OUT, at(leaves)))
    return work_out_day(taps, rules)


def dharura(arrives: str | None, leaves: str | None) -> DayResult:
    # A day that needs review: no fine, as a manager or the owner decides it (ATT-6); its taps kept, for them to see.
    return DayResult(
        DayStatus.NEEDS_REVIEW,
        NO_FINE,
        None if arrives is None else at(arrives),
        None if leaves is None else at(leaves),
    )


def test_shop_minute_reads_the_shops_clock() -> None:
    # The database keeps every time in UTC: Asha's tap at 07:35:40 in Arusha comes back as 04:35:40. The windows are
    # the shop's, three hours ahead, so the minute is read on the shop's clock, or she would look three hours early.
    stored = dt.datetime(2026, 11, 10, 4, 35, 40, tzinfo=dt.UTC)
    assert shop_minute(stored, ARUSHA) == dt.time(7, 35)


def test_shop_minute_drops_the_seconds() -> None:
    # 07:35:59 still shows 07:35 on the laptop, so it is still on time: the minute is cut, never rounded up to 07:36.
    tap = dt.datetime(2026, 11, 10, 7, 35, 59, 999999, tzinfo=ARUSHA)
    assert shop_minute(tap, ARUSHA) == dt.time(7, 35)


def test_shop_minute_refuses_a_time_with_no_zone() -> None:
    # A time with no zone says nothing of where it was read: Python would take it on the server's own clock, three
    # hours off Arusha's, and Asha's 07:35 would turn into 10:35, a day of dharura. So it fails loudly instead.
    with pytest.raises(ValueError):
        shop_minute(dt.datetime(2026, 11, 10, 7, 35), ARUSHA)


def test_a_tap_with_seconds_refused() -> None:
    # 07:35:40 is after 07:35, so a tap that kept its seconds would fine Asha though the counter showed 07:35. A tap's
    # minute comes from shop_minute, which drops them; one built without it is a bug in our code, so it fails loudly.
    with pytest.raises(ValueError):
        Tap(ClockKind.IN, dt.time(7, 35, 40))
    with pytest.raises(ValueError):
        Tap(ClockKind.OUT, dt.time(18, 40, 0, 1))


# The owner's table, spec §8.1: the arrivals, each leaving at closing.


def test_arrives_0720_leaves_at_closing_full_day() -> None:
    assert day("07:20", CLOSING) == DayResult(DayStatus.ON_TIME, NO_FINE, at("07:20"), at(CLOSING))


def test_arrives_0750_full_day_minus_fine() -> None:
    assert day("07:50", CLOSING) == DayResult(DayStatus.LATE, FIRST_FINE, at("07:50"), at(CLOSING))


def test_arrives_0810_full_day_minus_the_second_fine() -> None:
    assert day("08:10", CLOSING) == DayResult(DayStatus.LATE, SECOND_FINE, at("08:10"), at(CLOSING))


def test_arrives_0900_needs_review() -> None:
    assert day("09:00", CLOSING) == dharura("09:00", CLOSING)


def test_arrives_1230_half_day() -> None:
    # The afternoon's half day: no fine, as arriving for the afternoon is not arriving late.
    assert day("12:30", CLOSING) == DayResult(DayStatus.HALF, NO_FINE, at("12:30"), at(CLOSING))


def test_arrives_1330_needs_review() -> None:
    assert day("13:30", CLOSING) == dharura("13:30", CLOSING)


# The edges: "by" and "from" take their own minute, "before" and "after" don't (02 §12). One minute either side of
# each edge, as a mistake of one minute costs a worker a fine.


@pytest.mark.parametrize(
    ("arrives", "status", "fine"),
    [
        ("07:35", DayStatus.ON_TIME, NO_FINE),  # by 07:35: on time
        ("07:36", DayStatus.LATE, FIRST_FINE),  # after it: the first fine
        ("07:59", DayStatus.LATE, FIRST_FINE),  # before 08:00: still the first
        ("08:00", DayStatus.LATE, SECOND_FINE),  # from 08:00: the second
        ("08:29", DayStatus.LATE, SECOND_FINE),  # before 08:30: still the second
        ("08:30", DayStatus.NEEDS_REVIEW, NO_FINE),  # from 08:30: dharura
        ("11:59", DayStatus.NEEDS_REVIEW, NO_FINE),  # before 12:00: still dharura
        ("12:00", DayStatus.HALF, NO_FINE),  # from 12:00: the afternoon's half day
        ("13:00", DayStatus.HALF, NO_FINE),  # to 13:00: still the afternoon's
        ("13:01", DayStatus.NEEDS_REVIEW, NO_FINE),  # after 13:00: dharura
    ],
)
def test_each_arrival_window_takes_its_own_minute(arrives: str, status: DayStatus, fine: Decimal) -> None:
    assert day(arrives, CLOSING) == DayResult(status, fine, at(arrives), at(CLOSING))


def test_a_tap_at_073540_is_on_time() -> None:
    # Asha taps Ingia at 07:35:40 in Arusha, which the database keeps as 04:35:40 in UTC: the shop's minute is 07:35.
    tapped = dt.datetime(2026, 11, 10, 4, 35, 40, tzinfo=dt.UTC)
    taps = [Tap(ClockKind.IN, shop_minute(tapped, ARUSHA)), Tap(ClockKind.OUT, at(CLOSING))]
    assert work_out_day(taps, OWNERS_DAY).status == DayStatus.ON_TIME


def test_a_shop_with_no_fine_takes_nothing() -> None:
    # Every shop starts with both fines at 0 (ATT-2): a late day is still late, with nothing taken off.
    no_fines = dataclasses.replace(OWNERS_DAY, late_fine=NO_FINE, second_fine=NO_FINE)
    assert day("07:50", CLOSING, no_fines) == DayResult(DayStatus.LATE, NO_FINE, at("07:50"), at(CLOSING))
    assert day("08:10", CLOSING, no_fines) == DayResult(DayStatus.LATE, NO_FINE, at("08:10"), at(CLOSING))


def test_a_day_reads_the_rules_it_is_given() -> None:
    # A1: a day uses the rules in force on its date, which ATT-10 hands in. From 1 December the owner gives everyone
    # until 07:45, and the first fine is 1,000: 07:40 is on time that day, and 07:50 loses the new fine, not the old.
    december = dataclasses.replace(OWNERS_DAY, on_time_until=dt.time(7, 45), late_fine=Decimal("1000.00"))
    assert day("07:40", CLOSING, december).status == DayStatus.ON_TIME
    assert day("07:50", CLOSING, december) == DayResult(DayStatus.LATE, Decimal("1000.00"), at("07:50"), at(CLOSING))


# The owner's table, spec §8.1: the leavings.


def test_arrives_0720_leaves_1310_half_day() -> None:
    assert day("07:20", "13:10") == DayResult(DayStatus.HALF, NO_FINE, at("07:20"), at("13:10"))


def test_arrives_0720_leaves_1200_needs_review() -> None:
    assert day("07:20", "12:00") == dharura("07:20", "12:00")


def test_arrives_0720_leaves_1600_needs_review() -> None:
    assert day("07:20", "16:00") == dharura("07:20", "16:00")


def test_arrives_0720_never_clocks_out_needs_review() -> None:
    # No Toka: nobody knows when they left, so a manager decides (02 §20, item 6).
    assert day("07:20") == dharura("07:20", None)


def test_arrives_0750_leaves_1310_half_day_minus_fine() -> None:
    # The owner's answer (19 Nov 2026, through Jack): a late arrival who leaves for the morning's half day loses the
    # fine of their arrival too. The first fine for 07:50; the second for 08:10.
    assert day("07:50", "13:10") == DayResult(DayStatus.HALF, FIRST_FINE, at("07:50"), at("13:10"))
    assert day("08:10", "13:10") == DayResult(DayStatus.HALF, SECOND_FINE, at("08:10"), at("13:10"))


def test_arrives_1230_leaves_1600_needs_review() -> None:
    # The afternoon's half day stays until closing (02 §12): leaving at 16:00, nobody knows what half it was.
    assert day("12:30", "16:00") == dharura("12:30", "16:00")


@pytest.mark.parametrize(
    ("leaves", "status"),
    [
        ("12:59", DayStatus.NEEDS_REVIEW),  # before 13:00: dharura
        ("13:00", DayStatus.HALF),  # from 13:00: the morning's half day
        ("13:30", DayStatus.HALF),  # to 13:30: still the morning's
        ("13:31", DayStatus.NEEDS_REVIEW),  # after 13:30, and before 18:40: dharura
        ("18:39", DayStatus.NEEDS_REVIEW),  # before 18:40: still dharura
        ("18:40", DayStatus.ON_TIME),  # from 18:40: the full day
    ],
)
def test_each_leaving_window_takes_its_own_minute(leaves: str, status: DayStatus) -> None:
    assert day("07:20", leaves) == DayResult(status, NO_FINE, at("07:20"), at(leaves))


# The days the table has no time for: no tap, or a tap that can't be read.


def test_doesnt_come_absent() -> None:
    # The table's last row: no tap all day, no pay. Whether it was office duty, permission or a no-show is ATT-6's.
    assert day(None) == DayResult(DayStatus.ABSENT, NO_FINE, None, None)


def test_a_tap_with_no_trusted_time_needs_review() -> None:
    # Asha taps Ingia at 07:20, then again, and the second tap's time can't be trusted (`unverified`, ATT-1): the
    # laptop's clock moved, for that tap or for the one before it, so her 07:20 can't be believed either. Whatever the
    # other taps say, a manager decides.
    taps = [Tap(ClockKind.IN, at("07:20")), Tap(ClockKind.IN, None), Tap(ClockKind.OUT, at(CLOSING))]
    assert work_out_day(taps, OWNERS_DAY) == dharura("07:20", CLOSING)
    # And Juma's only Ingia can't be trusted: his Toka alone says nothing of when he came.
    assert work_out_day([Tap(ClockKind.IN, None), Tap(ClockKind.OUT, at(CLOSING))], OWNERS_DAY) == dharura(
        None, CLOSING
    )


def test_clock_out_without_clock_in_needs_review() -> None:
    # Toka at 18:40 and no Ingia: nobody knows when they came, so nobody knows the fine.
    assert day(None, CLOSING) == dharura(None, CLOSING)


def test_the_first_toka_ends_the_day() -> None:
    # At MPC Toka ends the day: nobody taps out for lunch (Jack, ATT-4's review). So the day reads from the first Ingia
    # to the first Toka after it, and a tap after that Toka counts for nothing.
    # Asha taps out at 13:05 and in again at 13:40: her 13:05 ended the day, the morning's half.
    asha = [Tap(ClockKind.IN, at("07:20")), Tap(ClockKind.OUT, at("13:05")), Tap(ClockKind.IN, at("13:40"))]
    assert work_out_day(asha, OWNERS_DAY) == DayResult(DayStatus.HALF, NO_FINE, at("07:20"), at("13:05"))
    # Juma taps Toka at 13:05 by mistake, Ingia at 13:10, and Toka at closing: still the morning's half, which a manager
    # can mend with a reason (ATT-6), the taps all kept.
    juma = [*asha[:2], Tap(ClockKind.IN, at("13:10")), Tap(ClockKind.OUT, at(CLOSING))]
    assert work_out_day(juma, OWNERS_DAY) == DayResult(DayStatus.HALF, NO_FINE, at("07:20"), at("13:05"))
    # Mparee taps Toka by mistake at 11:06, and Ingia again at 11:07: his day ended before midday, so a manager decides.
    mparee = [Tap(ClockKind.IN, at("07:20")), Tap(ClockKind.OUT, at("11:06")), Tap(ClockKind.IN, at("11:07"))]
    assert work_out_day(mparee, OWNERS_DAY) == dharura("07:20", "11:06")


def test_a_tap_made_twice_counts_once() -> None:
    # Ingia tapped twice by mistake, and Toka too, handed in in no order, as ATT-10 may hand the taps in any order: the
    # first Ingia starts the day, and the first Toka after it ends the day.
    taps = [
        Tap(ClockKind.OUT, at("18:42")),
        Tap(ClockKind.IN, at("07:22")),
        Tap(ClockKind.OUT, at(CLOSING)),
        Tap(ClockKind.IN, at("07:20")),
    ]
    assert work_out_day(taps, OWNERS_DAY) == DayResult(DayStatus.ON_TIME, NO_FINE, at("07:20"), at(CLOSING))


def test_a_toka_before_the_ingia_ends_nothing() -> None:
    # A Toka at 07:00, before any Ingia, ends no day: the day hadn't started. The day runs from 07:20 to closing.
    taps = [Tap(ClockKind.OUT, at("07:00")), Tap(ClockKind.IN, at("07:20")), Tap(ClockKind.OUT, at(CLOSING))]
    assert work_out_day(taps, OWNERS_DAY) == DayResult(DayStatus.ON_TIME, NO_FINE, at("07:20"), at(CLOSING))
