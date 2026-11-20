"""apps/staffpay/services.py — the writes of attendance and pay: the book of days (ATT-10; 02 §12), the month the month
page shows, worked out through it (ATT-5), and a worker's own month (ATT-12), and each worker's daily pay rate (WAGE-1).

    work_out_days(MPC, 16 Nov, 22 Nov)  → each job's day of that week, worked out, kept and answered:
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Juma   Mon 16 Nov  needs_review  0.00    07:20  —          no_out: a manager decides (ATT-6)
    Juma   Tue 17 Nov  needs_review  0.00    07:20  18:45      not_working: suspended on Monday (ATT-11)
    Asha   Sun 22 Nov  off           0.00    —      —          the shop is shut on Sundays and closed days

The day's rule (work_out_day, apps/staffpay/calculations.py) says what one day was; the book finds each day's taps and
rules, hands them in, and keeps the answer, one row per job and date (AttendanceDay). Three kinds of day the rule can't
see go to review: a closed day with a tap (ATT-10); and a day with a tap in doubt, or outside a job's days with a tap
(ATT-11). Each day to decide keeps why, the book's reason before the rule's (ReviewReason, ATT-5), for the month page
to show beside it. Nothing here is typed by a person: the days are answers, worked out again each time they are asked
for, as a tap can come late from a laptop that was offline, a manager can void a tap (ATT-6), and a job's first or last
day can be moved (PPL-10). ATT-5 asks for a month to show, WAGE-2 for a month to pay, ATT-7 each night. No line in the
change log: no laptop keeps a copy of the days.

The month page (ATT-5) asks for a month through attendance_month, which its route calls (GET attendance-month/): the
book's days, a line per worker the shop pays by the day with how many days were each kind, and the days a person must
decide, each with why. So that GET writes, as the book keeps the days it works out; asked twice, the month writes
nothing the second time.

A worker's name on that page opens their own month (ATT-12), through worker_attendance, which its route calls (GET
attendance-worker/{id}/): the book's days of that job, worked out the same way, and every tap of the month, today's too,
with its laptop, its photo or why none, and whether it is in doubt, the question the book asks too (_doubt_questions),
so the calendar's ! and the tap's own line never disagree.

A pay rate is typed by a person, the owner (set_pay_rate): from 10 Nov, Juma earns 10,000 a day. Whoever sets it sets a
worker's pay, so who may is the PIN's rule, asked by the people app (02 §5). No line in the change log either: a
worker's pay never sits on a shared device (03 §6.1).
"""

import calendar
import datetime as dt
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Coalesce

from apps.control.models import ATTACHMENT_KINDS, Attachment, AttachmentKind, Flag, FlagKind
from apps.core.acting import acting_as
from apps.core.links import table_of
from apps.core.permissions import Permission
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import StaffMember, StaffStatus
from apps.people.permissions import require
from apps.people.services import lock_worker_for_a_change
from apps.shops.models import Shop
from apps.shops.selectors import closed_days, shop_settings_between, shop_today
from apps.staffpay.calculations import NO_FINE, DayResult, Tap, shop_minute, work_out_day
from apps.staffpay.models import (
    AttendanceDay,
    AttendanceEvent,
    ClockKind,
    DayStatus,
    NoPhoto,
    PayRate,
    ReviewReason,
    TimeCheck,
)
from apps.staffpay.selectors import day_rules_between, rates_between, rules_as_text

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
# (ATT-5): a day to decide kept before it had none, and gets its reason the next time it is worked out.
WORKED_OUT = ["status", "fine", "first_in", "first_out", "rules_used", "review_reason"]

# The answer log's link code (apps/core/links.py): the push keeps a line there for each document a laptop sends, and
# flags a suspended or gone worker's tap on that line (X2), not on the tap. The log is a table of `sync`, a layer above
# `staffpay`, so the book names it by its code and asks Django for the table at run time, never importing it
# (ADR-0043). A code that named no table would fail loudly at the first read (UnknownLinkType).
ANSWER_LOG = "pushed_document"


def work_out_days(shop: Shop, first: dt.date, last: dt.date) -> list[AttendanceDay]:
    """Work out and keep each job's day from `first` to `last`, both counted, and answer them, date by date. Only the
    days that count: while attendance is switched on, from each job's first day to its last, and before the shop's
    today; and a day outside a job's days that it tapped on, for a person to decide (ATT-11). A day that comes out as
    it was kept is not written again. The shop must be open: the visit's own, or a system job's."""
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
    dates = [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]
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
        jobs = list(StaffMember.objects.filter(shop=shop).order_by("pk").select_for_update(no_key=True))
        taps, in_doubt = _taps(shop, first, last, zone)
        # The days kept before, each with its job read in the same query: the month page (ATT-5) names each day's
        # worker, and a day answered as it was kept would otherwise read its job alone, one query per day, some 600 for
        # a month of 20 workers. A day kept for the first time carries its job already.
        kept = {
            (row.staff_id, row.date): row
            for row in AttendanceDay.objects.filter(shop=shop, date__range=(first, last)).select_related("staff")
        }
        # The days the whole shop is closed (ATT-8): a public holiday, a family funeral. The attendance switch on each
        # day, and the day's rules on each day (A1). One read each for the whole span, never one per day.
        closed = closed_days(shop, first, last)
        switched_on = shop_settings_between([ATTENDANCE_ON], shop, first, last)
        rules_by_day = day_rules_between(shop, first, last)
        answered: list[AttendanceDay] = []
        for day in dates:
            # Attendance counts only from the day the owner switched it on (ADR-0033), a dated rule, so read on each
            # date: before it, nobody clocked in, and every day kept would be an absence that never was. No day at all,
            # not even an off one.
            if not switched_on[day][ATTENDANCE_ON.key]:
                continue
            # Sunday is off for every job that ran on it, whatever its taps, in doubt or not: the shop is shut, and
            # Sunday work is paid outside the system (01 §8.1). No rule is read for it. A job outside its days keeps
            # no Sunday at all: off pays nothing, so there is nothing for anyone to decide.
            if day.weekday() == SUNDAY:
                answered.extend(_off(shop, job, day) for job in jobs if _ran_on(job, day))
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
                outside = not _ran_on(job, day)
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
        # Kept as the book, never as the person whose visit asked for the month. The edit history's trigger names
        # whoever the visit's note says acts (apps/core/acting.py): Meneja opens November (ATT-5), and Asha's Monday,
        # changed by the Toka that came late, would read "Meneja changed it", though nobody did. So the book tells
        # PostgreSQL the system acts, from no device, for its own writes only (ADR-0036: a row the system writes names
        # nobody); the visit's note comes back as the block ends. And the trigger refuses a row of any shop but this
        # one (T1).
        with acting_as(_TheBook(shop.pk), device=None):
            return _keep(answered, kept)


def _ran_on(job: StaffMember, day: dt.date) -> bool:
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
    asks_not_working, asks_disputed = _doubt_questions(shop)
    lines = (
        # A voided tap counts for nothing (T2): a clock-in tapped twice by mistake, voided by a manager (ATT-6). Nor
        # does it send its day to review: Juma's flagged tap, once voided, leaves his day absent.
        AttendanceEvent.objects.filter(shop=shop, voided_at__isnull=True)
        .filter(_falls_between(first, last, zone))
        .annotate(maker_not_working=asks_not_working, disagreed_with=asks_disputed)
        .values_list(
            "staff_id", "kind", "trusted_time", "client_time", "time_check", "maker_not_working", "disagreed_with"
        )
    )
    taps: dict[_JobDay, list[Tap]] = defaultdict(list)
    in_doubt: dict[_JobDay, ReviewReason] = {}
    for staff_id, kind, trusted_time, client_time, time_check, not_working, disputed in lines:
        day, minute = _where_it_falls(trusted_time, client_time, zone)
        taps[(staff_id, day)].append(Tap(ClockKind(kind), minute))
        # A day with both doubts says the first, in ReviewReason's order (ATT-5): whether a suspended worker is paid at
        # all comes before his time. So a suspension writes over a disagreement, and a disagreement never over one.
        doubt = _doubt_of(not_working, disputed, time_check)
        if doubt == ReviewReason.NOT_WORKING:
            in_doubt[(staff_id, day)] = doubt
        elif doubt is not None:
            in_doubt.setdefault((staff_id, day), doubt)
    return taps, in_doubt


def _falls_between(first: dt.date, last: dt.date, zone: ZoneInfo) -> Q:
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


def _where_it_falls(
    trusted_time: dt.datetime | None, client_time: dt.datetime, zone: ZoneInfo
) -> tuple[dt.date, dt.time | None]:
    # A tap's date on the shop's calendar, by its trusted time, or by the laptop's for one with none; and its minute on
    # the shop's clock, its seconds dropped, as the counter showed it (shop_minute): 07:35:40 is 07:35, on time. No
    # minute for a tap with no trusted time, which sends its day to review (ATT-4).
    day = (trusted_time if trusted_time is not None else client_time).astimezone(zone).date()
    minute = shop_minute(trusted_time, zone) if trusted_time is not None else None
    return day, minute


def _doubt_questions(shop: Shop) -> tuple[Exists, Exists]:
    # The two questions that put a tap in doubt (ATT-11), asked inside the taps' own read, as annotations: the book's
    # (_taps) and a worker's month's (worker_attendance) ask them alike, so the calendar's ! and the tap's own line,
    # "alikuwa amesimamishwa", never disagree (ATT-12). Each answer is turned into a reason by _doubt_of. Two, in this
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


def _doubt_of(not_working: bool, disputed: bool, time_check: str) -> ReviewReason | None:
    # Why a tap is in doubt, from the two questions' answers (_doubt_questions), or None. Made while its worker wasn't
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
    new: list[AttendanceDay] = []
    for day in answered:
        old = kept.get((day.staff_id, day.date))
        if old is None:
            new.append(day)
            rows.append(day)
            continue
        if any(getattr(old, part) != getattr(day, part) for part in WORKED_OUT):
            # Changed: the kept row takes the new answer, so it keeps its id and the day it was first kept.
            for part in WORKED_OUT:
                setattr(old, part, getattr(day, part))
            changed.append(old)
        rows.append(old)
    # A day kept before: an UPDATE by its id, which the edit history's trigger writes down (ADR-0036), Asha's Monday
    # from needs review to on time.
    if changed:
        AttendanceDay.objects.bulk_update(changed, WORKED_OUT)
    # A day kept for the first time: an INSERT. No other run of the book can keep the same day meanwhile, as the jobs'
    # lock lets one run per shop at a time (work_out_days). Should a bug write a day twice all the same, the rule of
    # one day per job and date refuses the second, loudly, a server error, never a second row.
    if new:
        AttendanceDay.objects.bulk_create(new)
    return rows


@dataclass(frozen=True)
class WorkerMonth:
    # One worker's line on the month page: whose, and how many of their days of the month were each kind, every kind
    # but off, as a Sunday or a closed day is nobody's to count; the page shows each beside its mark (✓ Ch ½ H !). A
    # job's line, as a day is a job's: a person hired again in the month has two (PPL-11), each with its own days.
    staff_id: uuid.UUID
    display_name: str
    on_time: int
    late: int
    half: int
    absent: int
    needs_review: int


@dataclass(frozen=True)
class AttendanceMonth:
    # The month page's answer (ATT-5). `month` is its first day; `today` the shop's, so the page knows this month's
    # counts reach yesterday, as the book keeps no day until it is over. `working_day_over`: whether any working day
    # of the month is over, so the page can tell "no day is over yet" from "nobody is paid by the day" (the review).
    month: dt.date
    today: dt.date
    working_day_over: bool
    workers: list[WorkerMonth]
    to_decide: list[AttendanceDay]


def attendance_month(shop: Shop, month: dt.date) -> AttendanceMonth:
    """The month of `month`, any day of it, as the month page shows it (ATT-5): each worker with a daily pay rate on a
    working day of the month the book answers, with their counts, by name; and those workers' days to decide, oldest
    first, each with why. Works the month out through the book (work_out_days), so it writes as the book does, and
    asked twice writes nothing the second time. The shop must be open, as for the book."""
    first, last = _month_span(month)
    # The book's answer, never the table's rows: a day kept to decide that the book no longer answers, its tap voided
    # outside a job's days, stays in its row as it was (rule 7), and is no longer anyone's to decide (ATT-11's review).
    # Only days that are over: this month's stop at yesterday. Each comes with its worker, in the same read.
    days = work_out_days(shop, first, last)
    # Who the shop pays by the day, on each day (WAGE-1): only they are listed. Baba, the owner, never clocks in, so the
    # book keeps him absent every working day; he has no rate, so no line (Jack, ATT-10's review: A). Read on the
    # server, never through the rates route, which a manager who fixes attendance may not open: the page learns who
    # is listed, and no amount (Jack, WAGE-1's review: A). A rate goes on after a job's last day (rates_between), so a
    # worker is listed by the book's days alone: Neema, gone in September, has no October day, so no October line. And
    # by its working days alone, never an off one: Neema, whose last day was Sunday 1 March, would have a line of
    # zeros in March, as if she had worked there (ATT-5's review).
    rates = rates_between(shop, first, last)
    listed = {day.staff_id for day in days if day.status != DayStatus.OFF and (day.staff_id, day.date) in rates}
    counts: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    names: dict[uuid.UUID, str] = {}
    for day in days:
        if day.staff_id in listed:
            counts[day.staff_id][day.status] += 1
            names[day.staff_id] = day.staff.display_name
    workers = [_line(job, names[job], kinds) for job, kinds in counts.items()]
    # By name, as the owner looks for Juma by his name; "asha" beside "Asha", whatever its first letter; then the job's
    # id, so two jobs of one name always come in the same order.
    workers.sort(key=lambda line: (line.display_name.casefold(), line.staff_id))
    # The days to decide, oldest first, as the oldest has waited longest and payday comes for it first; on one day, by
    # name. A listed worker's only: a worker with no rate isn't paid by the day, so nothing of theirs waits here.
    to_decide = sorted(
        (day for day in days if day.staff_id in listed and day.status == DayStatus.NEEDS_REVIEW),
        key=lambda day: (day.date, day.staff.display_name.casefold(), day.staff_id),
    )
    # Whether a working day of the month is over: any day the book answered that isn't off, the owner's absent days
    # included, as every job has its days. False on the 1st, on Monday the 2nd after a Sunday the 1st, after a closed
    # 1st, and in a month to come or before attendance was switched on, when nobody is listed for want of a day, not
    # of a rate (ATT-5's review).
    working_day_over = any(day.status != DayStatus.OFF for day in days)
    return AttendanceMonth(
        month=first, today=shop_today(shop), working_day_over=working_day_over, workers=workers, to_decide=to_decide
    )


def _month_span(month: dt.date) -> tuple[dt.date, dt.date]:
    # The first and the last day of the month of `month`, any day of it. The last as the calendar counts the month's
    # days (30, 31, 28 or 29). Not "the 1st of the month after, less a day": in the calendar's last month, December
    # 9999, that sum runs past the last day Python knows, and a month typed into the address became a server error
    # (ATT-5's review).
    first = month.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def _line(staff_id: uuid.UUID, display_name: str, kinds: Counter[str]) -> WorkerMonth:
    # A worker's line of counts, from how many of their days were each kind. The month page's lines and a worker's own
    # month (ATT-12) count alike, so the calendar's ✓ 11 is the line's ✓ 11.
    return WorkerMonth(
        staff_id=staff_id,
        display_name=display_name,
        on_time=kinds[DayStatus.ON_TIME],
        late=kinds[DayStatus.LATE],
        half=kinds[DayStatus.HALF],
        absent=kinds[DayStatus.ABSENT],
        needs_review=kinds[DayStatus.NEEDS_REVIEW],
    )


class PhotoState(models.TextChoices):
    # What became of a clock-in's photo, as the day under a worker's calendar says it (ATT-12): its file came, and the
    # page may show it; the laptop hasn't sent it yet (CTRL-6); or it was taken away for good, 90 days after its pay
    # run (ATT-7). Not a column: worked out from the photo's row (Attachment, apps/control/models.py) on each read.
    KEPT = "kept", "Kept"
    WAITING = "waiting", "Waiting"
    REMOVED = "removed", "Removed"


@dataclass(frozen=True)
class TapPhoto:
    # A tap's photo: its id, which the photo route opens (`attachments/{id}/file/`, CTRL-3), and what became of it.
    id: uuid.UUID
    state: PhotoState


@dataclass(frozen=True)
class TapLine:
    # One tap, as the day under a worker's calendar shows it (ATT-12): "Ingia 07:20 asubuhi · Laptop ya Dawa", then its
    # photo or why it has none. `date` and `time` on the shop's calendar and clock, by the time the server trusts; a
    # tap with none has no `time`, and its date is the laptop's, as the book places it. `laptop_time` is the laptop's
    # own clock, on the shop's, the only time an untrusted tap has. `doubt`: why the tap itself is in doubt (ATT-11),
    # the push's flag or a later tap's disagreement, or None.
    id: uuid.UUID
    date: dt.date
    kind: ClockKind
    time: dt.time | None
    laptop_time: dt.time
    laptop: str
    photo: TapPhoto | None
    no_photo: NoPhoto | None
    doubt: ReviewReason | None


@dataclass(frozen=True)
class WorkerDay:
    # One of a worker's days, as their calendar marks it and the day says it: what it was, why it waits for a decision
    # on a day to decide, and its fine. The fine is the shop's own rule, which anyone working there may read on the
    # rules page, never the worker's rate or the day's pay (WAGE-1). And the two taps the rule read, the first Ingia and
    # the first Toka after it, for the reason that names one, "alifika saa 09:10", as the month page's list says it.
    date: dt.date
    status: DayStatus
    reason: ReviewReason | None
    fine: Decimal
    first_in: dt.time | None
    first_out: dt.time | None


@dataclass(frozen=True)
class WorkerAttendance:
    # A worker's month, as their calendar shows it (ATT-12): the month, as its first day; the shop's today, so the page
    # marks it (•); their line of counts, as on the month page; their first and last day, for a day outside them to say
    # why; each day the book answers for them, up to yesterday; and each of their taps of the month, today's too.
    month: dt.date
    today: dt.date
    worker: WorkerMonth
    started_on: dt.date
    left_on: dt.date | None
    days: list[WorkerDay]
    taps: list[TapLine]


def worker_attendance(shop: Shop, job: StaffMember, month: dt.date) -> WorkerAttendance:
    """One job's month of `month`, any day of it, as their calendar and its days show it (ATT-12): the book's days of
    the job, worked out through the book as the month page's are (work_out_days), so it writes as the book does, and
    asked twice writes nothing the second time; their counts; and every tap of the job in the month, today's too, none
    voided, each with its laptop, its photo or why none, and whether it is in doubt. The shop must be open, and the job
    one of it."""
    # The job is the shop's: the route finds it through the guard, so another shop's never comes here; but a service
    # checks what it is given (T1), so a bug that passed one would fail loudly, never answer another shop's taps.
    if job.shop_id != shop.pk:
        raise ShopMismatch("worker_attendance was given a job of another shop.")
    first, last = _month_span(month)
    # The whole shop's month, as the month page asks it: the book works out every job's days at once, under one lock
    # (work_out_days), so the calendar and the month page's line never come from two different workings out. Then this
    # job's days alone. Every day the book answers, off days too, which the calendar marks with –.
    days = [day for day in work_out_days(shop, first, last) if day.staff_id == job.pk]
    kinds = Counter(day.status for day in days if day.status != DayStatus.OFF)
    zone = ZoneInfo(shop.timezone)
    today = shop_today(shop)
    # The taps up to today, the last day the calendar shows: a day to come has none to show. And never read past the
    # month's end into the day after it: in the calendar's last month, December 9999, that day is past the last one
    # Python knows, and a month typed into the address was a server error, as on the month page before (ATT-12's
    # review, ATT-5's). A month to come has no tap at all, and nothing is read.
    taps_until = min(last, today)
    # The job's taps of the month, in one read, today's too: the book keeps no day until it is over (ATT-10), so
    # today's taps are read here as they come. Each with its laptop's name, joined in the same read, and the two
    # questions of doubt the book asks (_doubt_questions). A voided tap counts for nothing (T2), and the book doesn't
    # read it, so nor does this: ATT-6, which voids one, shows them crossed out (A2). In the order they were made, by
    # the time the book places them by, then by the laptop's own numbering, as two taps can share a minute.
    asks_not_working, asks_disputed = _doubt_questions(shop)
    lines = (
        []
        if taps_until < first
        else list(
            AttendanceEvent.objects.filter(shop=shop, staff=job, voided_at__isnull=True)
            .filter(_falls_between(first, taps_until, zone))
            .annotate(maker_not_working=asks_not_working, disagreed_with=asks_disputed)
            .order_by(Coalesce("trusted_time", "client_time"), "device_seq")
            .values_list(
                "pk",
                "kind",
                "trusted_time",
                "client_time",
                "time_check",
                "device__name",
                "no_photo",
                "maker_not_working",
                "disagreed_with",
            )
        )
    )
    photos = _photos_of(shop, [line[0] for line in lines])
    taps = []
    for tap_id, kind, trusted_time, client_time, time_check, laptop, no_photo, maker_not_working, disagreed in lines:
        day, minute = _where_it_falls(trusted_time, client_time, zone)
        taps.append(
            TapLine(
                id=tap_id,
                date=day,
                kind=ClockKind(kind),
                time=minute,
                laptop_time=shop_minute(client_time, zone),
                laptop=laptop,
                photo=photos.get(tap_id),
                # Empty when its photo came (ATT-3): said as no reason at all.
                no_photo=NoPhoto(no_photo) if no_photo else None,
                doubt=_doubt_of(maker_not_working, disagreed, time_check),
            )
        )
    return WorkerAttendance(
        month=first,
        today=today,
        worker=_line(job.pk, job.display_name, kinds),
        started_on=job.started_on,
        left_on=job.left_on,
        days=[
            WorkerDay(
                date=day.date,
                status=DayStatus(day.status),
                # The table keeps "no reason" as empty (ATT-5): said as None.
                reason=ReviewReason(day.review_reason) if day.review_reason else None,
                fine=day.fine,
                first_in=day.first_in,
                first_out=day.first_out,
            )
            for day in days
        ],
        taps=taps,
    )


def _photos_of(shop: Shop, tap_ids: list[uuid.UUID]) -> dict[uuid.UUID, TapPhoto]:
    # The clock-in photos of these taps, by tap, in one read, through the index on each record's attachments
    # (control_attachment_by_subject), never one read per tap. A photo's row is pinned to its tap by the tap's table's
    # code and its id (a generic link, CTRL-3), the code a clock-in photo's rule names. None asked for none.
    if not tap_ids:
        return {}
    pinned_to = ATTACHMENT_KINDS[AttachmentKind.CLOCK_PHOTO].subject_type
    rows = Attachment.objects.filter(
        shop=shop, kind=AttachmentKind.CLOCK_PHOTO, subject_type=pinned_to, subject_id__in=tap_ids
    ).values_list("id", "subject_id", "file", "file_removed_at")
    photos: dict[uuid.UUID, TapPhoto] = {}
    for photo_id, tap_id, file, removed_at in rows:
        # Removed first: a removed photo's file is empty, as is one still waiting, so only its removal tells them apart.
        state = PhotoState.REMOVED if removed_at is not None else PhotoState.KEPT if file else PhotoState.WAITING
        # One photo per tap: the clock document names one, and its id is the row's (expect_attachment).
        photos[tap_id] = TapPhoto(id=photo_id, state=state)
    return photos


def set_pay_rate(
    staff: StaffMember,
    *,
    daily_rate: Decimal,
    effective_from: dt.date,
    shares_meals: bool = True,
    note: str = "",
    rate_id: uuid.UUID | None = None,
    by: StaffMember | None,
) -> PayRate:
    """Give a worker a daily pay rate from the day `effective_from` on: one new PayRate row (WAGE-1, 02 §12). A raise
    is a new rate from its day; a rate typed wrong is mended by a new one for the same day, which counts, as the newest.
    `shares_meals`: False for the cook, who pays no share of the meals (WAGE-7). `rate_id`: the id the client made for
    the row (ADR-0007), if it made one. `by`: who sets it, under the PIN's rule and with settings.manage on the whole
    shop; None for the system or the superuser. Refuses, all together, each beside its box: an amount of 0 or less, or
    with cents (pay_rate.amount_invalid); a day before the job's first (pay_rate.before_first_day); and on the demo, a
    person's note (demo.no_note). Returns the rate as saved."""
    # Spaces around a note say nothing, and "  " is no note.
    note = note.strip()
    # One transaction: the lock below holds until the rate is saved, so who may is asked of the jobs as they are when it
    # is written. Not a recording_changes block: a rate writes no line in the change log, as no laptop gets one.
    with transaction.atomic():
        # Both jobs locked, then who may asked on them as they are now, by the people app, which owns the rule (02 §5):
        # whoever sets a rate sets a worker's pay, as whoever sets a PIN can act as them. So staff.manage on the whole
        # shop, holding every key the worker was given; never one's own rate (a manager raising his own pay); an owner's
        # only by the superuser. The same lock the book of days takes on every job (work_out_days), so a rate set while
        # a manager opens the month waits a moment for it.
        staff, by = lock_worker_for_a_change(staff, by)
        # And the key that changes the shop's rules and rates, the owner's (spec §6): a manager handed staff.manage to
        # reset PINs, or to add a loader, may not change anyone's pay with it (WAGE-1's card). Read afresh, after the
        # lock, as the rule above reads its own key: a key taken away a moment ago counts.
        if by is not None:
            require(by, Permission.SETTINGS_MANAGE, None)
        # A job that ended is history: its pay up to its last day is worked out with the rates it had. Asked of a person
        # by the rule above already; here for the system too, as change_worker asks it.
        if staff.status == StaffStatus.LEFT:
            raise ValidationError("This person has already left.", code="staff.left")
        # The boxes, all together, so a person who typed two wrong sees both at once, each beside its box. Each a code
        # the page translates (ADR-0040).
        errors: dict[str, list[ValidationError]] = {}
        # More than nothing, in whole shillings (Jack, 16 Nov 2026), as the table's two rules hold: named here, beside
        # the amount's box, where the table's own rules would name the whole row. to_integral_value() drops the places
        # without rounding the check away: 10000.50 is not whole.
        if daily_rate <= 0 or daily_rate != daily_rate.to_integral_value():
            errors["daily_rate"] = [
                ValidationError("A day's pay is a whole amount above 0.", code="pay_rate.amount_invalid")
            ]
        # Any day of the job, gone by or to come: Juma started on 10 Nov and Baba types his rate on the 19th, from the
        # 10th, so those days are paid. Never before the job's first day, read under the lock: a day before it is not a
        # day of this job to pay. A day in an approved month is WAGE-3's to refuse, once pay runs exist.
        if effective_from < staff.started_on:
            errors["effective_from"] = [
                ValidationError("A rate can't start before the worker's first day.", code="pay_rate.before_first_day")
            ]
        # On the demo every visitor logs in as Meneja (OPS-3): a note would show to every visitor after them, signed by
        # the shared manager, until the morning's seed, so a person's note isn't kept, as for a rule (demo.no_note,
        # set_setting). The seed's people are already refused above (demo.people_fixed); a worker a visitor added can
        # be given a rate, as trying that is the point. The system, as the seed acts, still may.
        if settings.DEMO_SEED and by is not None and note:
            errors["note"] = [ValidationError("On the demo, a note isn't kept.", code="demo.no_note")]
        if errors:
            raise ValidationError(errors)
        rate = PayRate(
            shop_id=staff.shop_id,
            staff=staff,
            daily_rate=daily_rate,
            effective_from=effective_from,
            shares_meals=shares_meals,
            note=note,
            created_by=by,
        )
        if rate_id is not None:
            # The client's id, not a new one: a retry of the same request then finds the rate it made.
            rate.id = rate_id
        # The row's own checks last, as a guard on what the boxes above already asked: a note too long, an id taken.
        rate.full_clean()
        rate.save()
    return rate
