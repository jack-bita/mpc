"""apps/staffpay/services/money.py — the money a person types, which the month's pay is made of (pay.py): each worker's
daily pay rate (WAGE-1), the day's meal money (WAGE-7), and money given to a worker before payday (WAGE-8).

A pay rate is typed by a person, the owner (set_pay_rate): from 10 Nov, Juma earns 10,000 a day. Whoever sets it sets a
worker's pay, so who may is the PIN's rule, asked by the people app (02 §5). No line in the change log: a worker's pay
never sits on a shared device (03 §6.1).

The day's meal money is typed by whoever the owner gave the key to (record_meal_money, WAGE-7): Monday's flour, 5,000,
and its meat, 3,000. A wrong one is crossed out, with who, when and why (void_meal_money), and the book splits what
counts among who came (book.py). Hela ya chakula asks for any days of it, and the whole of them, through
meal_money_days, which works them out through the book too, so it writes as the month's page does.

Money given before payday is typed on the day it is given by whoever holds money.advance, the owner or a manager, and
never their own (record_advance, WAGE-8): Juma's 20,000 of the 10th. A wrong one is crossed out, with who, when and why
(void_advance). Advansi asks for a month of them, and whom one may be typed for, through advances_month. No line in the
change log, as for a rate. What each worker was given in a month comes off that month's pay.
"""

import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.core.permissions import Permission
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import ALL_SHOPS, ShopMismatch, current_shop
from apps.people.models import StaffMember, StaffStatus
from apps.people.permissions import require
from apps.people.services import lock_worker_for_a_change
from apps.shops.models import Shop
from apps.shops.selectors import closed_days, get_setting, shop_today
from apps.staffpay.calculations import NO_MEAL_SHARE, add_up
from apps.staffpay.models import (
    MOST_ADVANCE,
    MOST_DAILY_RATE,
    MOST_MEAL_MONEY,
    Advance,
    AttendanceDay,
    MealMoney,
    PayRate,
)
from apps.staffpay.selectors import closed_to, is_closed, rates_between
from apps.staffpay.services.book import (
    SUNDAY,
    lock_jobs,
    month_span,
    ran_on,
    refuse_if_closed,
    who_shares,
    work_out_days,
)


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
    with cents (pay_rate.amount_invalid), or over ten million (pay_rate.amount_too_big); a day before the job's first
    (pay_rate.before_first_day), after the last of a job that ended (pay_rate.after_last_day), or one whose pay is
    approved (pay.day_approved); and on the demo, a person's note (demo.no_note). Returns the rate as saved."""
    # Spaces around a note say nothing, and "  " is no note.
    note = note.strip()
    # One transaction: the lock below holds until the rate is saved, so who may is asked of the jobs as they are when it
    # is written. Not a recording_changes block: a rate writes no line in the change log, as no laptop gets one.
    with transaction.atomic():
        # Both jobs locked, then who may asked on them as they are now, by the people app, which owns the rule (02 §5):
        # whoever sets a rate sets a worker's pay, as whoever sets a PIN can act as them. So staff.manage on the whole
        # shop, holding every key the worker was given; never one's own rate (a manager raising his own pay); an owner's
        # only by the superuser. The same lock the book of days takes on every job (work_out_days), so a rate set while
        # a manager opens the month waits a moment for it. One who left too: a day he worked before his first rate would
        # otherwise hold the month's approval, and every later month's, for good, with nothing able to mend it (WAGE-3's
        # review).
        staff, by = lock_worker_for_a_change(staff, by, left_too=True)
        # And the key that changes the shop's rules and rates, the owner's (spec §6): a manager handed staff.manage to
        # reset PINs, or to add a loader, may not change anyone's pay with it (WAGE-1's card). Read afresh, after the
        # lock, as the rule above reads its own key: a key taken away a moment ago counts.
        if by is not None:
            require(by, Permission.SETTINGS_MANAGE, None)
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
        # A slip of the zeros, as for a row of meal money (MOST_DAILY_RATE).
        elif daily_rate > MOST_DAILY_RATE:
            errors["daily_rate"] = [
                ValidationError("A day's pay is at most ten million.", code="pay_rate.amount_too_big")
            ]
        # Any day of the job, gone by or to come: Juma started on 10 Nov and Baba types his rate on the 19th, from the
        # 10th, so those days are paid. Never before the job's first day, read under the lock: a day before it is not a
        # day of this job to pay.
        if effective_from < staff.started_on:
            errors["effective_from"] = [
                ValidationError("A rate can't start before the worker's first day.", code="pay_rate.before_first_day")
            ]
        # Nor after the last day of a job that ended: it has no day there to pay, and a rate that starts then would mend
        # nothing. Its own days alone, until their pay is approved.
        elif staff.status == StaffStatus.LEFT and effective_from > cast(dt.date, staff.left_on):
            errors["effective_from"] = [
                ValidationError("A rate can't start after the worker's last day.", code="pay_rate.after_last_day")
            ]
        # Nor from a day whose pay is approved (WAGE-3, A3), the shop's or this worker's alone: those days were paid at
        # the rate there was, so a raise starts after them, from the next open month. Under the lock on the job, one of
        # those the approval takes.
        elif is_closed(Shop.objects.get(pk=staff.shop_id), effective_from, staff.pk):
            errors["effective_from"] = [ValidationError("The pay of this day is approved.", code="pay.day_approved")]
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


# On the demo, the ready reason money typed wrong is crossed out with, meal money (WAGE-7) or an advance (WAGE-8), kept
# as its code, which the page says in words, *Kiasi kimekosewa* (as DEMO_VOID_REASONS): a typed one would show to every
# visitor after.
DEMO_MONEY_VOID_REASONS = ("wrong_amount",)


def record_meal_money(
    shop: Shop, *, money_id: uuid.UUID, date: dt.date, amount: Decimal, note: str = "", by: StaffMember
) -> MealMoney:
    """Type what the shop spent on the workers' meals on one day (WAGE-7, 02 §12): Monday's flour, 5,000. A day may have
    several, which add up; the book splits the sum among who came the next time it works the date out. `money_id`: the
    client's (ADR-0007), so the route answers a request sent twice with the row it made (CreateOnceMixin). `by`: who
    types it, with meals.record on the whole shop. Refuses, all together, each beside its box: an amount of 0 or less,
    or with cents (meal_money.amount_invalid), or over ten million (meal_money.amount_too_big); a day to come
    (meal_money.in_future), a Sunday, or a day attendance was off (meal_money.not_working_day), or one whose pay is
    approved (pay.day_approved); and on the demo, a note (demo.no_note). Returns the row as saved."""
    # A job of another shop typing into this shop's money is a bug in the calling code (T1), never a person's mistake:
    # the route finds both in the one shop open. A server error, before anything is read.
    if by.shop_id != shop.pk:
        raise ShopMismatch("record_meal_money was given a person of another shop.")
    # Spaces around a note say nothing, and "  " is no note.
    note = note.strip()
    # Not a recording_changes block: meal money writes no line in the change log, as no laptop gets one (03 §6.1).
    with transaction.atomic():
        # First, so someone without it sets nothing to work; read afresh, so a key taken away a moment ago counts. On
        # the whole shop, as the workers of both sides eat together.
        require(by, Permission.MEALS_RECORD, None)
        # The book's lock, which the approval of a month takes (WAGE-3): money typed while Baba approves November waits,
        # and then finds it approved. Every job, as the money is split among whoever came.
        lock_jobs(shop)
        # The boxes, all together, so a person who got two wrong sees both at once, each beside its own (ADR-0040).
        errors: dict[str, list[ValidationError]] = {}
        # As the table's rules hold: named here, beside the amount's box, where the table's own would name the whole
        # row. to_integral_value() drops the places without rounding the check away: 5000.50 is not whole.
        if amount <= 0 or amount != amount.to_integral_value():
            errors["amount"] = [
                ValidationError("Meal money is a whole amount above 0.", code="meal_money.amount_invalid")
            ]
        elif amount > MOST_MEAL_MONEY:
            errors["amount"] = [ValidationError("Meal money is at most ten million.", code="meal_money.amount_too_big")]
        if date > shop_today(shop):
            # Tomorrow's meals aren't cooked yet, so it is a wrong date. Today's are: typed as they are paid for.
            errors["date"] = [ValidationError("A day to come has no meals yet.", code="meal_money.in_future")]
        elif date.weekday() == SUNDAY or not get_setting(ATTENDANCE_ON, shop, on=date):
            # A day the book answers for nobody: money typed there would be shared by nobody, a slip of the date. A
            # closed day takes it: breakfast was cooked the morning of a funeral, and each day that came is decided.
            errors["date"] = [ValidationError("Only a working day has meal money.", code="meal_money.not_working_day")]
        elif is_closed(shop, date):
            # Every worker's share of that day is paid (A3). One who left and was approved alone locks nothing here: the
            # others' shares still move, and theirs stays as they paid it (book.py).
            errors["date"] = [ValidationError("The pay of this day is approved.", code="pay.day_approved")]
        # On the demo every visitor logs in as Meneja (OPS-3): a note would show to every visitor after them, signed by
        # the shared manager, until the morning's seed, so it isn't kept, as for a rule (demo.no_note, set_setting).
        if settings.DEMO_SEED and note:
            errors["note"] = [ValidationError("On the demo, a note isn't kept.", code="demo.no_note")]
        if errors:
            raise ValidationError(errors)
        row = MealMoney(id=money_id, shop=shop, date=date, amount=amount, note=note, created_by=by)
        # The row's own checks last, as a guard on what the boxes above already asked: a note too long, an id taken.
        row.full_clean()
        # An INSERT, never an UPDATE: an id another row holds clashes, loudly, and never overwrites it (03 §5.4).
        row.save(force_insert=True)
    return row


def void_meal_money(money: MealMoney, *, reason: str, by: StaffMember) -> MealMoney:
    """Cross out meal money typed wrong (WAGE-7, 02 §12, T2): 30,000 for 3,000, "Sifuri moja zaidi". The row stays,
    voided once with who, when and why, and counts for nothing; the right amount is typed again. Never brought back.
    `by`: who crosses it out, with meals.record on the whole shop, whoever typed it. A row crossed out already, by this
    request sent twice or by someone a moment before, is answered as it was crossed out, never stamped again (CORE-3's
    Watch out). Refuses a row of a day whose pay is approved (pay.day_approved); and, beside the reason's box, no reason
    (meal_money.reason_missing), or on the demo a reason not the ready one (demo.ready_reasons). Returns the row as
    saved."""
    # Who voids is a staff member of the row's own shop (T1): the void rule in the database checks only that the stamp
    # is filled whole, so this is the check it can't make with one column.
    if by.shop_id != money.shop_id:
        raise ShopMismatch("void_meal_money was given a person of another shop.")
    reason = reason.strip()
    with transaction.atomic():
        require(by, Permission.MEALS_RECORD, None)
        shop = Shop.objects.get(pk=money.shop_id)
        lock_jobs(shop)
        # Read afresh under the lock: one crossed out already is answered as it is, whatever was approved since.
        if MealMoney.objects.get(pk=money.pk).voided_at is None:
            refuse_if_closed(shop, money.date)
        if not reason:
            raise ValidationError(
                {"reason": [ValidationError("Money crossed out says why.", code="meal_money.reason_missing")]}
            )
        if settings.DEMO_SEED and reason not in DEMO_MONEY_VOID_REASONS:
            raise ValidationError(
                {"reason": [ValidationError("On the demo, pick the ready reason.", code="demo.ready_reasons")]}
            )
        # The stamp, filled once, by one guarded UPDATE, as a tap's (void_tap): only while the row is not crossed out,
        # so two voids never both write it. Never save(), which AppendOnly refuses; the void trigger lets this UPDATE
        # change the stamp and nothing else (ADR-0021).
        MealMoney.objects.filter(pk=money.pk, voided_at__isnull=True).update(
            voided_at=timezone.now(), voided_by=by, void_reason=reason
        )
        # Read back as it is now: crossed out by this request, or by the same one sent before, its answer lost, or by
        # someone a moment before, whose stamp the page is then shown.
        return MealMoney.objects.get(pk=money.pk)


@dataclass(frozen=True)
class VoidedMealMoney:
    # Who crossed out a row of meal money, by nickname; when; and why. On the demo the reason is a ready one's code
    # (`wrong_amount`), which the page says in words.
    by: str
    at: dt.datetime
    reason: str


@dataclass(frozen=True)
class MealMoneyLine:
    # One row of a day's meal money, as the day's page shows it: "TSh 5,000 · Unga na maharage", who typed it and when,
    # and who crossed it out, or None while it counts. Its day too, as the sheet's answer is the row alone.
    id: uuid.UUID
    date: dt.date
    amount: Decimal
    note: str
    by: str
    at: dt.datetime
    voided: VoidedMealMoney | None


@dataclass(frozen=True)
class MealDay:
    # One day of Hela ya chakula (WAGE-7): its money, the sum of the rows that count; whether it is over, as today is
    # not, so its money isn't split yet; how many workers share it, each one's share as the book kept it, and how many
    # wait for a decision; and its rows, oldest first, the crossed-out ones too. No money and someone who came:
    # Haijaandikwa. Money and nobody to share it: Hakuna wa kuchangia.
    date: dt.date
    amount: Decimal
    over: bool
    sharers: int
    share: Decimal
    waiting: int
    rows: list[MealMoneyLine]


@dataclass(frozen=True)
class MealMoneyDays:
    # The page's answer: the span, up to the shop's today, or as it was asked when it is all to come; today itself; the
    # whole of its money; and its days, newest first. On the demo, the ready reason a row may be crossed out with;
    # elsewhere none.
    first: dt.date
    last: dt.date
    today: dt.date
    total: Decimal
    days: list[MealDay]
    ready_void_reasons: list[str]
    # Up to which day the shop's pay is approved (WAGE-3), or None: no money of those days is typed or crossed out.
    closed_to: dt.date | None = None


# No money: a day nobody typed, or a span of them. Two places, as every amount.
NO_MONEY = Decimal("0.00")


def meal_money_days(shop: Shop, first: dt.date, last: dt.date) -> MealMoneyDays:
    """The meal money from `first` to `last`, both counted and up to the shop's today, as Hela ya chakula shows it
    (WAGE-7): each day with money typed for it, or with a worker who came and shares it, or who may have, and today; and
    the whole of it. Worked out through the book (work_out_days), so it writes as the book does, and asked twice writes
    nothing the second time. The shop must be open, as for the book."""
    today = shop_today(shop)
    ready = list(DEMO_MONEY_VOID_REASONS) if settings.DEMO_SEED else []
    if today < first:
        # Days to come alone, when nobody has eaten yet: nothing to read. Answered as they were asked for, so the page
        # never heads them with a last day before the first.
        return MealMoneyDays(first, last, today, NO_MONEY, [], ready, closed_to(shop))
    last = min(last, today)
    # The book first, so each day's share is as it is now: the money typed a moment ago, a tap that came late, a day
    # decided. It answers every job's day up to yesterday. The rows are read after it, so money typed between the two
    # shows with the split before it, until the page asks again (as a tap does, worker_attendance).
    book: dict[dt.date, list[AttendanceDay]] = defaultdict(list)
    for worked_out in work_out_days(shop, first, last):
        book[worked_out.date].append(worked_out)
    rates = rates_between(shop, first, last)
    rows: dict[dt.date, list[MealMoney]] = defaultdict(list)
    # Who typed each and who crossed it out come in the same read. Oldest first, as they were typed; then the id, for
    # two typed at the very same moment.
    for row in (
        MealMoney.objects.filter(shop=shop, date__range=(first, last))
        .select_related("created_by", "voided_by")
        .order_by("date", "created_at", "id")
    ):
        rows[row.date].append(row)
    days: list[MealDay] = []
    for date in _dates_back(first, last):
        day = _meal_day(date, today, book[date], rows[date], rates)
        # A day to show: one with a row, crossed out or not; one whose meals someone ate, or may have; and today, while
        # it is a working day, as that is when its money is typed.
        if day.rows or day.sharers or day.waiting or (date == today and _works_today(shop, today)):
            days.append(day)
    return MealMoneyDays(first, last, today, sum((day.amount for day in days), NO_MONEY), days, ready, closed_to(shop))


def _dates_back(first: dt.date, last: dt.date) -> list[dt.date]:
    # Each day from `last` back to `first`, both counted. Counted forward from the first, never a day taken off each
    # time: past the first day Python knows, that step is an error.
    return [first + dt.timedelta(days=n) for n in range((last - first).days, -1, -1)]


def _meal_day(
    date: dt.date,
    today: dt.date,
    worked_out: list[AttendanceDay],
    rows: list[MealMoney],
    rates: dict[tuple[uuid.UUID, dt.date], PayRate],
) -> MealDay:
    # One date of Hela ya chakula, from its jobs' days as the book answered them, its rows, and the rates in force.
    sharing = who_shares([(day, day.decided_status) for day in worked_out], rates)
    # The share as the book kept it, the same for everyone who shares the date's meals: never worked out a second time
    # here, so the page and the pay can't differ (WAGE-2). Of those still to pay, where there are any: one who left and
    # was paid keeps the share they paid, though the date was split again among more since (WAGE-3). The most of them,
    # as a rate typed between the book's read and this one's adds someone whose kept share is still 0, until the page
    # asks again.
    to_pay = [day for day in sharing.days if day.payslip_id is None]
    share = max((day.meal_share for day in to_pay or sharing.days), default=NO_MEAL_SHARE)
    return MealDay(
        date=date,
        amount=sum((row.amount for row in rows if row.voided_at is None), NO_MONEY),
        over=date < today,
        sharers=len(sharing.days),
        share=share,
        waiting=sharing.waiting,
        rows=[meal_line(row) for row in rows],
    )


def meal_line(row: MealMoney) -> MealMoneyLine:
    """A row of meal money as the day's page shows it, which the sheets' answers are too. Who typed it is always there,
    as the table holds."""
    by = cast(StaffMember, row.created_by)
    voided = None
    if row.voided_at is not None and row.voided_by is not None:
        voided = VoidedMealMoney(by=row.voided_by.display_name, at=row.voided_at, reason=row.void_reason)
    return MealMoneyLine(
        id=row.pk,
        date=row.date,
        amount=row.amount,
        note=row.note,
        by=by.display_name,
        at=row.created_at,
        voided=voided,
    )


def _works_today(shop: Shop, today: dt.date) -> bool:
    # Whether the shop works today, as the book will count it once it is over: not a Sunday, not a closed day, and while
    # attendance is on.
    return (
        today.weekday() != SUNDAY
        and today not in closed_days(shop, today, today)
        and bool(get_setting(ATTENDANCE_ON, shop, on=today))
    )


def record_advance(
    staff: StaffMember, *, advance_id: uuid.UUID, date: dt.date, amount: Decimal, note: str = "", by: StaffMember
) -> Advance:
    """Type money given to a worker before payday (WAGE-8, 02 §12): Juma asked for 20,000 on the 10th, and Meneja gave
    it. It comes off the pay of its day's month the next time the pay is asked for. `advance_id`: the client's
    (ADR-0007), so the route answers a request sent twice with the row it made (CreateOnceMixin). `by`: who types it,
    with money.advance on the whole shop, and never the worker themself. Refuses: one's own (advance.own); and, all
    together, each beside its box, a worker with no daily pay (advance.not_paid_by_day); an amount of 0 or less, or with
    cents (advance.amount_invalid), or over ten million (advance.amount_too_big); a day to come (advance.in_future), one
    outside the job's days (advance.outside_job), or one whose pay is approved (pay.day_approved); and on the demo, a
    note (demo.no_note). Returns the row as saved."""
    # A job of another shop typing this shop's money is a bug in the calling code (T1), never a person's mistake: the
    # route finds both in the one shop open. A server error, before anything is read.
    if by.shop_id != staff.shop_id:
        raise ShopMismatch("record_advance was given a person of another shop.")
    # Spaces around a note say nothing, and "  " is no note.
    note = note.strip()
    # Not a recording_changes block: an advance writes no line in the change log, as no laptop gets one (03 §6.1).
    with transaction.atomic():
        # First, so someone without it sets nothing to work; read afresh, so a key taken away a moment ago counts. On
        # the whole shop, as a worker and their pay belong to it.
        require(by, Permission.MONEY_ADVANCE, None)
        # The job as it is now: its first or last day may have just moved (PPL-10). An advance may be of a day gone by,
        # so a worker who left still takes one for a day they worked: a forgotten one, or their last pay would be wrong.
        # Locked, as the approval of a month locks every job (WAGE-3): one typed while Baba approves November waits, and
        # then finds it approved. FOR NO KEY UPDATE, the light lock (backend rules).
        staff = StaffMember.objects.select_for_update(no_key=True).get(pk=staff.pk)
        # Never one's own (Jack: A), as nobody sets their own rate or decides their own day: a manager alone in the shop
        # would give themself its money on their own word. By the person, not the job: someone hired again (PPL-11) has
        # two jobs, and neither's is theirs to type.
        if staff.user_id == by.user_id:
            raise ValidationError("Nobody types their own advance.", code="advance.own")
        # The boxes, all together, so a person who got two wrong sees both at once, each beside its own (ADR-0040).
        errors: dict[str, list[ValidationError]] = {}
        # Only a worker the shop pays by the day, from whatever day: it comes off that pay, and off nothing else. The
        # owner, who has no rate, takes the shop's money as a withdrawal, the drawer's (02 §10).
        if not PayRate.objects.filter(shop_id=staff.shop_id, staff=staff).exists():
            errors["staff"] = [ValidationError("This worker has no daily pay.", code="advance.not_paid_by_day")]
        # As the table's rules hold: named here, beside the amount's box, where the table's own would name the whole
        # row. to_integral_value() drops the places without rounding the check away: 20000.50 is not whole. One bigger
        # than the pay so far is taken: the money was given, and the pay shows its minus.
        if amount <= 0 or amount != amount.to_integral_value():
            errors["amount"] = [ValidationError("An advance is a whole amount above 0.", code="advance.amount_invalid")]
        elif amount > MOST_ADVANCE:
            errors["amount"] = [ValidationError("An advance is at most ten million.", code="advance.amount_too_big")]
        shop = Shop.objects.get(pk=staff.shop_id)
        if date > shop_today(shop):
            # Tomorrow's isn't given yet, so it is a wrong date. A Sunday's is taken, and a closed day's: money is asked
            # for on any day, and nothing is shared or worked on it.
            errors["date"] = [ValidationError("An advance is never of a day to come.", code="advance.in_future")]
        elif not ran_on(staff, date):
            # Before the first day or after the last, the person wasn't a worker of this job, so it is a slip of the
            # date; and a day outside the job is in no pay of it the worker would look for it in.
            errors["date"] = [
                ValidationError("An advance is of a day the worker had this job.", code="advance.outside_job")
            ]
        elif is_closed(shop, date, staff.pk):
            # Their pay of that day's month is final (A3): this money would come off nothing. Given after it, it is of
            # the day it is given, and comes off the month that still runs.
            errors["date"] = [ValidationError("The pay of this day is approved.", code="pay.day_approved")]
        # On the demo every visitor logs in as Meneja (OPS-3): a note would show to every visitor after them, signed by
        # the shared manager, until the morning's seed, so it isn't kept, as for a rule (demo.no_note, set_setting).
        if settings.DEMO_SEED and note:
            errors["note"] = [ValidationError("On the demo, a note isn't kept.", code="demo.no_note")]
        if errors:
            raise ValidationError(errors)
        row = Advance(
            id=advance_id, shop_id=staff.shop_id, staff=staff, date=date, amount=amount, note=note, created_by=by
        )
        # The row's own checks last, as a guard on what the boxes above already asked: a note too long, an id taken.
        row.full_clean()
        # An INSERT, never an UPDATE: an id another row holds clashes, loudly, and never overwrites it (03 §5.4).
        row.save(force_insert=True)
    return row


def void_advance(advance: Advance, *, reason: str, by: StaffMember) -> Advance:
    """Cross out an advance typed wrong (WAGE-8, 02 §12, T2): 300,000 for 30,000, "Sifuri moja zaidi". The row stays,
    voided once with who, when and why, and counts for nothing; the right amount is typed again. Never brought back.
    `by`: who crosses it out, with money.advance on the whole shop, whoever typed it, and never the worker it was given
    to. A row crossed out already, by this request sent twice or by someone a moment before, is answered as it was
    crossed out, never stamped again (CORE-3's Watch out). Refuses: one's own (advance.own); one of a day whose pay is
    approved (pay.day_approved); and, beside the reason's box, no reason (advance.reason_missing), or on the demo a
    reason not the ready one (demo.ready_reasons). Returns the row as saved."""
    # Who voids is a staff member of the row's own shop (T1): the void rule in the database checks only that the stamp
    # is filled whole, so this is the check it can't make with one column.
    if by.shop_id != advance.shop_id:
        raise ShopMismatch("void_advance was given a person of another shop.")
    reason = reason.strip()
    with transaction.atomic():
        require(by, Permission.MONEY_ADVANCE, None)
        # Never one's own (Jack: A): crossing it out would pay the money twice, so a worker never erases what they took.
        # By the person, as typing one is. Their job locked, as typing one locks it.
        if StaffMember.objects.select_for_update(no_key=True).get(pk=advance.staff_id).user_id == by.user_id:
            raise ValidationError("Nobody crosses out their own advance.", code="advance.own")
        # Read afresh under the lock: one crossed out already is answered as it is, whatever was approved since.
        if Advance.objects.get(pk=advance.pk).voided_at is None:
            refuse_if_closed(Shop.objects.get(pk=advance.shop_id), advance.date, advance.staff_id)
        if not reason:
            raise ValidationError(
                {"reason": [ValidationError("An advance crossed out says why.", code="advance.reason_missing")]}
            )
        if settings.DEMO_SEED and reason not in DEMO_MONEY_VOID_REASONS:
            raise ValidationError(
                {"reason": [ValidationError("On the demo, pick the ready reason.", code="demo.ready_reasons")]}
            )
        # The stamp, filled once, by one guarded UPDATE, as a row of meal money's (void_meal_money): only while the row
        # is not crossed out, so two voids never both write it. Never save(), which AppendOnly refuses; the void trigger
        # lets this UPDATE change the stamp and nothing else (ADR-0021).
        Advance.objects.filter(pk=advance.pk, voided_at__isnull=True).update(
            voided_at=timezone.now(), voided_by=by, void_reason=reason
        )
        # Read back as it is now: crossed out by this request, or by the same one sent before, its answer lost, or by
        # someone a moment before, whose stamp the page is then shown.
        return Advance.objects.get(pk=advance.pk)


@dataclass(frozen=True)
class VoidedAdvance:
    # Who crossed out an advance, by nickname; when; and why. On the demo the reason is a ready one's code
    # (`wrong_amount`), which the page says in words.
    by: str
    at: dt.datetime
    reason: str


@dataclass(frozen=True)
class AdvanceLine:
    # One advance, as Advansi's line and its own page show it: "Jumanne 10/11 · Juma  20,000", what it was for, who
    # typed it and when, and who crossed it out, or None while it counts. Never the worker's rate or pay: whoever gives
    # money early sees what was given, not what is earned (the two keys of pay, WAGE-1).
    id: uuid.UUID
    staff_id: uuid.UUID
    display_name: str
    date: dt.date
    amount: Decimal
    note: str
    by: str
    at: dt.datetime
    voided: VoidedAdvance | None


@dataclass(frozen=True)
class AdvanceWorker:
    # A worker one may be typed for: the job, the nickname, and their last day if they left, which the sheet says beside
    # the name, as a person hired again in the month has two jobs of one name (PPL-11).
    staff_id: uuid.UUID
    display_name: str
    left_on: dt.date | None


@dataclass(frozen=True)
class AdvancesMonth:
    # Advansi's answer (WAGE-8): the month, as its first day; the shop's today; the sum of those that count; every one
    # of the month, newest first, the crossed-out ones too (A2); and whom one may be typed for, by name.
    month: dt.date
    today: dt.date
    total: Decimal
    rows: list[AdvanceLine]
    workers: list[AdvanceWorker]
    # Whether the month's pay is approved (WAGE-3): then none is typed in it, and the page offers no button.
    closed: bool = False


def ready_advance_void_reasons() -> list[str]:
    """The ready reason one may be crossed out with, for the sheet to offer: the demo's, or none elsewhere, where it is
    typed."""
    return list(DEMO_MONEY_VOID_REASONS) if settings.DEMO_SEED else []


def advances_month(shop: Shop, month: dt.date, *, viewer: StaffMember) -> AdvancesMonth:
    """The money given before payday in the month of `month`, any day of it, as Advansi shows it (WAGE-8), and whom one
    may be typed for: whoever the shop pays by the day and had a day of the job in the month, up to today, so one who
    left stays for the months they worked; and never `viewer`, whoever's job it is (Jack: A). The shop must be open."""
    # The same checks as the selectors', for the same reasons (ADR-0022): asked inside another shop's visit, the guard
    # would hide every row, and the month would be empty without a word.
    opened = current_shop()
    if opened is not ALL_SHOPS and opened != shop.pk:
        raise ShopMismatch("advances_month was given a shop that is not the one open.")
    if isinstance(month, dt.datetime):
        raise TypeError("advances_month needs the shop's business dates, not a datetime.")
    first, last = month_span(month)
    today = shop_today(shop)
    # Newest first: by day, then as they were typed, the id last, for two typed at the very same moment. The names come
    # in the same read.
    rows = [
        advance_line(row)
        for row in Advance.objects.filter(shop=shop, date__range=(first, last))
        .select_related("staff", "created_by", "voided_by")
        .order_by("-date", "-created_at", "-id")
    ]
    # Whoever has a rate, from whatever day, as record_advance asks; a first day to come takes none yet.
    workers = (
        StaffMember.objects.filter(shop=shop, started_on__lte=min(last, today))
        .filter(Q(left_on__isnull=True) | Q(left_on__gte=first))
        .filter(Exists(PayRate.objects.filter(shop=shop, staff=OuterRef("pk"))))
        .exclude(user_id=viewer.user_id)
    )
    return AdvancesMonth(
        month=first,
        today=today,
        total=add_up(row.amount for row in rows if row.voided is None),
        rows=rows,
        # By name, as Mishahara lists them; then the job's id, so two jobs of one name always come in one order.
        workers=[
            AdvanceWorker(staff_id=staff.pk, display_name=staff.display_name, left_on=staff.left_on)
            for staff in sorted(workers, key=lambda staff: (staff.display_name.casefold(), staff.pk))
        ],
        closed=is_closed(shop, first),
    )


def advance_line(row: Advance) -> AdvanceLine:
    """An advance as the pages show it, which the sheets' answers are too. Who typed it is always there, as the table
    holds."""
    by = cast(StaffMember, row.created_by)
    voided = None
    if row.voided_at is not None and row.voided_by is not None:
        voided = VoidedAdvance(by=row.voided_by.display_name, at=row.voided_at, reason=row.void_reason)
    return AdvanceLine(
        id=row.pk,
        staff_id=row.staff_id,
        display_name=row.staff.display_name,
        date=row.date,
        amount=row.amount,
        note=row.note,
        by=by.display_name,
        at=row.created_at,
        voided=voided,
    )
