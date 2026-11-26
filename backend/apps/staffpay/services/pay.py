"""apps/staffpay/services/pay.py — the month's pay: a draft, worked out from the days, the rates, the meals and the
advances (WAGE-2), until the month is approved (WAGE-3), and from then on read from its payslips.

    pay_month(MPC, November), open       worked out now: Asha 152,000, Juma 132,000, and what stops the approval
    pay_month(MPC, November), approved   as it was kept: Asha 152,000, Juma 132,000, approved by Baba, 1/12 19:05

The month's pay is asked for by Mishahara (pay_month) and by one worker's page (worker_pay): the book's days (book.py),
each at its own rate, added up by the sum (work_out_pay, apps/staffpay/calculations.py). The draft is never saved (Jack,
WAGE-2): a saved one is old as soon as a day is decided, so it is worked out each time, through the book, as the month's
page is. And today, still running, is added once the worker taps Toka, less their share of today's meals so far, so one
who leaves tonight is paid for it (Jack: A): judged by the book's own rule (answer_days), and never kept.

Once a month is approved, its payslips are the answer (Payslip, PayslipLine), and nothing is worked out: November says
the same a year later (A3). Each payslip comes with how it was handed out (PayslipPayment, WAGE-9), crossed out ones
too, and the month with what is still to hand out, Bado kulipa:

    pay_month(MPC, November), approved, 2 Dec   Asha 152,000 paid in cash by Baba · Juma 132,000 not paid yet
                                                Bado kulipa 132,000

A debt a payslip left, a total below 0, comes off the job's next pay, as a line of its own (Jack: A). Approving is
approval.py's, which keeps exactly what this file answers; so is what stops it (ToApprove), as the page that shows the
pay shows that too.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import cached_property
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.db.models import Min

from apps.control.models import ATTACHMENT_KINDS, Attachment, AttachmentKind
from apps.core.settings_registry import ATTENDANCE_ON, ROUNDING_STEP
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import StaffMember, StaffStatus
from apps.shops.models import Setting, Shop
from apps.shops.selectors import shop_settings_between, shop_today
from apps.staffpay.calculations import (
    CAME,
    NO_PAY,
    DayToPay,
    PaidAs,
    Pay,
    PayLine,
    add_up,
    cash_to_pay,
    debt_left,
    meal_share,
    pay_day,
    work_out_pay,
)
from apps.staffpay.models import (
    Advance,
    AttendanceDay,
    DayStatus,
    PayRate,
    PayRun,
    Payslip,
    PayslipLine,
    PayslipLineKind,
    PayslipPayment,
    ReviewReason,
)
from apps.staffpay.selectors import (
    QuietLaptop,
    advances_between,
    is_closed,
    meal_money_by_date,
    quiet_laptops,
    rates_between,
)
from apps.staffpay.services.book import answer_days, month_span, who_shares, work_out_days
from apps.staffpay.services.money import NO_MONEY
from apps.staffpay.services.payment import ready_payment_void_reasons


@dataclass(frozen=True)
class Approval:
    # Who approved a month's pay, or one worker's alone, by nickname, and when: "Imeidhinishwa na Baba · 1/12/2026
    # 19:05".
    by: str
    at: dt.datetime


@dataclass(frozen=True)
class VoidedPayment:
    # Who crossed out a payment, by nickname; when; and why. On the demo the reason is a ready one's code
    # (`marked_by_mistake`), which the page says in words.
    by: str
    at: dt.datetime
    reason: str


@dataclass(frozen=True)
class PaymentLine:
    # One handing-out of a payslip (WAGE-9), as the payslip's foot shows it: "Amelipwa taslimu na Baba · 2/12/2026
    # 08:10", the M-Pesa number, the amount, the signature's photo, or why there is none (on the demo), and who crossed
    # it out, or None while it counts.
    id: uuid.UUID
    method: str
    reference: str
    amount: Decimal
    by: str
    at: dt.datetime
    signature_id: uuid.UUID | None
    no_signature: str
    voided: VoidedPayment | None


@dataclass(frozen=True)
class WorkerPay:
    # One worker's pay of a month (WAGE-2), a job's, as a day is a job's: a person hired again in the month has two,
    # each with its own days and rates (PPL-11). Whose, and their last day if they left, which the page says beside
    # their name; the sum of the days that are over, line by line, less what they were given before payday (WAGE-8) and
    # what an earlier month left owed; today alone, once they tapped Toka, or None (Leo, Jack: A); and what is left to
    # pay, the two together.
    staff_id: uuid.UUID
    display_name: str
    left_on: dt.date | None
    pay: Pay
    today: Pay | None
    total: Decimal
    # The month the debt is from, as its first day, when there is one: "Deni la Novemba" (WAGE-3).
    carried_from: dt.date | None = None
    # Who approved it and when, once a payslip keeps it (WAGE-3), with its month or alone; None while it is a draft.
    approval: Approval | None = None
    # The days that stop its approval: those that wait for a decision, and those to pay with no rate. None on a payslip.
    waiting_on: tuple[dt.date, ...] = ()
    no_rate_on: tuple[dt.date, ...] = ()
    # Once a payslip keeps it: the payslip, which Lipa pays, and each time it was handed out, in the order made, those
    # crossed out among them (WAGE-9). None and nothing on a draft.
    payslip_id: uuid.UUID | None = None
    payments: tuple[PaymentLine, ...] = ()

    @property
    def payment(self) -> PaymentLine | None:
        # The payment that counts, or None: at most one, as the table holds.
        return next((made for made in self.payments if made.voided is None), None)

    @property
    def to_hand_out(self) -> Decimal:
        # What is still to hand this worker for a kept payslip (Bado kulipa): all it pays, until it is paid; nothing
        # once it is, nor for a payslip of 0, which has nothing to hand over (WAGE-9), nor for a draft, not yet kept.
        if self.payslip_id is None or self.payment is not None:
            return NO_PAY
        return cash_to_pay(self.total)


@dataclass(frozen=True)
class OpenDay:
    # A day that stops the approval, as the sheet names it: "Juma · Alhamisi 12/11".
    staff_id: uuid.UUID
    display_name: str
    date: dt.date


@dataclass(frozen=True)
class ToApprove:
    # What the approval of a month that is over waits for, and what it warns of (WAGE-3). Waits: an earlier month with
    # pay still open, as months are approved in order, or a debt would be lost; the days that wait for a decision
    # (Jack: A); and the days to pay with no rate. Warns, and stops nothing: the laptops that have sent nothing since
    # the month ended (Jack: A), whose taps may be missing; and who came to work without any daily pay in the month, by
    # nickname, as they are on no payslip. The same for one worker's approval alone, of what is theirs: which also waits
    # for their Toka, on their last evening, or today would be left out of their pay.
    earlier: dt.date | None
    waiting: list[OpenDay]
    no_rate: list[OpenDay]
    quiet_laptops: list[QuietLaptop]
    came_unpaid: list[str]
    still_clocked_in: bool = False


@dataclass(frozen=True)
class PayMonth:
    # Mishahara's answer (WAGE-2): the month, as its first day; the shop's today; the last day counted, or None when no
    # day of the month is over; a line per worker paid by the day, or given money before payday in it (WAGE-8), by name;
    # the whole of it, each who owes as 0 (cash_to_pay); and the jobs with a working day in it, over or today's, which
    # says whether there is anything to pay yet.
    month: dt.date
    today: dt.date
    counted_to: dt.date | None
    workers: list[WorkerPay]
    total: Decimal
    worked: frozenset[uuid.UUID]
    # Who approved the month and when (WAGE-3), or None while it is open; and, once it is over and open with someone to
    # pay, what its approval waits for.
    approval: Approval | None = None
    to_approve: ToApprove | None = None
    # Once the month is approved: the cash still to hand out, each payslip not paid yet (Bado kulipa, WAGE-9), 0 once
    # each is (Wote wamelipwa); None while it is open, as its payslips aren't all kept yet.
    still_to_pay: Decimal | None = None

    @property
    def is_running(self) -> bool:
        # Whether it is this month, by the shop's own today.
        return self.month == self.today.replace(day=1)

    @property
    def no_day_yet(self) -> bool:
        # No working day of the month yet, not even today's: on a 1st that is a Sunday or a closed day. Whoever isn't
        # listed then isn't for want of a day, not of a rate, so "Hakuna mfanyakazi anayelipwa kwa siku" would be untrue
        # (WAGE-2's review, as ATT-5's on the attendance month). Listed then is only who was given money (WAGE-8).
        return self.is_running and not self.worked


@dataclass(frozen=True)
class WorkerPayMonth:
    # One worker's pay of a month, as their page shows it: their line of Mishahara, with its month and its days; and,
    # for the page to say why there is nothing, whether there is a line of theirs, as the shop pays them by the day in
    # it or gave them money in it (WAGE-8), and whether their first working day of it is still to come: on a 1st that is
    # a Sunday, or hired from the 28th and looked at on the 25th.
    month: dt.date
    today: dt.date
    counted_to: dt.date | None
    paid_by_day: bool
    no_day_yet: bool
    worker: WorkerPay
    # For one who left, with pay still open: what their approval alone waits for (WAGE-3), or None, when there is
    # nothing to approve alone.
    to_approve: ToApprove | None = None
    # The ready reasons a payment may be crossed out with, on the demo alone; empty where the reason is typed (WAGE-9).
    void_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class MonthsParts:
    # What a month's draft is worked out from, each part read once, after the book worked its days out: each job's days
    # that are over, in their order; today's, by job, while the month runs; the rates and the settings on each day; what
    # each was given before payday; the payslips already kept, of those approved alone; and who has a line. The approval
    # keeps a month from the very parts the page showed it from (approval.py), read inside its lock.
    shop: Shop
    first: dt.date
    last: dt.date
    today: dt.date
    over: dict[uuid.UUID, list[AttendanceDay]]
    todays: dict[uuid.UUID, AttendanceDay]
    rates: dict[tuple[uuid.UUID, dt.date], PayRate]
    settings_by_day: dict[dt.date, dict[str, Any]]
    advances: dict[uuid.UUID, Decimal]
    kept: dict[uuid.UUID, WorkerPay]
    workers: dict[uuid.UUID, StaffMember]
    worked: frozenset[uuid.UUID]

    @property
    def open_jobs(self) -> set[uuid.UUID]:
        # The jobs with pay of this month that no payslip keeps yet.
        return self.workers.keys() - self.kept.keys()

    @cached_property
    def open_before(self) -> dict[uuid.UUID, dt.date]:
        # Each job with pay still open in an earlier month (open_before, below). Once for all that ask, as each month is
        # read for it: a debt waits for them, and so does the approval.
        return open_before(self.shop, self.first)

    def tonight(self, job: uuid.UUID) -> AttendanceDay | None:
        # Today's day of a job once it counts: when a Toka has ended it (first_out, ATT-4). Until then it is still
        # theirs to work, and the rule would send it to a person for want of one. A Toka the rule can't judge, at 16:00,
        # ended it too, and waits. And a day with a tap whose time nobody trusts, as the laptop's clock moved: a Toka
        # among them has no minute, so it ends nothing the rule can read, and whatever is tapped after, the day waits.
        # Said tonight: one who leaves with it unsaid would be paid without today, and nobody would know (WAGE-2's
        # review).
        today = self.todays.get(job)
        if today is None or (today.first_out is None and today.review_reason != ReviewReason.TIME_UNKNOWN):
            return None
        return today

    def days_to_pay(self, job: uuid.UUID, days: Iterable[AttendanceDay]) -> list[DayToPay]:
        # Some days of one job as the sum reads them, each with its own rate and step.
        return [
            _to_pay(day, self.rates.get((job, day.date)), self.settings_by_day[day.date][ROUNDING_STEP.key])
            for day in days
        ]


def pay_month(shop: Shop, month: dt.date) -> PayMonth:
    """The pay of the month of `month`, any day of it, as Mishahara shows it (WAGE-2; spec §8.1, 02 §15, 8), for
    everyone the shop pays by the day, or gave money before payday in it (WAGE-8). Approved, as its payslips keep it
    (WAGE-3). Open: each worker's days that are over, each at its own rate, added up line by line, less what they were
    given and what an earlier month left owed; today, for whoever has tapped Toka; those approved alone as their payslip
    keeps them; the whole; and, once the month is over, what its approval waits for. Worked out through the book
    (work_out_days), so it writes as the book does, and asked twice writes nothing the second time; the draft itself is
    never kept. The shop must be open, as for the book."""
    answer, parts = _month(shop, month)
    if parts is None or parts.today <= parts.last or not answer.workers or is_closed(shop, parts.first):
        # Approved, to come, still running, nobody to pay, or before an approved month: nothing to approve.
        return answer
    return replace(answer, to_approve=what_stops(shop, parts, answer))


def _month(shop: Shop, month: dt.date) -> tuple[PayMonth, MonthsParts | None]:
    # A month's pay, and the parts it was worked out from, which an approved month and one to come don't have.
    _check_asked(shop, month)
    first, last = month_span(month)
    # The shop's today, read once: the pay counts up to the day before it, and today apart, whatever the clock does
    # meanwhile. The book reads its own a moment later, and at midnight answers one day more, which for this answer is
    # still today: only the days before it, or it would be paid twice.
    today = shop_today(shop)
    run = run_of(shop, first)
    if run is not None:
        return _approved(shop, run, last, today), None
    if today < first:
        # A month to come: nothing of it is worked yet, and nothing more is read. So the calendar's last month is an
        # answer too, never a day past the last one Python knows (ATT-5's review).
        return PayMonth(month=first, today=today, counted_to=None, workers=[], total=NO_PAY, worked=frozenset()), None
    parts = read_parts(shop, first, last, today)
    return draft_of(shop, parts), parts


def worker_pay(shop: Shop, job: StaffMember, month: dt.date) -> WorkerPayMonth:
    """One job's pay of the month of `month`, any day of it (WAGE-2): the very line Mishahara shows of them (pay_month),
    so the two pages never say two totals. A worker the shop neither pays by the day in it nor gave money in it has
    nothing, and the answer says so. One who left, with pay still open, comes with what their approval alone waits for
    (WAGE-3). The shop must be open, and the job one of it."""
    # The route finds the job through the guard, so another shop's never comes here; but a service checks what it is
    # given (T1), so a bug that passed one fails loudly.
    if job.shop_id != shop.pk:
        raise ShopMismatch("worker_pay was given a job of another shop.")
    whole, parts = _month(shop, month)
    line = next((line for line in whole.workers if line.staff_id == job.pk), None)
    alone = (
        what_stops_alone(shop, parts, line)
        if parts is not None
        and line is not None
        and line.approval is None
        and job.status == StaffStatus.LEFT
        and not is_closed(shop, parts.first, job.pk)
        else None
    )
    return WorkerPayMonth(
        month=whole.month,
        today=whole.today,
        counted_to=whole.counted_to,
        paid_by_day=line is not None,
        # Not one who left, whose last day may be in a month before: nothing of theirs is to come.
        no_day_yet=whole.is_running and job.left_on is None and job.pk not in whole.worked,
        worker=_worker_pay(job, work_out_pay([]), None) if line is None else line,
        to_approve=alone,
        void_reasons=tuple(ready_payment_void_reasons()),
    )


def run_of(shop: Shop, month: dt.date) -> PayRun | None:
    """The approval of a month, by its first day, with who gave it, or None while the month is open (WAGE-3)."""
    return PayRun.objects.select_related("created_by").filter(shop=shop, month=month).first()


def read_parts(shop: Shop, first: dt.date, last: dt.date, today: dt.date) -> MonthsParts:
    """What the draft of a month begun by `today` is worked out from: the book's days first (work_out_days), then each
    other part once. For the approval, inside the book's lock, which it takes first (approve_month): then no part can
    change until it commits, as whatever would change one waits for the lock (WAGE-3). Elsewhere the book lets its lock
    go before the rest is read, so a first rate typed between the two lists Juma once with no meals taken, while Asha
    still carries his share, until the page asks again, as Hela ya chakula's does (_meal_day)."""
    days = [day for day in work_out_days(shop, first, last) if day.date < today]
    # Each job's rate on each day, a raise splitting the month at its own day (WAGE-1); the step half a day, and a share
    # of the meals, is rounded to on each day (A1), and the attendance switch, for today. One read each for the month.
    rates = rates_between(shop, first, last)
    settings_by_day = shop_settings_between([ATTENDANCE_ON, ROUNDING_STEP], shop, first, last)
    # Today's days, when the month is still running: by the job, as each has one.
    todays = {day.staff_id: day for day in _todays_days(shop, today, rates, settings_by_day)} if today <= last else {}
    # Who the shop pays by the day: a job with a rate on a working day of the month the book answers, the month page's
    # rule (attendance_month), or today. So not Baba, who has none; nor Neema, whose rate goes on after she left in
    # October; nor one whose only days of the month are Sundays. And on the 1st, when no day is over, everyone who works
    # today.
    working = [day for day in [*days, *todays.values()] if day.status != DayStatus.OFF]
    workers = {day.staff_id: day.staff for day in working if (day.staff_id, day.date) in rates}
    # What each was given before payday in the month, by its own days, today's with them: the money was given, whatever
    # of today is worked yet (WAGE-8). None is of a day to come, so the whole month is asked for. Read after the book,
    # as the rates are, so one typed between the two is in this answer, and one typed after it in the next.
    advances = advances_between(shop, first, last)
    # Those approved alone, the evening they left: their payslip is their line, whatever is worked out beside it.
    kept = _payslips_of(shop, first)
    # A worker given money is listed for it, though no working day of theirs has come, as on a 1st that is a Sunday, or
    # their rate starts later: or the money would be on nobody's pay until then. And one whose payslip is kept is listed
    # for it, though the book may no longer answer a day of theirs.
    unlisted = (advances.keys() | kept.keys()) - workers.keys()
    if unlisted:
        workers |= {staff.pk: staff for staff in StaffMember.objects.filter(shop=shop, pk__in=unlisted)}
    # The book answers date by date, so each worker's days come in their order, and so do the lines of their pay.
    over: dict[uuid.UUID, list[AttendanceDay]] = defaultdict(list)
    for day in days:
        over[day.staff_id].append(day)
    return MonthsParts(
        shop=shop,
        first=first,
        last=last,
        today=today,
        over=over,
        todays=todays,
        rates=rates,
        settings_by_day=settings_by_day,
        advances=advances,
        kept=kept,
        workers=workers,
        worked=frozenset(day.staff_id for day in working),
    )


def draft_of(shop: Shop, parts: MonthsParts) -> PayMonth:
    """A month's pay as it stands, from its parts: a line per worker, by name, and the whole. With nothing of its
    approval: pay_month adds what it waits for, and the approval asks it for itself."""
    debts = _debts(shop, parts)
    lines = []
    for job, staff in parts.workers.items():
        if job in parts.kept:
            # Approved alone: as it was kept, never worked out again (A3).
            lines.append(parts.kept[job])
            continue
        # Today, once it counts (Leo, Jack: A).
        tonight = parts.tonight(job)
        carried_from, carried = debts.get(job, (None, NO_PAY))
        # The advances and the debt come off the days that are over, never off today's part too, or they would be taken
        # twice.
        days = parts.days_to_pay(job, parts.over.get(job, []))
        pay = work_out_pay(days, advances=parts.advances.get(job, NO_PAY), carried=carried)
        today = None if tonight is None else work_out_pay(parts.days_to_pay(job, [tonight]))
        paid = [(day.date, pay_day(to_pay)) for day, to_pay in zip(parts.over.get(job, []), days, strict=True)]
        lines.append(
            replace(
                _worker_pay(staff, pay, today),
                carried_from=carried_from,
                waiting_on=tuple(date for date, each in paid if each.paid_as is PaidAs.WAITS),
                no_rate_on=tuple(date for date, each in paid if each.no_rate),
            )
        )
    # By name, as the month page lists them; "asha" beside "Asha"; then the job's id, so two jobs of one name always
    # come in the same order, the one had first before the other (UUIDv7).
    lines.sort(key=lambda line: (line.display_name.casefold(), line.staff_id))
    return PayMonth(
        month=parts.first,
        today=parts.today,
        # Up to yesterday, or the end of a month gone by; none on the 1st.
        counted_to=min(parts.last, parts.today - dt.timedelta(days=1)) if parts.first < parts.today else None,
        workers=lines,
        total=_cash(lines),
        worked=parts.worked,
    )


def what_stops(shop: Shop, parts: MonthsParts, draft: PayMonth) -> ToApprove:
    """What the approval of a month waits for, and what it warns of (WAGE-3), from the parts its draft was worked out
    from. Asked by the page, to say it before the tap, and by the approval itself, which refuses by it."""
    open_lines = [line for line in draft.workers if line.approval is None]
    return ToApprove(
        earlier=min(parts.open_before.values(), default=None),
        waiting=_by_date((line, day) for line in open_lines for day in line.waiting_on),
        no_rate=_by_date((line, day) for line in open_lines for day in line.no_rate_on),
        quiet_laptops=quiet_laptops(shop, _midnight(shop, parts.last + dt.timedelta(days=1))),
        # Came, by the decision where there is one, or waits for someone to say so, with no line of the month: no rate
        # on any working day of it, and no money given. Not the owner, who never clocks in.
        came_unpaid=sorted(
            {
                day.staff.display_name
                for job, days in parts.over.items()
                if job not in parts.workers
                for day in days
                if (day.decided_status or day.status) in (*CAME, DayStatus.NEEDS_REVIEW)
            },
            key=str.casefold,
        ),
    )


def what_stops_alone(shop: Shop, parts: MonthsParts, line: WorkerPay) -> ToApprove:
    """What the approval of one worker's pay alone waits for, and what it warns of (WAGE-3): of their own days and their
    own earlier months alone, as whoever else's day waits is no reason to keep one who left from their pay. And, on
    their last evening, for their Toka: clocked in with none, today isn't counted yet."""
    job = line.staff_id
    tonight = parts.todays.get(job)
    # Today, when it counts and the rule can't judge it, waits as any other day, and can be decided once it is over.
    waits = (parts.today,) if line.today is not None and line.today.waiting else ()
    no_rate = (parts.today,) if line.today is not None and line.today.no_rate else ()
    # Their last day, or the month's, was over at the midnight after it; one who leaves tonight is asked of since this
    # morning.
    since = min((line.left_on or parts.last) + dt.timedelta(days=1), parts.last + dt.timedelta(days=1), parts.today)
    return ToApprove(
        earlier=parts.open_before.get(job),
        waiting=_by_date((line, day) for day in (*line.waiting_on, *waits)),
        no_rate=_by_date((line, day) for day in (*line.no_rate_on, *no_rate)),
        quiet_laptops=quiet_laptops(shop, _midnight(shop, since)),
        came_unpaid=[],
        still_clocked_in=tonight is not None
        and tonight.status == DayStatus.NEEDS_REVIEW
        and parts.tonight(job) is None,
    )


def _midnight(shop: Shop, day: dt.date) -> dt.datetime:
    # The midnight a day starts at, on the shop's own clock (02 §1).
    return dt.datetime.combine(day, dt.time.min, tzinfo=ZoneInfo(shop.timezone))


def _by_date(days: Iterable[tuple[WorkerPay, dt.date]]) -> list[OpenDay]:
    # Days that stop an approval, the oldest first, as it has waited longest; on one date by name, as the lines are.
    return sorted(
        (OpenDay(line.staff_id, line.display_name, day) for line, day in days),
        key=lambda day: (day.date, day.display_name.casefold(), day.staff_id),
    )


def open_before(shop: Shop, month: dt.date) -> dict[uuid.UUID, dt.date]:
    """Each job with pay still open in a month before `month`, by the first such month (WAGE-3). None once every month
    before it is approved. Only the months since the last approval are asked for: a month is approved only once nothing
    before it is open, and from then on every day up to its end is closed (selectors.is_closed)."""
    found: dict[uuid.UUID, dt.date] = {}
    first = _first_month_to_ask(shop, month)
    while first is not None and first < month:
        _, last = month_span(first)
        for job in read_parts(shop, first, last, shop_today(shop)).open_jobs:
            found.setdefault(job, first)
        first = last + dt.timedelta(days=1)
    return found


def _first_month_to_ask(shop: Shop, month: dt.date) -> dt.date | None:
    # The month after the last one approved before `month`; or, with none approved yet, the first month that could hold
    # any pay: from when attendance was on and someone had a rate, or the first money was given. None when nothing
    # could.
    run = PayRun.objects.filter(shop=shop, month__lt=month).order_by("-month").first()
    if run is not None:
        return month_span(run.month)[1] + dt.timedelta(days=1)
    switched_on = Setting.objects.filter(
        shop=shop, key=ATTENDANCE_ON.key, value=ATTENDANCE_ON.kind.to_text(True)
    ).aggregate(day=Min("effective_from"))["day"]
    rated = PayRate.objects.filter(shop=shop).aggregate(day=Min("effective_from"))["day"]
    given = Advance.objects.filter(shop=shop, voided_at__isnull=True).aggregate(day=Min("date"))["day"]
    worked_from = max(switched_on, rated) if switched_on is not None and rated is not None else None
    days = [day for day in (worked_from, given) if day is not None]
    return min(days).replace(day=1) if days else None


def _debts(shop: Shop, parts: MonthsParts) -> dict[uuid.UUID, tuple[dt.date, Decimal]]:
    # What each job with a line owes from an earlier month (Jack: A): the latest payslip of the job before this month,
    # when its total is below 0, with its month. The latest alone, as a debt it didn't cover is in its own total. Not
    # while a month between the two holds the job's pay still open: the debt comes off that one first, and whether
    # anything of it is left nobody knows until it is approved, so this month's draft takes none, rather than take it
    # twice.
    latest = (
        Payslip.objects.filter(shop=shop, staff_id__in=parts.open_jobs, month__lt=parts.first)
        # One row per job, its newest, by PostgreSQL's DISTINCT ON.
        .order_by("staff_id", "-month")
        .distinct("staff_id")
        .values_list("staff_id", "month", "total")
    )
    owed = {job: (month, debt_left(total)) for job, month, total in latest if total < 0}
    if not owed:
        # Nearly always: nothing more is read.
        return owed
    return {job: debt for job, debt in owed.items() if job not in parts.open_before}


def _approved(shop: Shop, run: PayRun, last: dt.date, today: dt.date) -> PayMonth:
    # An approved month, from its payslips alone, those approved alone before it among them: nothing is worked out, and
    # the book isn't asked (A3).
    lines = sorted(
        _payslips_of(shop, run.month).values(), key=lambda line: (line.display_name.casefold(), line.staff_id)
    )
    return PayMonth(
        month=run.month,
        today=today,
        counted_to=last,
        workers=lines,
        total=_cash(lines),
        worked=frozenset(line.staff_id for line in lines),
        approval=_approval_of(run),
        still_to_pay=add_up(line.to_hand_out for line in lines),
    )


def _payslips_of(shop: Shop, month: dt.date) -> dict[uuid.UUID, WorkerPay]:
    # Each payslip of a month as its worker's line, by job, with how it was handed out (WAGE-9): in four reads at most,
    # whatever their number.
    slips = list(Payslip.objects.filter(shop=shop, month=month).select_related("staff", "created_by"))
    if not slips:
        return {}
    lines: dict[uuid.UUID, list[PayslipLine]] = defaultdict(list)
    for line in PayslipLine.objects.filter(shop=shop, payslip__in=slips).order_by("payslip_id", "position"):
        lines[line.payslip_id].append(line)
    paid = _payments_of(shop, slips)
    return {slip.staff_id: _line_of(slip, lines[slip.pk], paid.get(slip.pk, ())) for slip in slips}


def _payments_of(shop: Shop, slips: list[Payslip]) -> dict[uuid.UUID, tuple[PaymentLine, ...]]:
    # Each payslip's payments, in the order made, crossed out ones too, which the page shows struck through; and the
    # signature pinned to each one in cash. In two reads, the second only when any was handed out.
    made = list(
        PayslipPayment.objects.filter(shop=shop, payslip__in=slips)
        .select_related("created_by", "voided_by")
        .order_by("created_at", "pk")
    )
    if not made:
        return {}
    signed = dict(
        Attachment.objects.filter(
            shop=shop,
            kind=AttachmentKind.SIGNATURE,
            subject_type=ATTACHMENT_KINDS[AttachmentKind.SIGNATURE].subject_type,
            subject_id__in=[payment.pk for payment in made],
        ).values_list("subject_id", "pk")
    )
    by_slip: dict[uuid.UUID, list[PaymentLine]] = defaultdict(list)
    for payment in made:
        by_slip[payment.payslip_id].append(_payment_line(payment, signed.get(payment.pk)))
    return {slip: tuple(payments) for slip, payments in by_slip.items()}


def _payment_line(payment: PayslipPayment, signature: uuid.UUID | None) -> PaymentLine:
    # A payment as the page shows it. Always somebody's, as the table holds; and a crossing out always says who and why.
    voided = (
        None
        if payment.voided_at is None
        else VoidedPayment(
            by=cast(StaffMember, payment.voided_by).display_name, at=payment.voided_at, reason=payment.void_reason
        )
    )
    return PaymentLine(
        id=payment.pk,
        method=payment.method,
        reference=payment.reference,
        amount=payment.amount,
        by=cast(StaffMember, payment.created_by).display_name,
        at=payment.created_at,
        signature_id=signature,
        no_signature=payment.no_signature,
        voided=voided,
    )


def _line_of(slip: Payslip, lines: list[PayslipLine], payments: tuple[PaymentLine, ...]) -> WorkerPay:
    # A payslip as the same line its draft was, so the page draws one thing: each amount as it was kept, nothing
    # multiplied or rounded again.
    def off(*kinds: PayslipLineKind) -> Decimal:
        # What lines of a kind take off, as the draft says it: above 0. copy_negate, as a minus rounds to the digits the
        # thread keeps.
        return add_up(line.amount.copy_negate() for line in lines if line.kind in kinds)

    def days(kind: PayslipLineKind) -> int:
        return sum(line.days or 0 for line in lines if line.kind == kind)

    carried_from = next((line.date for line in lines if line.kind == PayslipLineKind.CARRIED), None)
    pay = Pay(
        lines=tuple(
            # The table holds both on such a line, so each is there.
            PayLine(PaidAs(line.kind), cast(int, line.days), cast(Decimal, line.each), line.amount)
            for line in lines
            if line.kind in (PayslipLineKind.FULL, PayslipLineKind.HALF)
        ),
        fined_days=days(PayslipLineKind.FINES),
        fines=off(PayslipLineKind.FINES),
        meal_days=days(PayslipLineKind.MEALS),
        meals=off(PayslipLineKind.MEALS),
        advances=off(PayslipLineKind.ADVANCE),
        carried=off(PayslipLineKind.CARRIED),
        # Nothing waits on a payslip: the approval refuses a day that does.
        waiting=0,
        no_rate=0,
        total=slip.total,
    )
    return WorkerPay(
        staff_id=slip.staff_id,
        # Their nickname and last day as they are now: the page names the worker, and the payslip holds what was paid.
        display_name=slip.staff.display_name,
        left_on=slip.staff.left_on,
        pay=pay,
        today=None,
        total=slip.total,
        carried_from=carried_from,
        approval=_approval_of(slip),
        payslip_id=slip.pk,
        payments=payments,
    )


def _approval_of(row: PayRun | Payslip) -> Approval:
    # Who approved a row and when. Always somebody, as both tables hold.
    return Approval(by=cast(StaffMember, row.created_by).display_name, at=row.created_at)


def _cash(lines: Iterable[WorkerPay]) -> Decimal:
    # What the month pays in all (WAGE-3, Jack: A): one who owes is handed nothing, so they count as 0. Their minus
    # would make the whole less than what the others are owed, and Baba would come short at the counter. One approved
    # alone counts too, though they were paid the evening they left: what is still to hand over is Bado kulipa
    # (still_to_pay, WAGE-9).
    return add_up(cash_to_pay(line.total) for line in lines)


def _check_asked(shop: Shop, month: dt.date) -> None:
    # The same checks as the book's, for the same reasons (ADR-0022), as an approved month never asks the book: inside
    # another shop's visit, the guard would hide every payslip, and the month would be empty without a word; and a
    # datetime is a moment, not the shop's day.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("The month's pay was asked of a shop that is not the one open.")
    if isinstance(month, dt.datetime):
        raise TypeError("The month's pay needs the shop's business dates, not a datetime.")


def _worker_pay(staff: StaffMember, pay: Pay, today: Pay | None) -> WorkerPay:
    return WorkerPay(
        staff_id=staff.pk,
        display_name=staff.display_name,
        left_on=staff.left_on,
        pay=pay,
        today=today,
        total=add_up(part.total for part in (pay, today) if part is not None),
    )


def _todays_days(
    shop: Shop,
    today: dt.date,
    rates: dict[tuple[uuid.UUID, dt.date], PayRate],
    settings_by_day: dict[dt.date, dict[str, Any]],
) -> list[AttendanceDay]:
    # Each job's day of today, still running, as the book's own rule says it from the taps there are (answer_days),
    # each with its share of today's meals so far (Jack: A). Never kept, and no lock taken: the book keeps today once it
    # is over, from every tap that came by then, and splits its meals again.
    jobs = list(StaffMember.objects.filter(shop=shop).order_by("pk"))
    days = answer_days(shop, jobs, today, today, ZoneInfo(shop.timezone), settings_by_day)
    money = meal_money_by_date(shop, today, today).get(today, NO_MONEY)
    # Who has eaten so far: whoever tapped today and shares the meals. One with no Toka yet waits, by the rule, and is
    # counted all the same, as they came: 8,000 among Asha, going home, and Juma, still at work, is 4,000 each. One rule
    # with the book's (who_shares): never the cook, and a person with two jobs once.
    sharing = who_shares([(day, "") for day in days], rates)
    share = meal_share(money, len(sharing.days) + sharing.waiting, settings_by_day[today][ROUNDING_STEP.key])
    for day in sharing.days:
        day.meal_share = share
    return days


def _to_pay(day: AttendanceDay, rate: PayRate | None, step: Decimal) -> DayToPay:
    # A day as the sum reads it: the book's answer and the decision beside it, with its own rate and step.
    return DayToPay(
        status=day.status,
        fine=day.fine,
        decided_status=day.decided_status,
        absence_type=day.absence_type,
        decided_fine=day.decided_fine,
        meal_share=day.meal_share,
        rate=None if rate is None else rate.daily_rate,
        step=step,
    )
