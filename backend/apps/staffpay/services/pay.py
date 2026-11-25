"""apps/staffpay/services/pay.py — the month's pay, worked out from the days, the rates, the meals and the advances
(WAGE-2).

The month's pay is asked for by Mishahara (pay_month) and by one worker's page (worker_pay): the book's days (book.py),
each at its own rate, added up by the sum (work_out_pay, apps/staffpay/calculations.py). The draft is never saved (Jack,
WAGE-2): a saved one is old as soon as a day is decided, so it is worked out each time, through the book, as the month's
page is. WAGE-3 saves a payslip once, at the approval. And today, still running, is added once the worker taps Toka,
less their share of today's meals so far, so one who leaves tonight is paid for it (Jack: A): judged by the book's own
rule (answer_days), and never kept.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from apps.core.settings_registry import ATTENDANCE_ON, ROUNDING_STEP
from apps.core.tenancy import ShopMismatch
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.shops.selectors import shop_settings_between, shop_today
from apps.staffpay.calculations import NO_PAY, DayToPay, Pay, add_up, meal_share, work_out_pay
from apps.staffpay.models import AttendanceDay, DayStatus, PayRate, ReviewReason
from apps.staffpay.selectors import advances_between, meal_money_by_date, rates_between
from apps.staffpay.services.book import answer_days, month_span, who_shares, work_out_days
from apps.staffpay.services.money import NO_MONEY


@dataclass(frozen=True)
class WorkerPay:
    # One worker's pay of a month (WAGE-2), a job's, as a day is a job's: a person hired again in the month has two,
    # each with its own days and rates (PPL-11). Whose, and their last day if they left, which the page says beside
    # their name; the sum of the days that are over, line by line, less what they were given before payday (WAGE-8);
    # today alone, once they tapped Toka, or None (Leo, Jack: A); and what is left to pay, the two together.
    staff_id: uuid.UUID
    display_name: str
    left_on: dt.date | None
    pay: Pay
    today: Pay | None
    total: Decimal


@dataclass(frozen=True)
class PayMonth:
    # Mishahara's answer (WAGE-2): the month, as its first day; the shop's today; the last day counted, or None when no
    # day of the month is over; a line per worker paid by the day, or given money before payday in it (WAGE-8), by name;
    # the whole of it; and the jobs with a working day in it, over or today's, which says whether there is anything to
    # pay yet.
    month: dt.date
    today: dt.date
    counted_to: dt.date | None
    workers: list[WorkerPay]
    total: Decimal
    worked: frozenset[uuid.UUID]

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


def pay_month(shop: Shop, month: dt.date) -> PayMonth:
    """The pay of the month of `month`, any day of it, as Mishahara shows it (WAGE-2; spec §8.1, 02 §15, 8), for
    everyone the shop pays by the day, or gave money before payday in it (WAGE-8): each worker's days that are over,
    each at its own rate, added up line by line, less what they were given; today, for whoever has tapped Toka; and the
    whole. Worked out through the book (work_out_days), so it writes as the book does, and asked twice writes nothing
    the second time; the pay itself is never kept. The shop must be open, as for the book."""
    first, last = month_span(month)
    # The shop's today, read once: the pay counts up to the day before it, and today apart, whatever the clock does
    # meanwhile. The book reads its own a moment later, and at midnight answers one day more, which for this answer is
    # still today: only the days before it, or it would be paid twice. The book also refuses a shop that isn't the one
    # open, and a moment in place of the shop's day.
    today = shop_today(shop)
    days = [day for day in work_out_days(shop, first, last) if day.date < today]
    if today < first:
        # A month to come: nothing of it is worked yet, and nothing more is read. So the calendar's last month is an
        # answer too, never a day past the last one Python knows (ATT-5's review).
        return PayMonth(month=first, today=today, counted_to=None, workers=[], total=NO_PAY, worked=frozenset())
    # Each job's rate on each day, a raise splitting the month at its own day (WAGE-1); the step half a day, and a share
    # of the meals, is rounded to on each day (A1), and the attendance switch, for today. One read each for the month.
    # After the book has let its lock go, so a first rate typed between the two lists Juma once with no meals taken,
    # while Asha still carries his share, until the page asks again, as Hela ya chakula's does (_meal_day). A payslip
    # kept for good must read them inside the lock (WAGE-3).
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
    # A worker given money is listed for it, though no working day of theirs has come, as on a 1st that is a Sunday, or
    # their rate starts later: or the money would be on nobody's pay until then.
    unlisted = advances.keys() - workers.keys()
    if unlisted:
        workers |= {staff.pk: staff for staff in StaffMember.objects.filter(shop=shop, pk__in=unlisted)}
    # The book answers date by date, so each worker's days come in their order, and so do the lines of their pay.
    over: dict[uuid.UUID, list[AttendanceDay]] = defaultdict(list)
    for day in days:
        over[day.staff_id].append(day)

    def paid(some: Iterable[AttendanceDay], given: Decimal = NO_PAY) -> Pay:
        # Some days of one worker, each with its own rate and step, less what they were given.
        return work_out_pay(
            (
                _to_pay(day, rates.get((day.staff_id, day.date)), settings_by_day[day.date][ROUNDING_STEP.key])
                for day in some
            ),
            advances=given,
        )

    lines = []
    for job, staff in workers.items():
        # Today only once a Toka has ended it (first_out, ATT-4): until then it is still theirs to work, and the rule
        # would send it to a person for want of one. A Toka the rule can't judge, at 16:00, ended it too, and waits. And
        # a day with a tap whose time nobody trusts, as the laptop's clock moved: a Toka among them has no minute, so it
        # ends nothing the rule can read, and whatever is tapped after, the day waits. Said tonight: one who leaves with
        # it unsaid would be paid without today, and nobody would know (WAGE-2's review).
        tonight = todays.get(job)
        waits = tonight is not None and tonight.review_reason == ReviewReason.TIME_UNKNOWN
        ended = [tonight] if tonight is not None and (tonight.first_out is not None or waits) else []
        # The advances come off the days that are over, never off today's part too, or they would be taken twice.
        pay = paid(over[job], advances.get(job, NO_PAY))
        lines.append(_worker_pay(staff, pay, paid(ended) if ended else None))
    # By name, as the month page lists them; "asha" beside "Asha"; then the job's id, so two jobs of one name always
    # come in the same order, the one had first before the other (UUIDv7).
    lines.sort(key=lambda line: (line.display_name.casefold(), line.staff_id))
    return PayMonth(
        month=first,
        today=today,
        # Up to yesterday, or the end of a month gone by; none on the 1st.
        counted_to=min(last, today - dt.timedelta(days=1)) if first < today else None,
        workers=lines,
        total=add_up(line.total for line in lines),
        worked=frozenset(day.staff_id for day in working),
    )


def worker_pay(shop: Shop, job: StaffMember, month: dt.date) -> WorkerPayMonth:
    """One job's pay of the month of `month`, any day of it (WAGE-2): the very line Mishahara shows of them (pay_month),
    so the two pages never say two totals. A worker the shop neither pays by the day in it nor gave money in it has
    nothing, and the answer says so. The shop must be open, and the job one of it."""
    # The route finds the job through the guard, so another shop's never comes here; but a service checks what it is
    # given (T1), so a bug that passed one fails loudly.
    if job.shop_id != shop.pk:
        raise ShopMismatch("worker_pay was given a job of another shop.")
    whole = pay_month(shop, month)
    line = next((line for line in whole.workers if line.staff_id == job.pk), None)
    return WorkerPayMonth(
        month=whole.month,
        today=whole.today,
        counted_to=whole.counted_to,
        paid_by_day=line is not None,
        # Not one who left, whose last day may be in a month before: nothing of theirs is to come.
        no_day_yet=whole.is_running and job.left_on is None and job.pk not in whole.worked,
        worker=_worker_pay(job, work_out_pay([]), None) if line is None else line,
    )


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
