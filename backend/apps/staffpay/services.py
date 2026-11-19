"""apps/staffpay/services.py — the writes of attendance and pay: the book of days (ATT-10; 02 §12), and each worker's
daily pay rate (WAGE-1).

    work_out_days(MPC, 16 Nov, 22 Nov)  → each job's day of that week, worked out, kept and answered:
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Juma   Mon 16 Nov  needs_review  0.00    07:20  —          no Toka: a manager decides (ATT-6)
    Juma   Tue 17 Nov  needs_review  0.00    07:20  18:45      suspended on Monday: a tap in doubt (ATT-11)
    Asha   Sun 22 Nov  off           0.00    —      —          the shop is shut on Sundays and closed days

The day's rule (work_out_day, apps/staffpay/calculations.py) says what one day was; the book finds each day's taps and
rules, hands them in, and keeps the answer, one row per job and date (AttendanceDay). Three kinds of day the rule can't
see go to review: a closed day with a tap (ATT-10); and a day with a tap in doubt, or outside a job's days with a tap
(ATT-11). Nothing here is typed by a person: the days are answers, worked out again each time they are asked for, as a
tap can come late from a laptop that was offline, a manager can void a tap (ATT-6), and a job's first or last day can be
moved (PPL-10). ATT-5 asks for a month to show, WAGE-2 for a month to pay, ATT-7 each night. No route of its own, and no
line in the change log: no laptop keeps a copy of the days.

A pay rate is typed by a person, the owner (set_pay_rate): from 10 Nov, Juma earns 10,000 a day. Whoever sets it sets a
worker's pay, so who may is the PIN's rule, asked by the people app (02 §5). No line in the change log either: a
worker's pay never sits on a shared device (03 §6.1).
"""

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from apps.control.models import Flag, FlagKind
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
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind, DayStatus, PayRate, TimeCheck
from apps.staffpay.selectors import day_rules_between, rules_as_text

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
# or the shop, which say which day it is; nor `created_at`, which says when the day was first kept.
WORKED_OUT = ["status", "fine", "first_in", "first_out", "rules_used"]

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
                if day in closed or (job.pk, day) in in_doubt or outside:
                    result = replace(result, status=DayStatus.NEEDS_REVIEW, fine=NO_FINE)
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
    )


def _answer_log() -> Any:
    # The answer log's table, asked of Django by its link code. Any, not its model: to know the table's columns, the
    # type checker would have to import `sync`'s model, which the layers forbid (ADR-0043). So its `document_id` is
    # proven by the tests instead: the book's (test_a_suspended_workers_tap_needs_review) and the push's own, which
    # finds a clock-in's line by it (test_suspended_worker_clock_in_flagged, apps/sync/tests/test_clock_in.py).
    return table_of(ANSWER_LOG)


# A day of a job: the job's id and the shop's date.
type _JobDay = tuple[uuid.UUID, dt.date]


def _taps(shop: Shop, first: dt.date, last: dt.date, zone: ZoneInfo) -> tuple[dict[_JobDay, list[Tap]], set[_JobDay]]:
    # Each job's taps on each date from `first` to `last`, as the rule reads them, and the days with a tap in doubt,
    # which a person must decide (ATT-11). A day's edges are the shop's own midnights, not UTC's: Asha's tap at 21:30
    # UTC on Monday is Tuesday's, at 00:30 in Arusha. So the span is read from the midnight starting its first day to
    # the one ending its last, each a moment with its zone.
    start = dt.datetime.combine(first, dt.time.min, tzinfo=zone)
    end = dt.datetime.combine(last + dt.timedelta(days=1), dt.time.min, tzinfo=zone)
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
    lines = (
        # A voided tap counts for nothing (T2): a clock-in tapped twice by mistake, voided by a manager (ATT-6). Nor
        # does it send its day to review: Juma's flagged tap, once voided, leaves his day absent.
        AttendanceEvent.objects.filter(shop=shop, voided_at__isnull=True)
        .filter(
            # By the time the server trusts, never the laptop's, whose clock anyone can move (ATT-1): through the
            # index on (shop, trusted_time). One with no trusted time (`unverified`) by the laptop's time instead,
            # the only one it has: its day needs review anyway, but it must land on a day for a manager to see it.
            Q(trusted_time__gte=start, trusted_time__lt=end)
            | Q(trusted_time__isnull=True, client_time__gte=start, client_time__lt=end)
        )
        .annotate(maker_not_working=maker_not_working, disagreed_with=disagreed_with)
        .values_list(
            "staff_id", "kind", "trusted_time", "client_time", "time_check", "maker_not_working", "disagreed_with"
        )
    )
    taps: dict[_JobDay, list[Tap]] = defaultdict(list)
    in_doubt: set[_JobDay] = set()
    for staff_id, kind, trusted_time, client_time, time_check, not_working, disputed in lines:
        # Its date on the shop's calendar, by its trusted time, or by the laptop's for one with none.
        day = (trusted_time if trusted_time is not None else client_time).astimezone(zone).date()
        # Its minute on the shop's clock, its seconds dropped, as the counter showed it (shop_minute): 07:35:40 is
        # 07:35, on time. None for a tap with no trusted time, which sends the day to review (ATT-4).
        minute = shop_minute(trusted_time, zone) if trusted_time is not None else None
        taps[(staff_id, day)].append(Tap(ClockKind(kind), minute))
        # In doubt: made while its worker wasn't working, or timed by a laptop clock a later tap disagrees with. Only
        # by the laptop's clock (`device_ok`): a tap sent at once has the server's time, which no laptop's clock can
        # make wrong, and one with no trusted time sends its day to review already (ATT-4).
        if not_working or (disputed and time_check == TimeCheck.DEVICE_OK):
            in_doubt.add((staff_id, day))
    return taps, in_doubt


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
