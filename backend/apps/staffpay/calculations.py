"""apps/staffpay/calculations.py — pure sums for attendance and pay: no database, no clock of their own (03 §5.2).

The time check (ATT-1, 02 §12): how far a clock-in's time can be trusted, from the evidence about the laptop's clock.
A laptop's clock can be moved by anyone, and an offline clock-in carries only its time, so the server keeps that time
only when no sign says the clock moved. Server only: the laptop never judges its own clock, so this one has no
TypeScript twin and no shared test vectors (03 §8).

The day's rule (ATT-4, spec §8.1): what one worker's day was, from that day's taps and that day's rules.

    in 07:20, out 18:40   → on time            in 08:10, out 18:40   → late, the second fine
    in 07:50, out 18:40   → late, first fine    in 12:30, out 18:40   → the afternoon's half day
    in 07:20, out 13:10   → the morning's half  in 07:50, out 13:10   → the morning's half, less the first fine
    in 09:00, or no out   → dharura, a manager or the owner decides it, told why: came late, or no Toka (ATT-5)

Every window of the owner's day is a minute on the shop's clock, which shop_minute reads from a tap's time. The rule
only answers: ATT-10 finds the taps and the rules in force that day, hands them in, and keeps the answer. Server only
too, as the day is worked out on the server (03 §5.8).

A decided day's fine (ATT-6): a manager or the owner decides a day, and a day decided late or half takes the fine its
first Ingia gives, by the rules that day used (T4):

    in 07:50  → Amechelewa: the first fine     Nusu siku: the first fine
    in 08:10  → Amechelewa: the second fine    Nusu siku: the second fine
    in 07:20  → Amechelewa: not offered        Nusu siku: no fine
    in 12:20  → Amechelewa: the second fine    Nusu siku: no fine, the afternoon's half
    a time in doubt → Amechelewa: not offered  Nusu siku: no fine (Jack, ATT-6's review)

A day's meal money (WAGE-7, 02 §15, 14): who shares it, and how much each pays:

    8,000 and 8 who came → 1,000 each     8,000 and 7 → 1,143 each     8,000 and nobody → 0.00, the shop bears it

What a day pays (WAGE-2, 02 §15, 8), each day alone, with its own rate, fine and decision, at 10,000 a day:

    on time → 10,000          half a day → 5,000                  waits for a decision → nothing yet
    late    → 10,000 less 500 half, fine 6,000 → 5,000 less 5,000  office duty → 10,000, absent → nothing

A worker's pay (WAGE-2, spec §8.1): the days added up, grouped by what they pay, so a raise makes two lines:

    14 full × 10,000   6 full × 12,000   2 half × 5,000   less the fines, the meals, the advances

What a pay hands over (WAGE-3, Jack: A): never less than nothing. What is below 0 is owed, and comes off the next pay:

    November  10,000 earned, 28,000 given early   → −18,000: 0 to hand over, a debt of 18,000
    December  152,000 earned, less that debt      → 134,000 to hand over, no debt
"""

import datetime as dt
import enum
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

from apps.core.numbers import round_money
from apps.staffpay.models import AbsenceType, ClockKind, DayChoice, DayStatus, ReviewReason, TimeCheck

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


def tap_day(trusted_time: dt.datetime | None, client_time: dt.datetime | None, zone: dt.tzinfo) -> dt.date:
    """A tap's date on the shop's calendar: by its trusted time, or by the laptop's for one with none. The one rule the
    book of days puts a tap on a day by (ATT-10), and a flag about the tap opens a day by (CTRL-4): written twice, the
    two could differ, and the flag would open a day the tap isn't on."""
    # A tap entered in the office has no laptop time, but always its trusted one (ATT-13); a laptop's always has its
    # own: the table's rule (from_a_laptop_or_the_office) holds one of the two there, so a tap with neither is a bug,
    # and fails loudly.
    moment = trusted_time if trusted_time is not None else client_time
    if moment is None:
        raise ValueError("A tap with neither a trusted time nor a laptop's: the table's rules forbid it.")
    return moment.astimezone(zone).date()


def shop_minute(moment: dt.datetime, zone: dt.tzinfo) -> dt.time:
    """A tap's time as a minute on the shop's clock, as the counter shows it (ATT-4, 02 §12): 04:35:40 in UTC is 07:35
    in Arusha. Every window of the owner's day is such a minute, so a tap's seconds never count."""
    # A time with no zone would be read on the server's own clock, which runs in UTC: Asha's 07:35 in Arusha would turn
    # into 10:35, and her day into dharura, without a word. So it fails loudly, as closed_days refuses a datetime.
    if moment.utcoffset() is None:
        raise ValueError("shop_minute needs a time with its zone.")
    # Cut, never rounded: 07:35:59 shows 07:35 on the laptop, so it is still on time (ATT-2).
    return moment.astimezone(zone).time().replace(second=0, microsecond=0)


# A day with nothing taken off: on time, a half day with no late arrival, absent, or one a manager decides. Written
# with two places, as every amount is stored (numeric(14,2), 03 §9) and as the fines' own default is (LATE_FINE,
# apps/core/settings_registry.py), so it reads 0.00 wherever ATT-10 keeps it. Its value would compare equal without
# them: Decimal("0") == Decimal("0.00").
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

    def __post_init__(self) -> None:
        # A minute with seconds is later than its minute: 07:35:40 is after 07:35, so Asha would lose the first fine
        # though the counter showed 07:35. shop_minute drops them; a tap built without it is a bug in our code, so it
        # fails loudly here, as shop_minute does for a time with no zone, before any fine is worked out.
        if self.minute is not None and (self.minute.second or self.minute.microsecond):
            raise ValueError("A tap's minute has no seconds: read it with shop_minute.")


@dataclass(frozen=True)
class DayResult:
    # The answer, for ATT-10 to keep with the rules it used (T4): what the day was, the fine taken off its pay, and the
    # two taps the answer read, the first clock-in and the first clock-out after it, which ended the day, for a manager
    # to see beside it (ATT-5). Both are taps with a time trusted: on a day sent to a manager for a tap whose time
    # can't be trusted, they may not be the day's real first Ingia or Toka, so a screen shows them as taps, not facts.
    # And why a day needs a manager (ATT-5): a reason on a day to decide, and only there.
    status: DayStatus
    fine: Decimal
    first_in: dt.time | None
    first_out: dt.time | None
    reason: ReviewReason | None = None

    def __post_init__(self) -> None:
        # A day sent to a manager with no reason would leave them guessing, and a reason on any other day would put it
        # on the month page's list for nothing: either is a bug in our code, so it fails here, before the book keeps
        # it, as the table's own rule would refuse the second (staffpay_attendanceday_reason_only_to_decide).
        if (self.status == DayStatus.NEEDS_REVIEW) != (self.reason is not None):
            raise ValueError("A day says why exactly when it needs review.")


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

    def dharura(why: ReviewReason) -> DayResult:
        # The owner's dharura, with why, for whoever decides it (ATT-5): its taps kept beside it, and no fine yet.
        return DayResult(DayStatus.NEEDS_REVIEW, NO_FINE, first_in, first_out, why)

    # A tap whose time can't be trusted (`unverified`, ATT-1): the laptop's clock moved, for that tap or for the one
    # before it, so no window can be read, whatever the other taps say (02 §12). First, as the manager should look at
    # the laptop's clock, not ask whether they came: an Ingia whose time is lost still says they did.
    if any(tap.minute is None for tap in taps):
        return dharura(ReviewReason.TIME_UNKNOWN)
    # A Toka with no Ingia: nobody knows when they came, so nobody knows the fine.
    if first_in is None:
        return dharura(ReviewReason.NO_IN)
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
        return dharura(ReviewReason.NO_OUT if first_out is None else ReviewReason.LEFT_EARLY)
    else:
        # From 08:30 and before 12:00, or after 13:00: the owner's dharura. Their arrival is why, read before their
        # leaving, whether they tapped Toka or not: "alifika saa 09:00" says more than "hakuna Toka".
        return dharura(ReviewReason.CAME_LATE)
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
    return dharura(ReviewReason.NO_OUT if first_out is None else ReviewReason.LEFT_EARLY)


# The reasons a day waits for that put its time itself in doubt (ATT-5): a tap whose time the server can't trust, and a
# tap a later one's time disagrees with, as a laptop's clock moved. On such a day the first Ingia the book read may not
# be when the worker came: a trusted Ingia at 09:00 after an untrusted one at 07:20, or a 07:50 by a clock that moved.
TIME_IN_DOUBT = (ReviewReason.TIME_UNKNOWN, ReviewReason.CLOCK_DISAGREES)


def day_choices(first_in: dt.time | None, rules: DayRules, *, time_in_doubt: bool = False) -> dict[DayChoice, Decimal]:
    """The choices a manager may decide a day as (ATT-6), each with the fine it takes, in the sheet's order: from the
    day's first Ingia with a trusted time (`first_in`, ATT-4) and the rules the day used (`rules_used`, T4), never
    today's. A choice the day can't take is left out: *Amechelewa* with no Ingia known, or an Ingia on time.
    `time_in_doubt`: the day waits for one of TIME_IN_DOUBT's reasons, so its Ingia counts as none known."""
    # A time in doubt fines nobody (Jack: A, ATT-6's review): a worker is never fined by a clock the system itself
    # doesn't trust. So the day is decided as one with no Ingia known: no Amechelewa, and a half day with no fine. Rare,
    # as a laptop's clock seldom moves, and the manager still sees the taps and their doubt beside the day.
    if time_in_doubt:
        first_in = None
    # A day sent to review carries no fine (NO_FINE, ATT-4), so deciding it late reads the fine again, as the rule
    # would have: by on_time_until no fine; after it and before second_fine_from the first; from second_fine_from on
    # the second. Past the rule's own windows (from review_from, 08:30, the owner's dharura) a late arrival is later
    # still, so it takes the second fine too, the larger: 09:10 is never cheaper than 08:10 (a default, in the plan
    # Jack approved).
    arrival_fine: Decimal | None
    if first_in is None or first_in <= rules.on_time_until:
        arrival_fine = None
    elif first_in < rules.second_fine_from:
        arrival_fine = rules.late_fine
    else:
        arrival_fine = rules.second_fine
    # A half day keeps a late morning arrival's fine, as the rule's morning half does (the owner, 19 Nov 2026); an
    # afternoon arrival, from afternoon_from on, is no late one (ATT-4), and an Ingia not known can't be fined.
    morning = first_in is not None and first_in < rules.afternoon_from
    half_fine = arrival_fine if morning and arrival_fine is not None else NO_FINE
    choices = {DayChoice.ON_TIME: NO_FINE}
    if arrival_fine is not None:
        choices[DayChoice.LATE] = arrival_fine
    choices[DayChoice.HALF] = half_fine
    # The three absences take no fine: nobody arrived late who never arrived.
    choices |= {DayChoice.OFFICE_DUTY: NO_FINE, DayChoice.PERMISSION: NO_FINE, DayChoice.NO_SHOW: NO_FINE}
    return choices


class MealPart(enum.Enum):
    # What one worker's day is to its date's meal money (WAGE-7, 02 §15, 14): they share it; nobody knows yet, as their
    # day waits for a decision; or it is no business of theirs.
    SHARES = "shares"
    WAITS = "waits"
    NONE = "none"


# The days a worker came, whichever way they came: a half day pays a whole share, as they ate (spec §8.1).
CAME = (DayStatus.ON_TIME, DayStatus.LATE, DayStatus.HALF)


def meal_part(status: str, decided_status: str, *, shares_meals: bool | None) -> MealPart:
    """What one worker's day is to its date's meal money: by the decision where there is one, else by the book (A2); an
    off day is nobody's, decided or not.
    `status`: what the book worked out. `decided_status`: what a person decided, "" for none (ATT-6). `shares_meals`: as
    the pay rate in force that day says it, or None with no rate that day."""
    # The cook, whose rate says they share no meals (WAGE-1), and whoever has no rate that day: the owner, who is never
    # paid by the day, or a worker whose rate was typed from a later one. First, so neither ever waits: deciding their
    # day would move nobody's share.
    if not shares_meals:
        return MealPart.NONE
    # A day the shop was shut, a Sunday or a closed day nobody tapped on, is nobody's, whatever was decided on it: a tap
    # on a closed day sent it to a person (ATT-10), who decided it, and the tap was then crossed out, so the day is off
    # again with its decision kept beside it (A2). Before the decision, as the month's line counts no off day either
    # (attendance_month); and the table refuses an off day a share, which would stop every page of the month from
    # opening (WAGE-7's review).
    if status == DayStatus.OFF:
        return MealPart.NONE
    # Office duty is kept as an absence with its kind (DECISION_OF, ATT-6), so it shares nothing here by itself: paid as
    # a full day, but they ate away (Jack: A, 24 Nov 2026). Permission and a no-show the same.
    counted = decided_status or status
    if counted in CAME:
        return MealPart.SHARES
    # A day still to decide has no share until a person says whether they came (02 §12): split without them now, and
    # among one more if they did.
    return MealPart.WAITS if counted == DayStatus.NEEDS_REVIEW else MealPart.NONE


# A day with no share of the meals: absent, waiting, the cook, or a day with no money typed. Two places, as NO_FINE.
NO_MEAL_SHARE = Decimal("0.00")


def meal_share(money: Decimal, sharers: int, step: Decimal) -> Decimal:
    """What each of `sharers` workers pays of a date's meal money (02 §15, 14): the same for all, rounded half-up to a
    multiple of `step`, the shop's rounding step that date. Nobody to share: nobody pays, and the shop bears it. The
    rounded shares may add up to a few shillings off the money."""
    if sharers < 0:
        # A count of heads from the book: below 0 is a bug in our code, and would pay workers for eating.
        raise ValueError(f"{sharers} workers can't share meal money: a count below 0.")
    if sharers == 0:
        return NO_MEAL_SHARE
    # Divided with more digits than any column holds, whatever other code set for this thread, as the shared numbers do
    # (apps/core/numbers.py): 8,000 ÷ 7 keeps every digit the half-up rounding looks at. Rounded by the one shared
    # function, once (ADR-0024).
    with localcontext(prec=40):
        each = money / sharers
    return round_money(each, step)


class PaidAs(enum.Enum):
    # What one worker's day is paid as (WAGE-2, 02 §15, 8): the whole of the day's rate, half of it, nothing, or nobody
    # knows yet, as the day waits for a decision.
    FULL = "full"
    HALF = "half"
    NOTHING = "nothing"
    WAITS = "waits"


# What a day counts as, and so what it is paid as. An off day and office duty aren't here: _paid_as asks for them first.
# A status missing from this list fails loudly (KeyError), where an "else, nothing" would leave a worker unpaid without
# a word should a status be added.
PAID_AS = {
    DayStatus.ON_TIME: PaidAs.FULL,
    # The whole rate too: what a late arrival costs is its fine, a line of its own.
    DayStatus.LATE: PaidAs.FULL,
    DayStatus.HALF: PaidAs.HALF,
    DayStatus.ABSENT: PaidAs.NOTHING,
    DayStatus.NEEDS_REVIEW: PaidAs.WAITS,
}


@dataclass(frozen=True)
class DayToPay:
    # One worker's day as the pay reads it: what the book worked out and its fine; the decision beside it, empty where
    # there is none (ATT-6); the share of the meals the book kept; and, as they were on that date (A1), the worker's
    # daily rate, None for no rate, and the shop's rounding step. Values, never the table's row: the sum reads no
    # database, and today's day, which is never kept, is paid by the same rule.
    status: str
    fine: Decimal
    decided_status: str
    absence_type: str
    decided_fine: Decimal | None
    meal_share: Decimal
    rate: Decimal | None
    step: Decimal


@dataclass(frozen=True)
class PaidDay:
    # What one day pays: what it is paid as, how much, the fine taken off it, and whether it should be paid but has no
    # rate. The fine is apart, as the pay shows it on a line of its own (spec §8.1).
    paid_as: PaidAs
    amount: Decimal
    fine: Decimal
    no_rate: bool = False


# A day that pays nothing. Two places, as NO_FINE.
NO_PAY = Decimal("0.00")


def add_up(amounts: Iterable[Decimal]) -> Decimal:
    """The sum of some amounts of money, 0.00 for none (WAGE-2): the one way the pay adds, its lines, a worker's total
    and everyone's. Exact, with more digits than any column holds, whatever other code set for this thread, as the
    shared numbers are (apps/core/numbers.py)."""
    with localcontext(prec=40):
        return sum(amounts, NO_PAY)


def _paid_as(day: DayToPay) -> PaidAs:
    # The shop was shut: the day is nobody's, whatever was decided on it. A tap on a closed day sent it to a person
    # (ATT-10), who decided it, and the tap was then crossed out, so the day is off again with its decision kept (A2).
    # As the meals and the month's counts read it (meal_part, attendance_month).
    if day.status == DayStatus.OFF:
        return PaidAs.NOTHING
    # Office duty is kept as an absence with its kind (DECISION_OF, ATT-6), and paid as a full day: they worked for the
    # shop elsewhere. Asked before the list, which pays an absence nothing.
    if day.absence_type == AbsenceType.OFFICE_DUTY:
        return PaidAs.FULL
    # The decision where there is one, else the book's answer (A2).
    return PAID_AS[DayStatus(day.decided_status or day.status)]


def pay_day(day: DayToPay) -> PaidDay:
    """What one worker's day pays (WAGE-2; spec §8.1, 02 §15, 8): the day's own rate, or half of it rounded once to the
    shop's step that day, or nothing; and the fine taken off it, never more than it pays (Jack: A)."""
    paid_as = _paid_as(day)
    if paid_as not in (PaidAs.FULL, PaidAs.HALF):
        return PaidDay(paid_as, NO_PAY, NO_FINE)
    # A day to pay with no rate in force: the worker's first day was moved earlier (PPL-10), and no rate typed from it.
    # Nobody knows what it pays, so nothing, and the page says how many such days there are, for the owner to type one.
    if day.rate is None:
        return PaidDay(paid_as, NO_PAY, NO_FINE, no_rate=True)
    # A whole day pays the rate as the owner typed it, whole shillings, never rounded.
    amount = day.rate
    if paid_as is PaidAs.HALF:
        # Half a day is rounded here, once, by the one shared function (ADR-0024), never the month's total: two half
        # days of 9,001 are 2 × 4,501 on the page, and the line is 9,002, so whoever reads it can check it. Divided
        # with more digits than any column holds, whatever other code set for this thread, as meal_share is.
        with localcontext(prec=40):
            half = day.rate / 2
        amount = round_money(half, day.step)
    # The decision's fine where there is a decision, which has one always (the table's rule), else the book's. Never
    # more than the day pays: half a day of 5,000 with a fine of 6,000 pays nothing, and takes nothing of the worker's
    # other days (Jack: A).
    fine = day.fine if day.decided_fine is None else day.decided_fine
    return PaidDay(paid_as, amount, min(fine, amount))


@dataclass(frozen=True)
class PayLine:
    # One line of a worker's pay: so many days, full or half, at so much each. "Siku kamili  23 × 9,000   207,000".
    paid_as: PaidAs
    days: int
    each: Decimal
    amount: Decimal


@dataclass(frozen=True)
class Pay:
    # A worker's pay over some days (02 §15, 8): the lines, the full days first, then the half ones, each in the days'
    # order; the fines taken, and on how many days; the meals, and how many days ate; the advances; a debt carried from
    # an earlier month (WAGE-3); the corrections of mistakes found after an earlier month's approval, their sum, plus or
    # minus (WAGE-10); how many days wait for a decision, and how many paid days have no rate, neither of them paid; and
    # what is left to pay, which may be below 0, as the meals, the advances, a debt and a correction can be more than
    # the days: cash_to_pay says what is handed over, and debt_left what the next month takes.
    lines: tuple[PayLine, ...]
    fined_days: int
    fines: Decimal
    meal_days: int
    meals: Decimal
    advances: Decimal
    carried: Decimal
    corrections: Decimal
    waiting: int
    no_rate: int
    total: Decimal


def cash_to_pay(total: Decimal) -> Decimal:
    """What is handed over for a pay that came to `total` (WAGE-3, Jack: A): all of it, or nothing when it is below 0,
    as nobody pays to have worked."""
    return total if total > 0 else NO_PAY


def debt_left(total: Decimal) -> Decimal:
    """What a worker still owes after a pay that came to `total` (WAGE-3, Jack: A): nothing, or what it is below 0,
    which their next pay takes off (`carried`)."""
    # copy_negate, never a minus: a minus rounds to the digits the thread keeps, which other code may have lowered.
    return total.copy_negate() if total < 0 else NO_PAY


def work_out_pay(
    days: Iterable[DayToPay], *, advances: Decimal = NO_PAY, carried: Decimal = NO_PAY, corrections: Decimal = NO_PAY
) -> Pay:
    """A worker's pay over `days`, in their order (WAGE-2; spec §8.1, 02 §15, 8): each paid alone (pay_day), then added
    up and grouped by what they pay. `advances`: money given before payday (WAGE-8), which comes off it. `carried`: what
    an earlier month's pay left owed (debt_left, WAGE-3), which comes off it too. `corrections`: what the mistakes found
    after an earlier month's approval add, or take off, below 0 (WAGE-10): Juma's + 9,000 of a November day left out.
    The sum reads nothing itself, so any days are paid by it: a month's, a leaver's, or today alone."""
    if advances < 0 or carried < 0:
        # Money the worker already took: below 0 it would pay them a second time, so a bug in our code. A correction
        # may be either way, as it says itself.
        raise ValueError(f"Advances of {advances}, a debt of {carried}: neither is ever below 0.")
    # How many days pay each amount, full days and half ones apart: half of 20,000 is as much as a full day at 10,000,
    # and the page says which is which. In the order each first comes, so the rate before a raise stays above the one
    # after it. A day that pays nothing is counted too, and no line below reads it.
    counts: Counter[tuple[PaidAs, Decimal]] = Counter()
    fines: list[Decimal] = []
    meals: list[Decimal] = []
    waiting = no_rate = 0
    for day in days:
        paid = pay_day(day)
        if paid.paid_as is PaidAs.WAITS:
            waiting += 1
        elif paid.no_rate:
            no_rate += 1
        else:
            counts[(paid.paid_as, paid.amount)] += 1
        # Only a fine that took something: a late day whose fine is 0, as every shop starts with (ATT-2), was late, and
        # costs nothing, so it is no day on the fines' line.
        if paid.fine:
            fines.append(paid.fine)
        # The share as the book kept it (WAGE-7), never split again here: Hela ya chakula and the pay say the same.
        if day.meal_share:
            meals.append(day.meal_share)
    # Only adding and whole multiples from here: every amount is whole cents already, so nothing is rounded again
    # (add_up says with how many digits).
    with localcontext(prec=40):
        lines = tuple(
            PayLine(kind, number, each, number * each)
            for kind in (PaidAs.FULL, PaidAs.HALF)
            for (paid_as, each), number in counts.items()
            if paid_as is kind
        )
        fined, eaten = add_up(fines), add_up(meals)
        total = add_up(line.amount for line in lines) - fined - eaten - advances - carried + corrections
    return Pay(
        lines=lines,
        fined_days=len(fines),
        fines=fined,
        meal_days=len(meals),
        meals=eaten,
        advances=advances,
        carried=carried,
        corrections=corrections,
        waiting=waiting,
        no_rate=no_rate,
        total=total,
    )
