"""apps/staffpay/services/book.py — the book of days: what each worker's day was, worked out and kept (ATT-10; 02 §12).

    work_out_days(MPC, 16 Nov, 22 Nov)  → each job's day of that week, worked out, kept and answered:
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Juma   Mon 16 Nov  needs_review  0.00    07:20  —          no_out: a manager decides (ATT-6)
    Juma   Tue 17 Nov  needs_review  0.00    07:20  18:45      not_working: suspended on Monday (ATT-11)
    Asha   Sun 22 Nov  off           0.00    —      —          the shop is shut on Sundays and closed days

Each day keeps the worker's share of that date's meal money too (WAGE-7): 8,000 among the 8 who came and share it, 1,000
each, worked out again whenever the day is.

The day's rule (work_out_day, apps/staffpay/calculations.py) says what one day was; the book finds each day's taps and
rules, hands them in, and keeps the answer, one row per job and date (AttendanceDay). Three kinds of day the rule can't
see go to review: a closed day with a tap (ATT-10); and a day with a tap in doubt, or outside a job's days with a tap
(ATT-11). Each day to decide keeps why, the book's reason before the rule's (ReviewReason, ATT-5), for the month page
to show beside it. Nothing here is typed by a person: the days are answers, worked out again each time they are asked
for, as a tap can come late from a laptop that was offline, a manager can void a tap (ATT-13), and a job's first or last
day can be moved (PPL-10). ATT-5 asks for a month to show, WAGE-2 for a month to pay, ATT-7 each night. No line in the
change log: no laptop keeps a copy of the days.

Until a payslip pays a day (WAGE-3): from then on the book answers it as it was kept, whatever came since, and never
writes it (A3), which the table refuses too. Its worker still counts among those who ate that day, so the others' share
of the meals is split as if nothing had been paid, and the paid one's stays as they paid it:

    Juma left on the 14th and was paid, 1,000 of the day's 8,000 taken. Then Asha's day is decided: she came too.
    Juma  14 Nov  on_time  1,000, paid          the others, now 8 beside him:  889 each

It also owns what the other services ask of a day the same way: whether a job ran on it, who shares its meals, where a
tap falls, whether a tap is in doubt, and a month's first and last day.
"""

import calendar
import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from apps.control.models import Flag, FlagKind
from apps.core.acting import acting_as
from apps.core.links import table_of
from apps.core.settings_registry import ATTENDANCE_ON, ROUNDING_STEP
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.shops.selectors import closed_days, shop_settings_between, shop_today
from apps.staffpay.calculations import (
    NO_FINE,
    DayResult,
    MealPart,
    Tap,
    meal_part,
    meal_share,
    shop_minute,
    tap_day,
    work_out_day,
)
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind, DayStatus, PayRate, ReviewReason, TimeCheck
from apps.staffpay.selectors import (
    day_rules_between,
    is_closed,
    meal_money_by_date,
    rates_between,
    rules_as_text,
)

# Sunday, as Python numbers the days of the week (Monday is 0). Always off, and not paid: Sunday work is a deal between
# the owner and the worker, outside the system (01 §8.1), so a shop has no setting for it.
SUNDAY = 6


@dataclass(frozen=True)
class _TheBook:
    # The book as it acts (an Actor, apps/core/tenancy.py): the shop it works for, and no staff member, as the system
    # acts, as a nightly job does.
    shop_id: uuid.UUID
    staff_id: uuid.UUID | None = None


# What the book works out on a day, and so what it writes again when a day comes out otherwise. Not the job, the date
# or the shop, which say which day it is; nor `created_at`, which says when the day was first kept. The reason too
# (ATT-5): a day to decide kept before it had none, and gets its reason the next time it is worked out. And its share of
# the date's meal money (WAGE-7), which money typed later, another worker's day decided, or a pay rate typed, moves.
WORKED_OUT = ["status", "fine", "first_in", "first_out", "rules_used", "review_reason", "meal_share"]

# How many changed days one UPDATE of the book's names (_keep).
MOST_DAYS_A_STATEMENT = 300

# The answer log's link code (apps/core/links.py): the push keeps a line there for each document a laptop sends, and
# flags a suspended or gone worker's tap on that line (X2), not on the tap. The log is a table of `sync`, a layer above
# `staffpay`, so the book names it by its code and asks Django for the table at run time, never importing it
# (ADR-0043). A code that named no table would fail loudly at the first read (UnknownLinkType).
ANSWER_LOG = "pushed_document"


def work_out_days(shop: Shop, first: dt.date, last: dt.date) -> list[AttendanceDay]:
    """Work out and keep each job's day from `first` to `last`, both counted, and answer them, date by date. Only the
    days that count: while attendance is switched on, from each job's first day to its last, and before the shop's
    today; and a day outside a job's days that it tapped on, for a person to decide (ATT-11). A day that comes out as
    it was kept is not written again, and one a payslip paid is answered as it was kept, whatever it would come out as
    (WAGE-3). The shop must be open: the visit's own, or a system job's."""
    # A shop must be open, and be this one, as for get_setting and closed_days: through the guard, another shop's taps
    # would be hidden, and its workers' days kept as absent without a word. So fail closed (ADR-0022).
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("work_out_days was given a shop that is not the one open.")
    # A datetime is a kind of date in Python, but a moment, not the shop's day: in UTC, 22:00 on 15 Nov is already
    # 16 Nov in Arusha. The rules and the closed days take the shop's dates, so the book does too.
    if isinstance(first, dt.datetime) or isinstance(last, dt.datetime):
        raise TypeError("work_out_days needs the shop's business dates, not datetimes.")
    zone = ZoneInfo(shop.timezone)
    # Only days that are over. Today is not kept until it is: at 11:00 Asha, in since 07:20, has no Toka yet, and the
    # rule would send her day to a manager. So a span that reaches today stops at yesterday, and ATT-5 shows today's
    # taps as they come; the night's job keeps today once it is yesterday (ATT-7).
    last = min(last, shop_today(shop) - dt.timedelta(days=1))
    if last < first:
        return []
    # One transaction: the span's days are kept all together, or none of them. It is not one moment of the database:
    # PostgreSQL, as Django runs it (READ COMMITTED), lets each read see what was committed when that read began, so a
    # tap committed between two reads is seen by the second alone. The lock below is what keeps two runs apart.
    with transaction.atomic():
        # Every job, one per row, as a person who left and is hired again the same day has two (PPL-11), each locked
        # until this run commits: one run of the book per shop at a time. Two managers open November at once, or the
        # night's job runs beside them: the second waits here for the first to commit, then reads the taps and the days
        # as the first left them, so it never writes an older answer over a newer one (Asha's Toka came between the
        # two). Locked in the order of their ids, as every run locks them, so two runs never each hold a job the other
        # waits for (a deadlock). FOR NO KEY UPDATE, the light lock (backend rules): a tap pushed meanwhile still saves,
        # as its link to the job takes only a KEY SHARE lock, which this one lets through; a change to a job's own row,
        # a PIN or a fix (PPL-10), waits for the run, a moment.
        jobs = lock_jobs(shop)
        # The attendance switch on each day, with the step a share of the meals is rounded to (WAGE-7): one read for the
        # whole span, never one per day.
        settings_by_day = shop_settings_between([ATTENDANCE_ON, ROUNDING_STEP], shop, first, last)
        answered = answer_days(shop, jobs, first, last, zone, settings_by_day)
        # The days kept before, each with its job read in the same query: the month page (ATT-5) names each day's
        # worker, and a day answered as it was kept would otherwise read its job alone, one query per day, some 600 for
        # a month of 20 workers. A day kept for the first time carries its job already.
        kept = {
            (row.staff_id, row.date): row
            for row in AttendanceDay.objects.filter(shop=shop, date__range=(first, last)).select_related("staff")
        }
        # The days a payslip paid, as they were kept, in place of what their taps and rules would say now (A3).
        answered = _with_paid_days(answered, kept)
        # Who pays for each date's meals, once every job's day of it is worked out (WAGE-7).
        steps = {day: values[ROUNDING_STEP.key] for day, values in settings_by_day.items()}
        _share_meals(shop, first, last, answered, kept, steps)
        # Kept as the book, never as the person whose visit asked for the month. The edit history's trigger names
        # whoever the visit's note says acts (apps/core/acting.py): Meneja opens November (ATT-5), and Asha's Monday,
        # changed by the Toka that came late, would read "Meneja changed it", though nobody did. So the book tells
        # PostgreSQL the system acts, from no device, for its own writes only (ADR-0036: a row the system writes names
        # nobody); the visit's note comes back as the block ends. And the trigger refuses a row of any shop but this
        # one (T1).
        with acting_as(_TheBook(shop.pk), device=None):
            return _keep(answered, kept)


def refuse_if_closed(shop: Shop, day: dt.date, job: uuid.UUID | None = None) -> None:
    """Refuse to change what an approved month's pay was made of (is_closed, WAGE-3, A3): pay.day_approved. A mistake
    found after the approval is an adjustment in a later month (WAGE-9). Called once the lock is held, so an approval
    and the change never both go through."""
    if is_closed(shop, day, job):
        raise ValidationError("The pay of this day is approved.", code="pay.day_approved")


def lock_jobs(shop: Shop) -> list[StaffMember]:
    """Every job of the shop, locked until the transaction ends, in the order of their ids: the book's lock, which
    work_out_days explains. Whatever the pay is made of waits for it, one way or another: a decision and meal money take
    it, as the approval of a month does (approve_month, WAGE-3); a tap, a rate and an advance take their own job's row,
    one of these."""
    return list(StaffMember.objects.filter(shop=shop).order_by("pk").select_for_update(no_key=True))


def answer_days(
    shop: Shop,
    jobs: list[StaffMember],
    first: dt.date,
    last: dt.date,
    zone: ZoneInfo,
    settings_by_day: dict[dt.date, dict[str, Any]],
) -> list[AttendanceDay]:
    # Each job's day from `first` to `last`, both counted, as the book answers it: worked out from its taps and its
    # date's rules, date by date, with no share of the meals yet, and not kept: keeping is the book's, once the days are
    # over (work_out_days). Apart from it, so today, which is still running, can be judged by the same rule and never be
    # kept (WAGE-2).
    taps, in_doubt = _taps(shop, first, last, zone)
    # The days the whole shop is closed (ATT-8): a public holiday, a family funeral. And the day's rules on each day
    # (A1). One read each for the whole span, never one per day.
    closed = closed_days(shop, first, last)
    rules_by_day = day_rules_between(shop, first, last)
    dates = [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]
    answered: list[AttendanceDay] = []
    for day in dates:
        # Attendance counts only from the day the owner switched it on (ADR-0033), a dated rule, so read on each
        # date: before it, nobody clocked in, and every day kept would be an absence that never was. No day at all,
        # not even an off one.
        if not settings_by_day[day][ATTENDANCE_ON.key]:
            continue
        # Sunday is off for every job that ran on it, whatever its taps, in doubt or not: the shop is shut, and
        # Sunday work is paid outside the system (01 §8.1). No rule is read for it. A job outside its days keeps
        # no Sunday at all: off pays nothing, so there is nothing for anyone to decide.
        if day.weekday() == SUNDAY:
            answered.extend(_off(shop, job, day) for job in jobs if ran_on(job, day))
            continue
        # The day's rules, the same for every job (A1).
        rules = rules_by_day[day]
        rules_used = rules_as_text(rules)
        for job in jobs:
            # Only the job's own taps: Asha's on Asha's day, even on a laptop Juma used too. With none, the rule
            # answers absent.
            job_taps = taps.get((job.pk, day), [])
            # Outside the job's days, before its first or after its last (02 §5): a worker added on the 10th has
            # no absent days before it; one who left on Friday has none after. The days as they are now, as PPL-10
            # can move them: a day kept before a first day moved later is no longer answered, and its row stays
            # (rule 7), counted nowhere. Unless the job tapped on it: Neema, added from the 10th, came on the 10th
            # and the 11th, and a manager then moved her first day to the 12th. Her taps say she came, her first
            # day says she didn't, so a person decides (Jack, ATT-11: A), below.
            outside = not ran_on(job, day)
            if outside and not job_taps:
                continue
            if day in closed and not job_taps:
                # A closed day is off, and not paid, like Sunday (ATT-8).
                answered.append(_off(shop, job, day))
                continue
            result = work_out_day(job_taps, rules)
            # Three kinds of day the rule can't see, as each depends on more than the taps' kinds and minutes.
            # Each goes to the owner or a manager (ATT-6), and takes no fine until then. Its taps' minutes stay,
            # which the rule read, to show when the worker came; the rules too, for whoever decides.
            # - A closed day a worker tapped on all the same: the owner closed the shop at 10:00 for a funeral, and
            #   Asha had clocked in at 07:20. Nobody can tell from the taps whether her morning is paid (Jack,
            #   ATT-10).
            # - A day with a tap in doubt (ATT-11): Juma's, made the morning after Baba suspended him, on a laptop
            #   offline that didn't know yet (X2), or the one Asha's later tap disagrees with. His tap is real, but
            #   whether to pay for it is a person's call.
            # - A day outside the job's days that it tapped on, as above (ATT-11).
            # Each says why (ATT-5), the first that holds, in ReviewReason's order: outside the job's days, then a
            # closed day, then a tap in doubt. The book's reason comes before the rule's, as each asks whether the
            # day is paid at all, whatever its times say: Juma suspended, with no Toka, is about the suspension.
            why = (
                ReviewReason.OUTSIDE_JOB
                if outside
                else ReviewReason.CLOSED_DAY
                if day in closed
                else in_doubt.get((job.pk, day))
            )
            if why is not None:
                result = replace(result, status=DayStatus.NEEDS_REVIEW, fine=NO_FINE, reason=why)
            answered.append(_worked_out(shop, job, day, result, rules_used))
    return answered


def ran_on(job: StaffMember, day: dt.date) -> bool:
    # Whether `day` is one of the job's days: from its first day to its last, both counted (02 §5), as they are now.
    return job.started_on <= day and (job.left_on is None or day <= job.left_on)


def _off(shop: Shop, job: StaffMember, day: dt.date) -> AttendanceDay:
    # A day the shop is shut, a Sunday or a closed day: off, nothing taken off, no tap read, and no rule, as none was.
    return AttendanceDay(
        shop=shop,
        staff=job,
        date=day,
        status=DayStatus.OFF,
        fine=NO_FINE,
        first_in=None,
        first_out=None,
        rules_used={},
        review_reason="",
    )


def _worked_out(
    shop: Shop, job: StaffMember, day: dt.date, result: DayResult, rules_used: dict[str, str]
) -> AttendanceDay:
    # A day the rule answered, as the book keeps it: its answer, and the rules it read.
    return AttendanceDay(
        shop=shop,
        staff=job,
        date=day,
        status=result.status,
        fine=result.fine,
        first_in=result.first_in,
        first_out=result.first_out,
        # A copy for each day (T4): one day's rules are never another's object, so nothing done to one could reach
        # the other.
        rules_used=dict(rules_used),
        # Why it needs a decision, on a day that does (ATT-5); empty on any other, as the table keeps "no reason".
        review_reason=result.reason or "",
    )


def _with_paid_days(
    answered: list[AttendanceDay], kept: dict[tuple[uuid.UUID, dt.date], AttendanceDay]
) -> list[AttendanceDay]:
    # The days the book worked out, with each day a payslip paid as it was kept instead (WAGE-3, A3): Juma's 12
    # November, paid as a full day, stays one when a tap of it comes late from an old laptop, or is crossed out. And a
    # paid day the book would no longer answer at all, as his first day was moved later past it since, or he was marked
    # as gone from before it: it was paid, so every page that shows the month shows it, as the payslip does.
    paid = {key: row for key, row in kept.items() if row.payslip_id is not None}
    if not paid:
        # Every month still open, which is nearly every run.
        return answered
    days = [day for day in answered if (day.staff_id, day.date) not in paid]
    # In the order the book answers: date by date, and on each by the job's id, as the jobs were read. Python and
    # PostgreSQL order ids alike, byte by byte.
    return sorted([*days, *paid.values()], key=lambda day: (day.date, day.staff_id))


def _share_meals(
    shop: Shop,
    first: dt.date,
    last: dt.date,
    answered: list[AttendanceDay],
    kept: dict[tuple[uuid.UUID, dt.date], AttendanceDay],
    steps: dict[dt.date, Decimal],
) -> None:
    # Each worked-out day's share of its date's meal money (WAGE-7, 02 §15, 14), written on the days the book is about
    # to keep. Every job's day of a date is here, so the count of those who share it is whole. Read inside the book's
    # lock, as the taps are: the last run to take it reads the newest money, and never keeps an older split over a newer
    # one.
    money = meal_money_by_date(shop, first, last)
    if not money:
        # Nobody typed any in the span, as in every month before WAGE-7: each day's share stays the 0 it is made with.
        return
    # Who shares the meals, on each day: by the rate in force that day (WAGE-1), which names the cook.
    rates = rates_between(shop, first, last)
    by_date: dict[dt.date, list[tuple[AttendanceDay, str]]] = defaultdict(list)
    for day in answered:
        if day.date not in money:
            continue
        # The day as a person decided it, where one did: the decision is on the row kept before, which this run read and
        # whose decision nothing changes meanwhile, as deciding waits for the jobs' lock too (decide_day).
        old = kept.get((day.staff_id, day.date))
        by_date[day.date].append((day, old.decided_status if old is not None else ""))
    for date, days in by_date.items():
        sharing = who_shares(days, rates)
        # The same for everyone who came, a half day too, rounded by the date's own step (A1). One a payslip paid counts
        # among them, as they ate, and keeps the share they paid (WAGE-3): the shop bears the few shillings between.
        share = meal_share(money[date], len(sharing.days), steps[date])
        for day in sharing.days:
            if day.payslip_id is None:
                day.meal_share = share


@dataclass(frozen=True)
class Sharing:
    # Who shares one date's meals (WAGE-7): a day for each person, which carries their share; and how many more people
    # may, once their day is decided.
    days: list[AttendanceDay]
    waiting: int


def who_shares(days: Iterable[tuple[AttendanceDay, str]], rates: dict[tuple[uuid.UUID, dt.date], PayRate]) -> Sharing:
    # Of one date's days, each with its decision ("" for none), those that share its meals. By the person, not the job:
    # a person who left and was hired again the same day has two jobs, so two days (PPL-11), and ate once (Jack: A, 25
    # Nov 2026). Their share is on the job they had first, as ids are made in time's order (UUIDv7); and one who shares
    # already waits for nothing, whatever their other day does. One rule, for the book, which writes the shares, and for
    # the page, which counts who shares and who waits (_meal_day).
    carries: dict[uuid.UUID, AttendanceDay] = {}
    waits: set[uuid.UUID] = set()
    for day, decided in sorted(days, key=lambda pair: pair[0].staff_id):
        rate = rates.get((day.staff_id, day.date))
        part = meal_part(day.status, decided, shares_meals=rate.shares_meals if rate is not None else None)
        # The job comes with each day, in the read that found it, or as the book made it (work_out_days): no query here.
        person = day.staff.user_id
        if part is MealPart.SHARES:
            carries.setdefault(person, day)
        elif part is MealPart.WAITS:
            waits.add(person)
    return Sharing(days=list(carries.values()), waiting=len(waits - carries.keys()))


def _answer_log() -> Any:
    # The answer log's table, asked of Django by its link code. Any, not its model: to know the table's columns, the
    # type checker would have to import `sync`'s model, which the layers forbid (ADR-0043). So its `document_id` is
    # proven by the tests instead: the book's (test_a_suspended_workers_tap_needs_review) and the push's own, which
    # finds a clock-in's line by it (test_suspended_worker_clock_in_flagged, apps/sync/tests/test_clock_in.py).
    return table_of(ANSWER_LOG)


# A day of a job: the job's id and the shop's date.
type _JobDay = tuple[uuid.UUID, dt.date]


def _taps(
    shop: Shop, first: dt.date, last: dt.date, zone: ZoneInfo
) -> tuple[dict[_JobDay, list[Tap]], dict[_JobDay, ReviewReason]]:
    # Each job's taps on each date from `first` to `last`, as the rule reads them, and the days with a tap in doubt,
    # which a person must decide (ATT-11), each with why (ATT-5). One query, whatever the number of taps.
    asks_not_working, asks_disputed = doubt_questions(shop)
    lines = (
        # A voided tap counts for nothing (T2): a clock-in tapped twice by mistake, voided by a manager (ATT-13). Nor
        # does it send its day to review: Juma's flagged tap, once voided, leaves his day absent.
        AttendanceEvent.objects.filter(shop=shop, voided_at__isnull=True)
        .filter(falls_between(first, last, zone))
        .annotate(maker_not_working=asks_not_working, disagreed_with=asks_disputed)
        .values_list(
            "staff_id", "kind", "trusted_time", "client_time", "time_check", "maker_not_working", "disagreed_with"
        )
    )
    taps: dict[_JobDay, list[Tap]] = defaultdict(list)
    in_doubt: dict[_JobDay, ReviewReason] = {}
    for staff_id, kind, trusted_time, client_time, time_check, not_working, disputed in lines:
        day, minute = where_it_falls(trusted_time, client_time, zone)
        taps[(staff_id, day)].append(Tap(ClockKind(kind), minute))
        # A day with both doubts says the first, in ReviewReason's order (ATT-5): whether a suspended worker is paid at
        # all comes before his time. So a suspension writes over a disagreement, and a disagreement never over one.
        doubt = doubt_of(not_working, disputed, time_check)
        if doubt == ReviewReason.NOT_WORKING:
            in_doubt[(staff_id, day)] = doubt
        elif doubt is not None:
            in_doubt.setdefault((staff_id, day), doubt)
    return taps, in_doubt


def falls_between(first: dt.date, last: dt.date, zone: ZoneInfo) -> Q:
    # The taps that fall from `first` to `last`, both counted, on the shop's calendar. A day's edges are the shop's own
    # midnights, not UTC's: Asha's tap at 21:30 UTC on Monday is Tuesday's, at 00:30 in Arusha. So the span is read
    # from the midnight starting its first day to the one ending its last, each a moment with its zone.
    start = dt.datetime.combine(first, dt.time.min, tzinfo=zone)
    end = dt.datetime.combine(last + dt.timedelta(days=1), dt.time.min, tzinfo=zone)
    # By the time the server trusts, never the laptop's, whose clock anyone can move (ATT-1): through the index on
    # (shop, trusted_time). One with no trusted time (`unverified`) by the laptop's time instead, the only one it has:
    # its day needs review anyway, but it must land on a day for a manager to see it.
    return Q(trusted_time__gte=start, trusted_time__lt=end) | Q(
        trusted_time__isnull=True, client_time__gte=start, client_time__lt=end
    )


def where_it_falls(
    trusted_time: dt.datetime | None, client_time: dt.datetime | None, zone: ZoneInfo
) -> tuple[dt.date, dt.time | None]:
    # A tap's date on the shop's calendar (tap_day); and its minute on the shop's clock, its seconds dropped, as the
    # counter showed it (shop_minute): 07:35:40 is 07:35, on time. No minute for a tap with no trusted time, which sends
    # its day to review (ATT-4).
    minute = shop_minute(trusted_time, zone) if trusted_time is not None else None
    return tap_day(trusted_time, client_time, zone), minute


def doubt_questions(shop: Shop) -> tuple[Exists, Exists]:
    # The two questions that put a tap in doubt (ATT-11), asked inside the taps' own read, as annotations: the book's
    # (_taps) and a worker's month's (worker_attendance) ask them alike, so the calendar's ! and the tap's own line,
    # "alikuwa amesimamishwa", never disagree (ATT-12). Each answer is turned into a reason by doubt_of. Two, in this
    # order: whether the maker wasn't working, and whether a later tap disagrees; named by each read as it annotates
    # them, as the type checker reads an annotation's name only where it is written.
    #
    # A tap whose maker wasn't working when they made it: Baba suspended Juma at 11:00, and the laptop, offline, let his
    # Ingia through the next morning. The push flags it on the tap's line in the answer log (suspended_staff_activity,
    # X2), not on the tap, whose own time check can be `server` or `device_ok`, so the tap alone looks like any other.
    # Its line is the one whose document_id is the tap's own id. Whatever the flag's status: a manager who closes it has
    # looked at the tap, not decided the day, which is ATT-6's override. Only that kind: a device_gap flag on the same
    # line, a record still missing, says nothing of whether the worker came. Asked inside the taps' own read (EXISTS),
    # so a month still takes one query for its taps, whatever their number; through the guard, as every read is
    # (ADR-0022), and through the log's one-line-per-document rule, which leads with `shop`, so each tap's line is one
    # lookup. The flags are read once per run, not once per tap: every flag of the shop, kept or not by its kind, as no
    # index has the kind. A shop raises a few a day, so a month's run reads some hundreds, which is cheap; an index on
    # the kind can come should a shop raise many more (03 §6.6).
    suspension_flags = Flag.objects.filter(
        shop=shop, kind=FlagKind.SUSPENDED_STAFF_ACTIVITY, subject_type=ANSWER_LOG
    ).values("subject_id")
    maker_not_working = Exists(
        _answer_log()._default_manager.filter(shop=shop, document_id=OuterRef("pk")).filter(pk__in=suspension_flags)
    )
    # A tap a later one's time disagrees with: Juma's Toka says 18:45, then Asha's, the laptop's next record, says
    # 18:30. A clock moved between the two, and nobody knows whose, so hers has no trusted time, and keeps his id
    # (`disagrees_with`, ATT-11): his time can be the wrong one too (Jack: A). Any tap of the shop that keeps his id,
    # wherever it fell: hers can fall on another day, or another month, by the laptop's clock, the only time it has.
    # Voided or not: a void says a tap counts for nothing, not that the laptop's clock was right. Through the small
    # index of the taps that keep a record (staffpay_event_by_disagreement), each tap's question one lookup.
    disagreed_with = Exists(AttendanceEvent.objects.filter(shop=shop, disagrees_with=OuterRef("pk")))
    return maker_not_working, disagreed_with


def doubt_of(not_working: bool, disputed: bool, time_check: str) -> ReviewReason | None:
    # Why a tap is in doubt, from the two questions' answers (doubt_questions), or None. Made while its worker wasn't
    # working, first; or timed by a laptop clock a later tap disagrees with, only by the laptop's clock (`device_ok`): a
    # tap sent at once has the server's time, which no laptop's clock can make wrong, and one with no trusted time sends
    # its day to review already (ATT-4).
    if not_working:
        return ReviewReason.NOT_WORKING
    if disputed and time_check == TimeCheck.DEVICE_OK:
        return ReviewReason.CLOCK_DISAGREES
    return None


def _keep(answered: list[AttendanceDay], kept: dict[tuple[uuid.UUID, dt.date], AttendanceDay]) -> list[AttendanceDay]:
    # Keep each day the book worked out, and answer the rows as kept. A day that came out as it was kept is answered as
    # it was, and not written again: the edit history keeps only real changes (a tap that came late, a tap voided), and
    # a month asked for twice writes nothing the second time.
    rows: list[AttendanceDay] = []
    changed: list[AttendanceDay] = []
    # The days on which the share of the meals alone moved, by the share they now have.
    moved: dict[Decimal, list[uuid.UUID]] = defaultdict(list)
    new: list[AttendanceDay] = []
    for day in answered:
        old = kept.get((day.staff_id, day.date))
        if old is None:
            new.append(day)
            rows.append(day)
            continue
        differs = [part for part in WORKED_OUT if getattr(old, part) != getattr(day, part)]
        # Changed: the kept row takes the new answer, so it keeps its id and the day it was first kept.
        for part in differs:
            setattr(old, part, getattr(day, part))
        if differs == ["meal_share"]:
            moved[old.meal_share].append(old.pk)
        elif differs:
            changed.append(old)
        rows.append(old)
    # A day kept before: an UPDATE by its id, which the edit history's trigger writes down (ADR-0036), Asha's Monday
    # from needs review to on time. A few hundred days a statement: each names every part of every row, so one
    # statement for a whole year of them grows too long to be quick, with the jobs locked meanwhile.
    if changed:
        AttendanceDay.objects.bulk_update(changed, WORKED_OUT, batch_size=MOST_DAYS_A_STATEMENT)
    # A share moved alone, the same on every day that now has it: one UPDATE a share. Every worker's share of a date
    # moves at once, and a rate mended from January moves a year of them (WAGE-7's review).
    for share, days in moved.items():
        AttendanceDay.objects.filter(pk__in=days).update(meal_share=share)
    # A day kept for the first time: an INSERT. No other run of the book can keep the same day meanwhile, as the jobs'
    # lock lets one run per shop at a time (work_out_days). Should a bug write a day twice all the same, the rule of
    # one day per job and date refuses the second, loudly, a server error, never a second row.
    if new:
        AttendanceDay.objects.bulk_create(new)
    return rows


def month_span(month: dt.date) -> tuple[dt.date, dt.date]:
    # The first and the last day of the month of `month`, any day of it. The last as the calendar counts the month's
    # days (30, 31, 28 or 29). Not "the 1st of the month after, less a day": in the calendar's last month, December
    # 9999, that sum runs past the last day Python knows, and a month typed into the address became a server error
    # (ATT-5's review).
    first = month.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])
