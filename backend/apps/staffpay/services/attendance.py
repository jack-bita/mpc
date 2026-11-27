"""apps/staffpay/services/attendance.py — attendance as a person sees and fixes it: the month the month page shows
(ATT-5), a worker's own month (ATT-12), a person's decision on a day (ATT-6), and a manager's fixes to the taps
(ATT-13). All of it through the book of days (book.py).

The month page (ATT-5) asks for a month through attendance_month, which its route calls (GET attendance-month/): the
book's days, a line per worker the shop pays by the day with how many days were each kind, and the days a person must
decide, each with why. So that GET writes, as the book keeps the days it works out; asked twice, the month writes
nothing the second time.

A worker's name on that page opens their own month (ATT-12), through worker_attendance, which its route calls (GET
attendance-worker/{id}/): the book's days of that job, worked out the same way, and every tap of the month, today's too,
with its laptop, its photo or why none, and whether it is in doubt, the question the book asks too (doubt_questions),
so the calendar's ! and the tap's own line never disagree.

A day to decide is decided by a person (decide_day): the owner, or a manager, never on their own day (Jack, ATT-6).
Juma's Thursday with no Toka is a full day, "Alisahau kubonyeza Toka". The decision sits beside what the book worked
out, which stays visible (A2), in columns the book never writes (DECISION), and a day decided late or half takes the
fine its first Ingia gives by its own rules (day_choices, T4). No line in the change log: no laptop keeps a day.

A tap is fixed by a person, the owner or a manager, never on their own taps (ATT-13): Juma tapped Toka at 10:00 by
mistake and worked on to 18:45, so Baba crosses out the 10:00 Toka (void_tap) and adds Toka 18:45 (add_tap), each
with a reason. An added tap is a line of the attendance book like a laptop's, with no laptop, its time the minute typed,
trusted; a tap crossed out stays in the book, voided once with who, when and why, and counts for nothing (T2). The book
reads both the next time it works the day out, as it reads every tap.
"""

import datetime as dt
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.control.models import ATTACHMENT_KINDS, Attachment, AttachmentKind
from apps.core.changes import record_change, recording_changes
from apps.core.editing import VersionConflict
from apps.core.permissions import Permission
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import ShopMismatch
from apps.people.models import StaffMember
from apps.people.permissions import require
from apps.shops.models import Shop
from apps.shops.selectors import get_setting, shop_today
from apps.staffpay.calculations import TIME_IN_DOUBT, day_choices, shop_minute
from apps.staffpay.models import (
    DECISION_OF,
    AbsenceType,
    AttendanceDay,
    AttendanceEvent,
    ClockKind,
    DayChoice,
    DayStatus,
    NoPhoto,
    ReviewReason,
    TimeCheck,
)
from apps.staffpay.selectors import closed_pay, closings, rates_between, rules_from_text
from apps.staffpay.services.book import (
    SUNDAY,
    doubt_of,
    doubt_questions,
    falls_between,
    month_span,
    past_deciding,
    ran_on,
    refuse_if_closed,
    where_it_falls,
    work_out_days,
)

# A person's decision on a day (ATT-6), which only decide_day writes, and the book never: what the book works out
# (WORKED_OUT, book.py) and what a manager decided are two lists with no column in common, so neither ever writes over
# the other (A2).
DECISION = ["decided_status", "absence_type", "decided_fine", "decided_by", "decided_at", "decision_reason"]


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
    first, last = month_span(month)
    # The book's answer, never the table's rows: a day kept to decide that the book no longer answers, its tap voided
    # outside a job's days, stays in its row as it was (rule 7), and is no longer anyone's to decide (ATT-11's review).
    # Only days that are over: this month's stop at yesterday. Each comes with its worker, in the same read.
    closed = closed_pay(shop)
    # Without the days whose pay was approved before they came (past_deciding): they are nobody's to decide or to count.
    days = [day for day in work_out_days(shop, first, last) if not past_deciding(day, closed)]
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
            counts[day.staff_id][_counted_as(day)] += 1
            names[day.staff_id] = day.staff.display_name
    workers = [_line(job, names[job], kinds) for job, kinds in counts.items()]
    # By name, as the owner looks for Juma by his name; "asha" beside "Asha", whatever its first letter; then the job's
    # id, so two jobs of one name always come in the same order.
    workers.sort(key=lambda line: (line.display_name.casefold(), line.staff_id))
    # The days to decide, oldest first, as the oldest has waited longest and payday comes for it first; on one day, by
    # name. A listed worker's only: a worker with no rate isn't paid by the day, so nothing of theirs waits here. A day
    # someone has decided waits no more (ATT-6), though the book still says it needs review beside the decision (A2).
    to_decide = sorted(
        (
            day
            for day in days
            if day.staff_id in listed and day.status == DayStatus.NEEDS_REVIEW and not day.decided_status
        ),
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


def _counted_as(day: AttendanceDay) -> str:
    # What a day counts as on a worker's line of the month (ATT-5, ATT-12): the decision once there is one (ATT-6), else
    # the book's answer. An absence by its kind: office duty is a full day paid, so it counts with ✓; permission and a
    # no-show are unpaid, so they count with H (a default, in the plan Jack approved). The calendar marks each day
    # by its kind (O, R, H); the line keeps its five counts.
    if day.absence_type == AbsenceType.OFFICE_DUTY:
        return DayStatus.ON_TIME
    return day.decided_status or day.status


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
class TapStamp:
    # Who added a tap in the office, or crossed one out (ATT-13), by nickname on this shop, as every name on these pages
    # is; when, the server's moment; and why: "imeongezwa na Baba, 19/11 · Sababu: Alisahau kubonyeza Toka". On the
    # demo the reason is a ready one's code (`forgot_tap`), which the page says in words.
    by: str
    at: dt.datetime
    reason: str


@dataclass(frozen=True)
class TapLine:
    # One tap, as the day under a worker's calendar shows it (ATT-12): "Ingia 07:20 asubuhi · Laptop ya Dawa", then its
    # photo or why it has none. `date` and `time` on the shop's calendar and clock, by the time the server trusts; a
    # tap with none has no `time`, and its date is the laptop's, as the book places it. `laptop_time` is the laptop's
    # own clock, on the shop's, the only time an untrusted tap has. A tap entered in the office (ATT-13) has neither a
    # laptop nor its clock, so `laptop` and `laptop_time` are None, and its `time` is the one the manager typed.
    # `doubt`: why the tap itself is in doubt (ATT-11), the push's flag or a later tap's disagreement, or None.
    id: uuid.UUID
    date: dt.date
    kind: ClockKind
    time: dt.time | None
    laptop_time: dt.time | None
    laptop: str | None
    photo: TapPhoto | None
    no_photo: NoPhoto | None
    doubt: ReviewReason | None
    # Who entered it in the office, when and why, or None for a laptop's tap (ATT-13); and who crossed it out, when and
    # why, or None while it counts. A tap crossed out still shows, struck through (A2), and is never in doubt, as it
    # counts for nothing.
    entered: TapStamp | None
    voided: TapStamp | None
    # Whether it came after its day's pay was approved (WAGE-10): kept, counted nowhere, and flagged (late_record), so
    # the day says so beside it. Its day as the book places it, the job's own approval, alone or with the month.
    after_approval: bool = False


@dataclass(frozen=True)
class DayDecision:
    # A decision as the day shows it: "Siku kamili · uamuzi wa Baba, 20/11 · Sababu: Alisahau kubonyeza Toka". `by` is
    # the decider's nickname on this shop, as every other name on these pages is. `at` is when it was made, which a
    # page sends back when it decides the day again (`replaces`), so a decision it never saw is never written over.
    status: DayStatus
    absence_type: AbsenceType | None
    fine: Decimal
    by: str
    at: dt.datetime
    reason: str


@dataclass(frozen=True)
class DayOption:
    # One line of the sheet: a choice and the fine it takes, "Amechelewa · faini 500".
    choice: DayChoice
    fine: Decimal


@dataclass(frozen=True)
class WorkerDay:
    # One of a worker's days, as their calendar marks it and the day says it: what it was, why it waits for a decision
    # on a day to decide, and its fine. The fine is the shop's own rule, which anyone working there may read on the
    # rules page, never the worker's rate or the day's pay (WAGE-1). Its share of the date's meals too, as the book kept
    # it, the same for everyone who came (WAGE-7, as Jack drew the day), 0 for none. And the two taps the rule read, the
    # first Ingia and the first Toka after it, for the reason that names one, "alifika saa 09:10", as the month page's
    # list says it. Its id: the address a decision on it is sent to (attendance-days/{id}/decide/, ATT-6).
    id: uuid.UUID
    date: dt.date
    status: DayStatus
    reason: ReviewReason | None
    fine: Decimal
    meal_share: Decimal
    first_in: dt.time | None
    first_out: dt.time | None
    # A person's decision on the day, or None (ATT-6), shown beside what the book said, which stays (A2).
    decision: DayDecision | None
    # What the day may be decided as, each with its fine (day_choices), in the sheet's order: none on an off day, on one
    # whose pay is approved (WAGE-3), or when the month is the viewer's own, as nobody decides their own day (Jack,
    # ATT-6).
    choices: list[DayOption]
    # Whether a tap of the day was added, arrived from a laptop, or was crossed out after the day was decided (Jack: A,
    # ATT-13): the decision stays, as the book never writes over one, and the day says its taps changed since, for
    # whoever looks to decide it again. False on a day nobody decided.
    taps_changed: bool


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
    # Whether the month is the viewer's own: then no day of it is theirs to decide, and the page says the owner decides
    # it (Jack, ATT-6).
    yours: bool
    # Whether the month's pay is approved, with everyone's or the worker's alone (WAGE-3): then its days take no
    # decision and its taps no fix, and the page says so.
    closed: bool
    # On the demo, the three ready reasons a decision may take (DEMO_REASONS, Jack: A), as codes the page says in
    # words; elsewhere none, and a person types their own.
    ready_reasons: list[str]
    # The same for a tap added and a tap crossed out (DEMO_ADD_REASONS, DEMO_VOID_REASONS, ATT-13): one each.
    ready_add_reasons: list[str]
    ready_void_reasons: list[str]


def worker_attendance(shop: Shop, job: StaffMember, month: dt.date, *, viewer: StaffMember | None) -> WorkerAttendance:
    """One job's month of `month`, any day of it, as their calendar and its days show it (ATT-12): the book's days of
    the job, worked out through the book as the month page's are (work_out_days), so it writes as the book does, and
    asked twice writes nothing the second time; their counts; and every tap of the job in the month, today's too, the
    crossed-out ones among them (ATT-13), each with its laptop, or who added it in the office, its photo or why none,
    whether it is in doubt, and who crossed it out, when and why. Each day with its decision and
    what it may be decided as (ATT-6), as `viewer` may decide it: the person looking, or None for the system. The shop
    must be open, and the job one of it."""
    # The job is the shop's: the route finds it through the guard, so another shop's never comes here; but a service
    # checks what it is given (T1), so a bug that passed one would fail loudly, never answer another shop's taps.
    if job.shop_id != shop.pk:
        raise ShopMismatch("worker_attendance was given a job of another shop.")
    first, last = month_span(month)
    # The whole shop's month, as the month page asks it: the book works out every job's days at once, under one lock
    # (work_out_days), so the calendar and the month page's line never come from two different workings out. Then this
    # job's days alone. Every day the book answers, off days too, which the calendar marks with –.
    # Nor one whose pay was approved before it came (past_deciding): its taps stay to be read, marked +, as on any day
    # that isn't counted.
    approved = closed_pay(shop)
    days = [
        day for day in work_out_days(shop, first, last) if day.staff_id == job.pk and not past_deciding(day, approved)
    ]
    kinds = Counter(_counted_as(day) for day in days if day.status != DayStatus.OFF)
    # Never one's own day (Jack, ATT-6): by the person, as decide_day asks it, so a person hired again (PPL-11) can't
    # decide the days of either of their jobs.
    yours = viewer is not None and viewer.user_id == job.user_id
    # Whether the month's pay is approved, with everyone's or theirs alone (WAGE-3): then nothing of it may change.
    closed = approved.holds(job.pk, first)
    # Who decided, by nickname, in one read for the whole month, never one per day.
    deciders = dict(
        StaffMember.objects.filter(pk__in={day.decided_by_id for day in days if day.decided_by_id}).values_list(
            "pk", "display_name"
        )
    )
    zone = ZoneInfo(shop.timezone)
    today = shop_today(shop)
    # The taps up to today, the last day the calendar shows: a day to come has none to show. And never read past the
    # month's end into the day after it: in the calendar's last month, December 9999, that day is past the last one
    # Python knows, and a month typed into the address was a server error, as on the month page before (ATT-12's
    # review, ATT-5's). A month to come has no tap at all, and nothing is read.
    taps_until = min(last, today)
    # Read after the book has kept the month's days, in a read of its own, so the two can disagree for a moment: Asha's
    # Toka, pushed between them, shows in the list while her day still says "hakuna Toka". The next ask works the day
    # out again with it (work_out_days), so it mends itself within a minute of the page asking again (ATT-12's review).
    # Not one transaction with the book: the book's lock would then be held for this read too, and every other run of
    # the book, a month page or the night's job, would wait for it.
    # The job's taps of the month, in one read, today's too: the book keeps no day until it is over (ATT-10), so
    # today's taps are read here as they come; the crossed-out ones too (ATT-13), and those added in the office, as
    # _tap_lines reads every tap.
    read = (
        []
        if taps_until < first
        else _tap_lines(
            shop, AttendanceEvent.objects.filter(shop=shop, staff=job).filter(falls_between(first, taps_until, zone))
        )
    )
    taps = [tap for tap, _ in read]
    # When each day's taps last changed: a tap kept (a laptop's arriving, or one added in the office) or crossed out.
    # A day decided before that moment says its taps changed since (ATT-13).
    changed: dict[dt.date, dt.datetime] = {}
    for tap, moment in read:
        changed[tap.date] = max(changed.get(tap.date, moment), moment)
    return WorkerAttendance(
        month=first,
        today=today,
        worker=_line(job.pk, job.display_name, kinds),
        started_on=job.started_on,
        left_on=job.left_on,
        days=[
            WorkerDay(
                id=day.pk,
                date=day.date,
                status=DayStatus(day.status),
                # The table keeps "no reason" as empty (ATT-5): said as None.
                reason=ReviewReason(day.review_reason) if day.review_reason else None,
                fine=day.fine,
                meal_share=day.meal_share,
                first_in=day.first_in,
                first_out=day.first_out,
                decision=decision_of(day, deciders),
                # None on a day whose pay is approved either (WAGE-3): it takes no decision, and its copy of the rules,
                # which its choices' fines are read from, is never read again, so a rule added years from now, missing
                # from that copy, stops no page from opening (ATT-6's review).
                choices=[]
                if yours or day.status == DayStatus.OFF or closed
                else [
                    DayOption(choice=choice, fine=fine)
                    for choice, fine in day_choices(
                        day.first_in, rules_from_text(day.rules_used), time_in_doubt=day.review_reason in TIME_IN_DOUBT
                    ).items()
                ],
                taps_changed=day.decided_at is not None and day.date in changed and changed[day.date] > day.decided_at,
            )
            for day in days
        ],
        taps=taps,
        yours=yours,
        closed=closed,
        ready_reasons=list(DEMO_REASONS) if settings.DEMO_SEED else [],
        ready_add_reasons=list(DEMO_ADD_REASONS) if settings.DEMO_SEED else [],
        ready_void_reasons=list(DEMO_VOID_REASONS) if settings.DEMO_SEED else [],
    )


def _tap_lines(shop: Shop, taps: QuerySet[AttendanceEvent]) -> list[tuple[TapLine, dt.datetime]]:
    # Each of `taps` as the day under a worker's calendar shows it (ATT-12), with the moment it last changed: when it
    # was kept (a laptop's push arriving, or a manager entering it) or, later, crossed out (ATT-13). In one read,
    # whatever their number: each with its laptop's name, joined in, and the two questions of doubt the book asks
    # (doubt_questions), so the calendar's ! and the tap's own line never disagree; the crossed-out ones too, each with
    # who, when and why, for the day to show struck through (A2), though the book doesn't read them, as they count for
    # nothing (T2); and those added in the office with who entered it, when and why, both names joined in the same
    # read; then their photos in one more (_photos_of). In the order they were made, by the moment the book places them
    # by; two of one moment, rare, as on two laptops at once, by their ids, which each laptop makes in time order
    # (UUIDv7, ADR-0007): never by a laptop's own numbering, which says nothing between two laptops (ATT-12's review).
    zone = ZoneInfo(shop.timezone)
    asks_not_working, asks_disputed = doubt_questions(shop)
    # Rows named by their columns (`named=True`), as there are fifteen. Any: the type checker's Django plugin can't
    # read the joined names' types.
    lines: list[Any] = list(
        taps.annotate(maker_not_working=asks_not_working, disagreed_with=asks_disputed)
        .order_by(Coalesce("trusted_time", "client_time"), "pk")
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
            "received_at",
            "created_by__display_name",
            "entry_reason",
            "voided_at",
            "voided_by__display_name",
            "void_reason",
            "staff_id",
            "created_at",
            named=True,
        )
    )
    photos = _photos_of(shop, [line.pk for line in lines])
    # When each day's pay closed, for the jobs of these taps, in two reads more (WAGE-10).
    closed = closings(shop, {line.staff_id for line in lines})
    answered = []
    for line in lines:
        day, minute = where_it_falls(line.trusted_time, line.client_time, zone)
        voided = (
            None
            if line.voided_at is None
            else TapStamp(by=line.voided_by__display_name, at=line.voided_at, reason=line.void_reason)
        )
        tap = TapLine(
            id=line.pk,
            date=day,
            kind=ClockKind(line.kind),
            time=minute,
            # None for a tap entered in the office, which no laptop clock timed (ATT-13).
            laptop_time=shop_minute(line.client_time, zone) if line.client_time is not None else None,
            laptop=line.device__name,
            photo=photos.get(line.pk),
            # Empty when its photo came (ATT-3): said as no reason at all.
            no_photo=NoPhoto(line.no_photo) if line.no_photo else None,
            # A tap crossed out counts for nothing, so nothing about it is in doubt.
            doubt=None if voided else doubt_of(line.maker_not_working, line.disagreed_with, line.time_check),
            entered=TapStamp(by=line.created_by__display_name, at=line.received_at, reason=line.entry_reason)
            if line.time_check == TimeCheck.ENTERED
            else None,
            voided=voided,
            # It was kept after its day's pay was approved: by the moment its row was written, which the push takes
            # under the job's lock (post_clock), so it orders as the lock does, never by the push's arrival, which is
            # one moment for a whole batch, read before any of its taps waited for an approval. One entered in the
            # office never is, as a closed day takes none (add_tap).
            after_approval=(since := closed.since(line.staff_id, day)) is not None and line.created_at > since,
        )
        answered.append((tap, max(line.received_at, line.voided_at or line.received_at)))
    return answered


def tap_line(tap: AttendanceEvent) -> TapLine:
    """One tap as the day under a worker's calendar shows it (ATT-13), read afresh as a worker's month reads its taps
    (_tap_lines): what the routes that add and cross out a tap answer, so the sheet shows the tap as the day will. The
    shop must be open, and be the tap's."""
    shop = Shop.objects.get(pk=tap.shop_id)
    return _tap_lines(shop, AttendanceEvent.objects.filter(shop=shop, pk=tap.pk))[0][0]


def decision_of(day: AttendanceDay, deciders: dict[uuid.UUID, str]) -> DayDecision | None:
    """A day's decision as the page shows it (ATT-6), or None when nobody has decided it. `deciders`: the nickname of
    each job that decided, by id, read once for many days. The table keeps "no kind" as empty: said as None. Whole or
    none, as the table's own rule holds, so every part is there once decided_at is."""
    if day.decided_at is None or day.decided_by_id is None or day.decided_fine is None:
        return None
    return DayDecision(
        status=DayStatus(day.decided_status),
        absence_type=AbsenceType(day.absence_type) if day.absence_type else None,
        fine=day.decided_fine,
        by=deciders[day.decided_by_id],
        at=day.decided_at,
        reason=day.decision_reason,
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


# On the demo every visitor logs in as Meneja (OPS-3): a reason one visitor typed would show to every visitor after
# them, until the morning's seed makes the shop again, so a reason there is one of three ready ones the sheet offers,
# kept as its code, which the page says in words (Jack: A, 20 Nov 2026): *Alisahau kubonyeza Toka*, *Alikuwa kazini
# nje*, *Ameruhusiwa na mwenye duka*. Visitors still try the whole of deciding a day, and nobody types free text there.
DEMO_REASONS = ("forgot_toka", "away_on_work", "owner_allowed")


def decide_day(
    day: AttendanceDay, *, choice: DayChoice, reason: str, replaces: dt.datetime | None, by: StaffMember
) -> AttendanceDay:
    """Decide what a worker's day was (ATT-6, 02 §12): Juma's Thursday, sent to review with no Toka, is a full day,
    "Alisahau kubonyeza Toka". The decision is kept beside what the book worked out, which stays as it was (A2), with
    its fine (day_choices, from the day's first Ingia and its own rules, T4), who, when and why. `replaces`: when the
    decision the person saw was made, or None if they saw none. `by`: who decides, with attendance.manage on the whole
    shop, and never the day's own worker. The same decision sent again by its maker, its first answer lost, is answered
    as done. Refuses: one's own day (day.own); a day that isn't a working day gone by (day.not_working_day); a day whose
    pay is approved (pay.day_approved); someone else decided it since (VersionConflict, 409); and, all together, each
    beside its box, a choice the day can't take (day.choice_not_offered), no reason (day.reason_missing), or on the demo
    a reason not one of the ready ones (demo.ready_reasons). Returns the day as saved."""
    # A job of another shop deciding this shop's day is a bug in the calling code (T1), never a person's mistake: the
    # route finds the day and the person in the one shop open. A server error, before anything is read.
    if by.shop_id != day.shop_id:
        raise ShopMismatch("decide_day was given a person of another shop.")
    # Spaces around a reason say nothing, and "  " is no reason, as the table's own rule holds.
    reason = reason.strip()
    # One transaction: the locks below hold until the decision is saved. Not a recording_changes block: no laptop keeps
    # a day, so a decision writes no line in the change log (03 §6.6).
    with transaction.atomic():
        # Who may, asked afresh inside the transaction, as set_pay_rate asks: a key taken away a moment ago counts.
        # First, so someone without it sets nothing to work. attendance.manage on the whole shop, as attendance belongs
        # to the whole shop (a funeral closes both sides).
        require(by, Permission.ATTENDANCE_MANAGE, None)
        # The day as the book answers it now, worked out afresh (work_out_days), and only if the book answers it at all:
        # a row it no longer reads, its job's first day moved later past it (PPL-10) or its only tap voided outside the
        # job's days (ATT-11's review), stays in the table as it was (rule 7), but counts for nothing, so a decision on
        # it would be read by nothing; and today, which the book keeps only once it is over (ATT-10). The book locks
        # every job of the shop, in the order of their ids, as each of its runs does, before it reads the taps: so a
        # decision waits a moment for a manager opening the month, and the book for the decision; and both take the
        # jobs, then the days, in one order, so neither ever holds what the other waits for (a deadlock). Worked out
        # afresh too, so the fine below reads the day's first Ingia as it is now, a tap that came late included.
        shop = Shop.objects.get(pk=day.shop_id)
        answered = work_out_days(shop, day.date, day.date)
        if not any(each.pk == day.pk for each in answered):
            raise ValidationError("Only a working day that is over can be decided.", code="day.not_working_day")
        # Then the day, with the light lock: two decisions on it at once take turns here (FOR NO KEY UPDATE, backend
        # rules). The job's lock is the book's, held until the decision is saved.
        day = AttendanceDay.objects.select_for_update(no_key=True).get(pk=day.pk)
        job = StaffMember.objects.get(pk=day.staff_id)
        # Never one's own day (Jack: A, 20 Nov 2026): the manager's days are the owner's to decide, as a person never
        # approves their own, and a manager late at 08:10 would otherwise take his own fine off. By the person, not
        # the job: someone hired again (PPL-11) has two jobs, and neither of their days is theirs to decide.
        if job.user_id == by.user_id:
            raise ValidationError("Nobody decides their own day.", code="day.own")
        # A working day: an off day, a Sunday or a closed day nobody tapped on, is the shop's calendar, never paid
        # (01 §8.1); a closed day with a tap is no off day, as it waits for a decision (ATT-10).
        if day.status == DayStatus.OFF:
            raise ValidationError("Only a working day that is over can be decided.", code="day.not_working_day")
        # The same decision sent again, as a phone does when the network lost the first one's answer: the day holds it
        # already, made by this person, with the same choice and the same reason. Answered as done, writing nothing and
        # no second line in the edit history, never refused below as if someone else had decided it (ATT-6's review).
        status, absence = DECISION_OF[choice]
        if (day.decided_by_id, day.decided_status, day.absence_type, day.decision_reason) == (
            by.pk,
            status,
            absence,
            reason,
        ):
            return day
        # Its pay is approved (WAGE-3, A3): what the day was is final, and the mend is an adjustment in a later month.
        # Under the book's lock, which the approval takes too, so the two never cross. After the answer above, as a
        # decision made before the approval was made all the same.
        refuse_if_closed(shop, day.date, day.staff_id)
        # Two managers on the same day at once: the second decided on a page that showed no decision, or an older one,
        # so theirs would write over a decision they never saw. Refused as an edit on an old copy is (409), so the page
        # reads the day again and shows them what was decided.
        if day.decided_at != replaces:
            raise VersionConflict()
        # The choices this day may take, each with its fine, from the day's own rules (T4): a day sent to review keeps
        # its first Ingia and the rules it read, for this (ATT-10); and none fined when its time is in doubt (Jack: A).
        offered = day_choices(
            day.first_in, rules_from_text(day.rules_used), time_in_doubt=day.review_reason in TIME_IN_DOUBT
        )
        # The boxes, all together, so a person who got two wrong sees both at once, each beside its box (ADR-0040).
        errors: dict[str, list[ValidationError]] = {}
        if choice not in offered:
            # Amechelewa on a day with no Ingia known, or one on time: the sheet doesn't offer it; a request that sends
            # it all the same is refused, never fined by a guess.
            errors["choice"] = [ValidationError("This day can't be decided so.", code="day.choice_not_offered")]
        if not reason:
            errors["reason"] = [ValidationError("A decision says why.", code="day.reason_missing")]
        elif settings.DEMO_SEED and reason not in DEMO_REASONS:
            errors["reason"] = [ValidationError("On the demo, pick a ready reason.", code="demo.ready_reasons")]
        if errors:
            raise ValidationError(errors)
        day.decided_status, day.absence_type = status, absence
        day.decided_fine = offered[choice]
        day.decided_by = by
        day.decided_at = timezone.now()
        day.decision_reason = reason
        # Only the decision's columns: what the book worked out stays exactly as it was (A2). The edit history's
        # trigger keeps the change, and the decision before it, if there was one (ADR-0036).
        day.save(update_fields=DECISION)
    return day


# On the demo, the ready reason a fix to a tap takes, kept as its code, which the page says in words (as DEMO_REASONS,
# Jack: A, 21 Nov 2026): adding a tap the worker forgot, *Alisahau kubonyeza*; crossing out one tapped by mistake,
# *Alibonyeza kwa makosa*. Each fix its own, so neither sheet offers the other's.
DEMO_ADD_REASONS = ("forgot_tap",)
DEMO_VOID_REASONS = ("wrong_tap",)


def add_tap(
    staff: StaffMember,
    *,
    tap_id: uuid.UUID,
    kind: ClockKind,
    date: dt.date,
    minute: dt.time,
    reason: str,
    by: StaffMember,
) -> AttendanceEvent:
    """Add a tap a worker forgot, entered in the office (ATT-13, 02 §12): Juma's Toka at 18:45 on Thursday, "Alisahau
    kubonyeza Toka". A line of the attendance book like a laptop's, with no laptop: `by` entered it (`created_by`), its
    time is `minute` on `date` on the shop's clock, trusted (`entered`), and it has no photo (`entered`). The book reads
    it the next time it works the day out. `tap_id`: the client's (ADR-0007), so the route answers a request sent twice
    with the tap it made (CreateOnceMixin). `by`: who adds it, with attendance.manage on the whole shop, never for
    themselves. Refuses: one's own tap (tap.own); a Sunday, a day outside the job's, or one attendance was off
    (tap.not_working_day); a day whose pay is approved (pay.day_approved); and, all together, each beside its box, a
    minute still to come (tap.in_future), no reason (tap.reason_missing), or on the demo a reason not the ready one
    (demo.ready_reasons). Returns the tap as saved."""
    # A job of another shop adding to this shop's book is a bug in the calling code (T1), never a person's mistake: the
    # route finds the worker and the person in the one shop open. A server error, before anything is read.
    if by.shop_id != staff.shop_id:
        raise ShopMismatch("add_tap was given a person of another shop.")
    # Spaces around a reason say nothing, and "  " is no reason, as the table's own rule holds.
    reason = reason.strip()
    shop = Shop.objects.get(pk=staff.shop_id)
    # One transaction, as the push saves a laptop's tap: recording_changes, whose change line no laptop pulls today,
    # as no device keeps the book (apps/sync/registry.py), and which the push writes for each tap all the same.
    with recording_changes(shop):
        job = _ready_to_fix(staff.pk, by)
        # A day the job works, as the book counts it (02 §5): from its first day to its last, as they are now, and
        # never a Sunday, when the shop is shut and a tap counts nothing (01 §8.1). A closed day takes one: Juma came
        # the morning of a funeral, and the book sends that day to review, as it would a laptop's tap (ATT-10). And a
        # day attendance was switched on, a dated rule read on that day (ADR-0033): the book keeps no day while it is
        # off, so a tap there would be kept and count nothing (ATT-13's review).
        if date.weekday() == SUNDAY or not ran_on(job, date) or not get_setting(ATTENDANCE_ON, shop, on=date):
            raise ValidationError("Only a working day of the job takes a tap.", code="tap.not_working_day")
        # A day already paid, or not, for good (WAGE-3, A3): a tap there would be kept and move nothing. Under the job's
        # lock, one of those the approval takes.
        refuse_if_closed(shop, date, job.pk)
        # A worker suspended or gone takes one too, and it counts (Jack: A, ATT-13's review): a laptop's tap let through
        # while a worker is suspended sends its day to review (X2, the push's flag), as nobody chose it; this one a
        # manager adds on purpose, with their name and why on it, so it counts as their word. Refusing it would also
        # block mending the worker's days from before the suspension.
        # The minute on the shop's clock, made a moment with the shop's zone, here, never the phone's (03 §5.10); its
        # seconds dropped, as the counter shows a minute (shop_minute): 07:35:40 is 07:35, on time.
        moment = dt.datetime.combine(date, minute.replace(second=0, microsecond=0), tzinfo=ZoneInfo(shop.timezone))
        now = timezone.now()
        # The boxes, all together, so a person who got two wrong sees both at once, each beside its box (ADR-0040).
        errors: dict[str, list[ValidationError]] = {}
        # A tap is added once it is true: at 10:05, Juma's Toka of 18:45 hasn't happened yet.
        if moment > now:
            errors["time"] = [ValidationError("A tap is added once it has happened.", code="tap.in_future")]
        if not reason:
            errors["reason"] = [ValidationError("A tap added says why.", code="tap.reason_missing")]
        elif settings.DEMO_SEED and reason not in DEMO_ADD_REASONS:
            errors["reason"] = [ValidationError("On the demo, pick the ready reason.", code="demo.ready_reasons")]
        if errors:
            raise ValidationError(errors)
        tap = AttendanceEvent(
            id=tap_id,
            shop=shop,
            # When it was entered, the server's clock, as a laptop's tap keeps when its push arrived. A day decided
            # before this moment says its taps changed since (ATT-13).
            received_at=now,
            created_by=by,
            staff=job,
            kind=kind,
            trusted_time=moment,
            time_check=TimeCheck.ENTERED,
            no_photo=NoPhoto.ENTERED,
            entry_reason=reason,
        )
        # An INSERT, never an UPDATE, as the push saves a laptop's: an id another row holds clashes on the primary key,
        # loudly, and never overwrites it (03 §5.4).
        tap.save(force_insert=True)
        record_change(tap)
    return tap


def void_tap(tap: AttendanceEvent, *, reason: str, by: StaffMember) -> AttendanceEvent:
    """Cross out a tap made by mistake (ATT-13, 02 §12, T2): Juma's Toka at 10:00, "Alibonyeza kwa makosa". The tap
    stays in the book, voided once with who, when and why, and counts for nothing; the page shows it struck through
    (A2). Never brought back: a mistake is mended by adding a tap (add_tap). An added tap is crossed out like any other.
    `by`: who crosses it out, with attendance.manage on the whole shop, never on their own tap. A tap crossed out
    already, by this request sent twice or by someone a moment before, is answered as it was crossed out, never stamped
    again (CORE-3's Watch out). Refuses: one's own tap (tap.own); a tap of a day whose pay is approved
    (pay.day_approved); no reason (tap.reason_missing), or on the demo a reason not the ready one (demo.ready_reasons),
    beside the reason's box. Returns the tap as saved."""
    # Who voids is a staff member of the tap's own shop (T1): the void rule in the database checks only that the stamp
    # is filled whole, so this is the check it can't make with one column (v1.58). Another shop's person here is a bug
    # in the calling code, as the route finds both in the one shop open: a server error, before anything is read.
    if by.shop_id != tap.shop_id:
        raise ShopMismatch("void_tap was given a person of another shop.")
    reason = reason.strip()
    with recording_changes(tap.shop_id):
        _ready_to_fix(tap.staff_id, by)
        # Read afresh under the lock: one crossed out already is answered as it is, whatever was approved since.
        tap = AttendanceEvent.objects.get(pk=tap.pk)
        if tap.voided_at is None:
            # The tap's day, as the book places it (WAGE-3, A3): one paid for good takes no fix.
            shop = Shop.objects.get(pk=tap.shop_id)
            day, _ = where_it_falls(tap.trusted_time, tap.client_time, ZoneInfo(shop.timezone))
            refuse_if_closed(shop, day, tap.staff_id)
        if not reason:
            raise ValidationError(
                {"reason": [ValidationError("A tap crossed out says why.", code="tap.reason_missing")]}
            )
        if settings.DEMO_SEED and reason not in DEMO_VOID_REASONS:
            raise ValidationError(
                {"reason": [ValidationError("On the demo, pick the ready reason.", code="demo.ready_reasons")]}
            )
        # The stamp, filled once, by one guarded UPDATE (CORE-3's Watch out): only while the tap is not crossed out, so
        # two voids never both write it, whatever their order. Never save(), which AppendOnly refuses; the void trigger
        # lets this UPDATE change the stamp and nothing else (ADR-0021).
        stamped = AttendanceEvent.objects.filter(pk=tap.pk, voided_at__isnull=True).update(
            voided_at=timezone.now(), voided_by=by, void_reason=reason
        )
        # Read back as it is now: crossed out by this request, or, when no row was stamped, by the same request sent
        # before, its answer lost, or by someone a moment before, whose void the page is then shown (03 §5.5).
        tap = AttendanceEvent.objects.get(pk=tap.pk)
        if stamped:
            record_change(tap)
    return tap


def _ready_to_fix(staff_id: uuid.UUID, by: StaffMember) -> StaffMember:
    # The checks every fix to a tap starts with, inside its transaction (ATT-13). Who may, asked afresh, as decide_day
    # asks: a key taken away a moment ago counts, and someone without it sets nothing to work. attendance.manage on the
    # whole shop, as attendance belongs to the whole shop.
    require(by, Permission.ATTENDANCE_MANAGE, None)
    # Then the job, locked as the book locks every job of the shop while it works the days out (work_out_days): a fix,
    # a run of the book and a decision take turns, so the book never keeps a day from the taps as they were a moment
    # before a fix, and a decision made meanwhile is either seen by the fix or sees it. One job, so no other job's lock
    # is waited for while it is held, and no two runs each hold what the other waits for (a deadlock); the one lock
    # taken after it is the shop's change numbers, at the block's end, which no run of the book or decision holds.
    # FOR NO KEY UPDATE, the light lock (backend rules): a laptop's tap pushed meanwhile still saves. Read afresh with
    # it, as its first and last day may have just moved (PPL-10).
    job = StaffMember.objects.select_for_update(no_key=True).get(pk=staff_id)
    # Never one's own taps (as ATT-6's day.own): a manager who came late would otherwise add himself an Ingia on time.
    # By the person, not the job: someone hired again (PPL-11) has two jobs, and neither's taps are theirs to fix.
    if job.user_id == by.user_id:
        raise ValidationError("Nobody fixes their own taps.", code="tap.own")
    return job
