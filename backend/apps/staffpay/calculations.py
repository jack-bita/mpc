"""apps/staffpay/calculations.py — pure sums for attendance and pay: no database, no clock of their own (03 §5.1).

The time check (ATT-1, 02 §12): how far a clock-in's time can be trusted, from the evidence about the laptop's clock.
A laptop's clock can be moved by anyone, and an offline clock-in carries only its time, so the server keeps that time
only when no sign says the clock moved. Server only: the laptop never judges its own clock, so this one has no
TypeScript twin and no shared test vectors (03 §8).

The day's rule (ATT-4, spec §8.1): what one worker's day was, from that day's taps and that day's rules.

    in 07:20, out 18:40   → on time            in 08:10, out 18:40   → late, the second fine
    in 07:50, out 18:40   → late, first fine    in 12:30, out 18:40   → the afternoon's half day
    in 07:20, out 13:10   → the morning's half  in 07:50, out 13:10   → the morning's half, less the first fine
    in 09:00, or no out   → dharura, a manager or the owner decides it

Every window of the owner's day is a minute on the shop's clock, which shop_minute reads from a tap's time. The rule
only answers: ATT-10 finds the taps and the rules in force that day, hands them in, and keeps the answer. Server only
too, as the day is worked out on the server (03 §5.8).
"""

import datetime as dt
import enum
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from apps.staffpay.models import ClockKind, DayStatus, TimeCheck

# A clock-in the laptop sent within 2 minutes of the tap, both by its own clock, was made online: the push runs 2
# seconds after a new record (03 §6.5), and a retry or two still fits. Its time is the server's time of the tap: the
# push's arrival less the wait.
ONLINE_WITHIN = dt.timedelta(minutes=2)
# How far two clocks may disagree before it is a sign the laptop's moved: a laptop's clock drifts a little while it
# is offline, and a push takes a moment to arrive. Past it, a worker could win a late fine's worth, so it stays small.
CLOCK_SLACK = dt.timedelta(minutes=2)


class Sign(enum.Enum):
    # The four signs that a laptop's clock moved (02 §12), by name, so the saving code knows which it found: sign 1
    # says two records disagree, and its flag names the maker of the record before too (Jack, ATT-1's review). And a
    # fifth reason no time can be trusted, which is no clock's: the record came in a rescue file (SYNC-12).
    RECORD_BEFORE_IS_LATER = "record_before_is_later"  # 1. its record before has a later time
    BEFORE_THE_LAST_SERVER_TIME = "before_the_last_server_time"  # 2. it is before a time the server had told it
    CLOCK_OFF_AT_SENDING = "clock_off_at_sending"  # 3. the laptop's clock was off as it sent
    AFTER_SENDING = "after_sending"  # 4. it is after the laptop's own clock as it sent
    CARRIED = "carried"  # 5. it came in a rescue file from another laptop, plain text anyone could edit


@dataclass(frozen=True)
class Evidence:
    # What the server knows of one clock-in's time (02 §12). Three times by the laptop's clock, which may be wrong.
    client_time: dt.datetime  # when the worker tapped
    sent_at: dt.datetime  # when the laptop sent the push
    time_before: dt.datetime | None  # its record numbered before this one; None for its first
    # And two the laptop's clock can't move.
    received_at: dt.datetime  # the server's clock as the push arrived
    last_server_time: dt.datetime  # the last time the server told the laptop, before the tap
    # Brought in a rescue file from a dying laptop and sent by another (SYNC-12): its time was read from a file.
    carried: bool = False


@dataclass(frozen=True)
class CheckedTime:
    # The answer, copied onto the line (T4): how far its time can be trusted, the time trusted (None when it can't be),
    # and how far off the laptop's clock was as it sent (its clock minus the server's). And the signs found, for the
    # saving code: empty for a time kept or sent at once.
    time_check: TimeCheck
    trusted_time: dt.datetime | None
    clock_error: dt.timedelta
    signs: frozenset[Sign]


def check_time(evidence: Evidence) -> CheckedTime:
    """How far one clock-in's time can be trusted (02 §12): the server's time when it was sent at once; else the
    laptop's, when no sign says its clock moved; else none, for a manager to decide (ATT-6)."""
    # How far off the laptop's clock was as it sent: kept whatever the answer, so a manager can see it. For a carried
    # record, the clock of the laptop that sent it, not the one that made it: what that laptop said of itself.
    clock_error = evidence.sent_at - evidence.received_at
    # Carried in a rescue file: never trusted, whatever the other signs say, and never "sent at once", which compares
    # two laptops' clocks. A file is plain text: a time set to "now" by hand would pass as a tap the server saw, and a
    # late fine would go. A rescue is rare, so a manager confirms the few it brings (Jack, SYNC-12's review; ATT-6).
    if evidence.carried:
        return CheckedTime(TimeCheck.UNVERIFIED, None, clock_error, frozenset({Sign.CARRIED}))
    # How long it waited on the laptop, both ends by the laptop's own clock: a wrong clock is wrong at both ends, so
    # the wait is right. Below zero, the clock went back between the tap and the push, which is not "at once": sign
    # 4 below looks at it.
    waited = evidence.sent_at - evidence.client_time
    if dt.timedelta(0) <= waited <= ONLINE_WITHIN:
        # The server's time of the tap: the push's arrival less the wait, so a worker who taps at 07:35:00 on a line
        # that takes 40 seconds to send stays on time (ATT-1's review). The same as the laptop's time less its clock's
        # error, which is how the book's rule checks it, from what the line keeps.
        return CheckedTime(TimeCheck.SERVER, evidence.received_at - waited, clock_error, frozenset())
    # Each sign compares the gap between two times with the slack, never a time moved by it: a time from year 1, which
    # a laptop's code can send, can't be moved 2 minutes earlier, and the crash would answer retry at every push.
    seen = {
        # 1. Its record before it has a later time: the clock moved between the two, back for this one or forward for
        # that one.
        Sign.RECORD_BEFORE_IS_LATER: (
            evidence.time_before is not None and evidence.time_before - evidence.client_time > CLOCK_SLACK
        ),
        # 2. Its time is before a time the server had already told the laptop.
        Sign.BEFORE_THE_LAST_SERVER_TIME: evidence.last_server_time - evidence.client_time > CLOCK_SLACK,
        # 3. The laptop's clock was off as it sent, slow or fast, so what it wrote that morning can't be believed.
        Sign.CLOCK_OFF_AT_SENDING: abs(clock_error) > CLOCK_SLACK,
        # 4. Its time is after the laptop's own clock as it sent: made "in the future", so the clock was moved forward
        # for the tap and set right again before the push, which no other sign sees (ATT-1's review).
        Sign.AFTER_SENDING: evidence.client_time - evidence.sent_at > CLOCK_SLACK,
    }
    signs = frozenset(sign for sign, found in seen.items() if found)
    if signs:
        return CheckedTime(TimeCheck.UNVERIFIED, None, clock_error, signs)
    return CheckedTime(TimeCheck.DEVICE_OK, evidence.client_time, clock_error, signs)


def shop_minute(moment: dt.datetime, zone: dt.tzinfo) -> dt.time:
    """A tap's time as a minute on the shop's clock, as the counter shows it (ATT-4, 02 §12): 04:35:40 in UTC is 07:35
    in Arusha. Every window of the owner's day is such a minute, so a tap's seconds never count."""
    # A time with no zone would be read on the server's own clock, which runs in UTC: Asha's 07:35 in Arusha would turn
    # into 10:35, and her day into dharura, without a word. So it fails loudly, as closed_days refuses a datetime.
    if moment.utcoffset() is None:
        raise ValueError("shop_minute needs a time with its zone.")
    # Cut, never rounded: 07:35:59 shows 07:35 on the laptop, so it is still on time (ATT-2).
    return moment.astimezone(zone).time().replace(second=0, microsecond=0)


# A day with nothing taken off: on time, a half day for the afternoon, or one a manager decides. Two places, as money
# is kept (rule 3), so it compares equal to a fine a shop typed.
NO_FINE = Decimal("0.00")


@dataclass(frozen=True)
class DayRules:
    # The owner's day, as get_setting answers each rule on one date (02 §12, A1): ATT-10 reads them, the rule never
    # does. Each time a minute on the shop's clock. Their order is the settings' own rule, 07:35 < 08:00 < 08:30 <
    # 12:00 < 13:00 < 13:30 < 18:40 on every day (ATT-2), so each window can start where the one before it ends.
    on_time_until: dt.time  # arriving by it: on time
    second_fine_from: dt.time  # from it, and before review_from: late with the second fine
    review_from: dt.time  # from it, and before afternoon_from: dharura
    afternoon_from: dt.time  # from it to midday: the afternoon's half day
    midday: dt.time  # the morning's half ends and the afternoon's starts
    morning_leave_until: dt.time  # leaving from midday to it: the morning's half day
    closing: dt.time  # leaving from it: the full day
    late_fine: Decimal  # the first fine: arriving after on_time_until, before second_fine_from
    second_fine: Decimal  # the second fine: arriving from second_fine_from, before review_from


@dataclass(frozen=True)
class Tap:
    # One tap of Ingia or Toka, as the rule reads it: its minute on the shop's clock (shop_minute), or None when no
    # time is trusted (`unverified`, ATT-1). A voided tap never comes here: ATT-10 leaves it out (T2).
    kind: ClockKind
    minute: dt.time | None


@dataclass(frozen=True)
class DayResult:
    # The answer, for ATT-10 to keep with the rules it used (T4): what the day was, the fine taken off its pay, and the
    # two taps the answer read, the first clock-in and the first clock-out after it, which ended the day, for a manager
    # to see beside it (ATT-5).
    status: DayStatus
    fine: Decimal
    first_in: dt.time | None
    first_out: dt.time | None


def work_out_day(taps: Sequence[Tap], rules: DayRules) -> DayResult:
    """What one worker's day was, from that day's taps and that day's rules (ATT-4; spec §8.1, 02 §12): on time, late
    with its fine, a half day, absent, or dharura for a manager to decide."""
    # No tap at all: they didn't come, and the day is unpaid. Whether it was office duty, permission or a no-show is a
    # manager's to mark (ATT-6).
    if not taps:
        return DayResult(DayStatus.ABSENT, NO_FINE, None, None)
    # The first clock-in starts the day, in whatever order the taps come: Ingia tapped twice by mistake is one arrival,
    # at the first. Only taps with a time trusted: the others have no minute to compare.
    first_in = min((tap.minute for tap in taps if tap.kind == ClockKind.IN and tap.minute is not None), default=None)
    # And the first Toka after it ends the day: at MPC nobody taps out for lunch, so a tap after that Toka counts for
    # nothing, and a Toka tapped by mistake sends the day to a manager, who mends it with a reason (Jack, ATT-4's
    # review; ATT-6). A Toka before any Ingia ends no day; with no Ingia at all, the first Toka is kept for the manager.
    outs = sorted(tap.minute for tap in taps if tap.kind == ClockKind.OUT and tap.minute is not None)
    first_out = next((minute for minute in outs if first_in is None or minute >= first_in), None)
    dharura = DayResult(DayStatus.NEEDS_REVIEW, NO_FINE, first_in, first_out)
    # A tap whose time can't be trusted (`unverified`, ATT-1): the laptop's clock moved, for that tap or for the one
    # before it, so no window can be read, whatever the other taps say (02 §12). And a Toka with no Ingia: nobody knows
    # when they came, so nobody knows the fine. A manager decides both.
    if first_in is None or any(tap.minute is None for tap in taps):
        return dharura
    # Arriving, window by window in the owner's order. "By" and "from" take their own minute, "before" doesn't:
    # 07:35 is on time, 08:00 takes the second fine.
    if first_in <= rules.on_time_until:
        late, fine = False, NO_FINE
    elif first_in < rules.second_fine_from:
        late, fine = True, rules.late_fine
    elif first_in < rules.review_from:
        late, fine = True, rules.second_fine
    elif rules.afternoon_from <= first_in <= rules.midday:
        # The afternoon's half day, from 12:00 to 13:00, if they stay until closing. No fine: arriving for the
        # afternoon is not arriving late.
        if first_out is not None and first_out >= rules.closing:
            return DayResult(DayStatus.HALF, NO_FINE, first_in, first_out)
        return dharura
    else:
        # From 08:30 and before 12:00, or after 13:00: the owner's dharura.
        return dharura
    # Leaving, after a morning arrival: from closing, the full day, or the late one with its fine. A fine of 0, as a
    # shop starts with (ATT-2), still makes the day late, with nothing taken off.
    if first_out is not None and first_out >= rules.closing:
        return DayResult(DayStatus.LATE if late else DayStatus.ON_TIME, fine, first_in, first_out)
    # The morning's half day: leaving from midday to morning_leave_until, both counted. A late arrival's fine still
    # comes off (the owner, 19 Nov 2026): in at 07:50, out at 13:10, half the day's pay less the first fine.
    if first_out is not None and rules.midday <= first_out <= rules.morning_leave_until:
        return DayResult(DayStatus.HALF, fine, first_in, first_out)
    # Leaving before midday, after 13:30 and before closing, or never clocking out: the owner's dharura, as nobody
    # knows which half was worked, or when they left (02 §20, item 6).
    return dharura
