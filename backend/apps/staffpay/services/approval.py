"""apps/staffpay/services/approval.py — approving a month's pay, or one worker's alone (WAGE-3; 02 §12, A3): the one
moment it is kept.

    1 Dec, Baba reads November, 432,000 for three workers, and approves it:
        PayRun Novemba, by Baba
        Payslip Asha 152,000, Baraka 148,000, Juma 132,000, each with its lines, added up to the very total he read
        and each of their days of November marked as paid, which nothing changes from then on

What is kept is what the page showed (pay.py), worked out once more inside the book's lock, so no part of it moves
between the reading and the keeping; and only if every total is still the one the person saw. Refused while anything
would be missing from it: a day that waits (Jack: A), a day with no rate, an earlier month still open, a month not over.
Never undone: a mistake found later is an adjustment in a later month (A3, WAGE-9). Handing out the money is WAGE-9's.

One who left is approved alone, as they can't wait for the month's end (Jack, 15 Nov 2026), their last evening too:

    14 Nov, 18:45, Neema taps Toka and leaves; Baba reads her pay, 62,000, Leo with it, and approves it
        Payslip Neema 62,000, with no run; her days up to the 14th marked, today's kept with them
    1 Dec: the month's approval leaves her payslip as it is

No line in the change log, here or on any of the rows: no laptop keeps a payslip (03 §6.1).
"""

import datetime as dt
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.permissions import Permission
from apps.core.tenancy import ShopMismatch
from apps.people.models import StaffMember, StaffStatus
from apps.people.permissions import require
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.calculations import PaidAs, Pay, add_up, work_out_pay
from apps.staffpay.models import AttendanceDay, PayRun, Payslip, PayslipLine, PayslipLineKind
from apps.staffpay.selectors import advances_by_job, is_closed
from apps.staffpay.services.book import lock_jobs, month_span
from apps.staffpay.services.pay import (
    OpenDay,
    ToApprove,
    WorkerPay,
    draft_of,
    read_parts,
    run_of,
    what_stops,
    what_stops_alone,
)

# The keys whoever approves must hold, on the whole shop: the owner's own key to the approval, and the two of pay, as
# nobody approves what they may not read (02 §5; Jack, WAGE-1's review: A).
APPROVES = (Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE)


def approve_month(
    shop: Shop, month: dt.date, *, run_id: uuid.UUID, seen: Mapping[uuid.UUID, Decimal], by: StaffMember
) -> PayRun:
    """Approve the pay of the month of `month`, any day of it (WAGE-3, A3): a payslip for each worker with a line and
    none yet, its lines, and each of its days marked as paid, all in one transaction. `run_id`: the client's (ADR-0007),
    so the route answers a request sent twice with the run it made (CreateOnceMixin). `seen`: each worker's total as the
    person read it, by job, those approved alone among them. `by`: who approves, with pay.approve and the two keys of
    pay on the whole shop. Refuses: a month approved already (pay_run.already_approved), one before a month approved
    (pay_run.later_month_approved), one not over yet (pay_run.month_not_over), one with nobody to pay (pay_run.nobody),
    one while an earlier month is open (pay_run.earlier_month_open), a day that waits for a decision
    (pay_run.days_waiting), a day to pay with no rate (pay_run.days_without_rate), and totals that are no longer those
    seen (pay_run.totals_moved). The shop must be open. Returns the run as saved."""
    # A job of another shop approving this shop's pay is a bug in the calling code (T1), never a person's mistake: the
    # route finds both in the one shop open. A server error, before anything is read.
    if by.shop_id != shop.pk:
        raise ShopMismatch("approve_month was given a person of another shop.")
    first, last = month_span(month)
    with transaction.atomic():
        # The book's lock, before anything the pay is made of is read, and held until the run is kept: a decision, a
        # tap, a rate, an advance or meal money sent now waits, and then finds the month approved. And two people
        # approving at once take turns here: the second finds the run.
        _, by = _locked_by(shop, by)
        if run_of(shop, first) is not None:
            raise ValidationError("This month's pay is approved already.", code="pay_run.already_approved")
        _refuse_before_an_approved_month(shop, first)
        today = shop_today(shop)
        if today <= last:
            # Its last day isn't over, by the shop's own calendar, so nobody knows yet what it pays.
            raise ValidationError("A month is approved once it is over.", code="pay_run.month_not_over")
        # What the page showed, worked out again inside the lock, from parts that can't move until the commit.
        parts = read_parts(shop, first, last, today)
        draft = draft_of(shop, parts)
        if not draft.workers:
            raise ValidationError("Nobody is paid in this month.", code="pay_run.nobody")
        _refuse_if_stopped(what_stops(shop, parts, draft))
        if dict(seen) != {line.staff_id: line.total for line in draft.workers}:
            # Asha's day was decided a moment after Baba read the page: he approves only what he read, so the page shows
            # him the new totals first. By worker, never the whole alone, as two changes could cancel each other out.
            raise ValidationError("A total has changed since it was read.", code="pay_run.totals_moved")
        run = PayRun(id=run_id, shop=shop, month=first, created_by=by)
        # The row's own checks, as a guard on what was asked above: an id taken.
        run.full_clean()
        # An INSERT, never an UPDATE: an id another row holds clashes, loudly, and never overwrites it (03 §5.4).
        run.save(force_insert=True)
        _keep(
            first,
            run,
            [(line, parts.over.get(line.staff_id, [])) for line in draft.workers if line.approval is None],
            advances_by_job(shop, first, last),
            by,
        )
    return run


def approve_leaver(
    staff: StaffMember, month: dt.date, *, payslip_id: uuid.UUID, seen: Decimal, by: StaffMember
) -> Payslip:
    """Approve the pay of one worker who left, alone, for the month of `month`, any day of it (WAGE-3; Jack, 15 Nov
    2026): their payslip, its lines, and their days marked as paid, today's kept with them when they go tonight (Leo).
    `payslip_id`: the client's (ADR-0007), as a run's. `seen`: the total the person read. `by`: who approves, as for a
    month, and never one's own. Refuses: one's own (payslip.own); a worker who hasn't left (payslip.not_left); a month
    approved already (pay_run.already_approved), one before a month approved (pay_run.later_month_approved), or theirs
    (payslip.already_approved); nothing to pay (payslip.nothing); still clocked in today (payslip.still_clocked_in);
    and, as a month's, an earlier month of theirs still open, a day of theirs that waits or has no rate, and a total
    that is no longer the one seen. The shop must be open. Returns the payslip as saved."""
    if by.shop_id != staff.shop_id:
        raise ShopMismatch("approve_leaver was given a person of another shop.")
    shop = Shop.objects.get(pk=staff.shop_id)
    first, last = month_span(month)
    with transaction.atomic():
        # The same lock as the month's, so the two never both make a payslip of theirs; and the job read afresh with it,
        # as it may have just been marked as gone.
        jobs, by = _locked_by(shop, by)
        staff = next(job for job in jobs if job.pk == staff.pk)
        # Never one's own, alone (as an advance, WAGE-8): someone hired again would close their old job's pay on their
        # own word. By the person, not the job.
        if staff.user_id == by.user_id:
            raise ValidationError("Nobody approves their own pay alone.", code="payslip.own")
        if staff.status != StaffStatus.LEFT:
            # One who works here waits for the month: approved alone, nothing of the month could be fixed for them.
            raise ValidationError("Only one who left is approved alone.", code="payslip.not_left")
        if run_of(shop, first) is not None:
            raise ValidationError("This month's pay is approved already.", code="pay_run.already_approved")
        if Payslip.objects.filter(shop=shop, staff=staff, month=first).exists():
            raise ValidationError("This worker's pay is approved already.", code="payslip.already_approved")
        _refuse_before_an_approved_month(shop, first, staff.pk)
        today = shop_today(shop)
        if today < first:
            raise ValidationError("This worker has no pay in this month.", code="payslip.nothing")
        parts = read_parts(shop, first, last, today)
        if shop_today(shop) != today:
            # Midnight passed as the month was read, so what the page showed as today is a day gone by, which the book
            # may have kept a moment ago. The person reads the page again, which says it so.
            raise ValidationError("A total has changed since it was read.", code="pay_run.totals_moved")
        line = next((line for line in draft_of(shop, parts).workers if line.staff_id == staff.pk), None)
        if line is None:
            raise ValidationError("This worker has no pay in this month.", code="payslip.nothing")
        stops = what_stops_alone(shop, parts, line)
        if stops.still_clocked_in:
            # Before the others, as it comes of itself: approved now, today would be left out of their pay for good.
            raise ValidationError("This worker is still clocked in.", code="payslip.still_clocked_in")
        _refuse_if_stopped(stops)
        if seen != line.total:
            raise ValidationError("A total has changed since it was read.", code="pay_run.totals_moved")
        days = list(parts.over.get(staff.pk, []))
        tonight = parts.todays.get(staff.pk)
        if tonight is not None:
            # Today's day, still to come in the book, which keeps a day once it is over: kept now, as it is judged, with
            # its share of the meals as it stands, or the book would work it out again tomorrow with nothing paid
            # (Jack: A). Leo is a line of the page alone: on the payslip it is one of their days.
            days.append(tonight)
        # The very sum the page showed in two parts, in one: each day is paid alone, so the two add up to it.
        pay = work_out_pay(parts.days_to_pay(staff.pk, days), advances=line.pay.advances, carried=line.pay.carried)
        # Its own total, never the two parts' again: should the two ever differ, the lines wouldn't add up to it, and
        # nothing is kept.
        whole = replace(line, pay=pay, today=None, total=pay.total)
        (slip,) = _keep(first, None, [(whole, days)], advances_by_job(shop, first, last), by, ids=[payslip_id])
    return slip


def _locked_by(shop: Shop, by: StaffMember) -> tuple[list[StaffMember], StaffMember]:
    # The book's lock, every job of the shop, with who approves asked of their own row under it: Baba takes Meneja's key
    # away, or suspends him, while Meneja taps Idhinisha. Taking a key holds his job's row, which the lock waits for, so
    # asked only before it, the key he no longer holds would approve a month for good (AUTH-8's order, as set_pay_rate
    # keeps it). Asked before it too, so someone without a key sets nothing to work and holds nobody up.
    _ask_who_approves(by)
    jobs = lock_jobs(shop)
    by = next(job for job in jobs if job.pk == by.pk)
    _ask_who_approves(by)
    return jobs, by


def _ask_who_approves(by: StaffMember) -> None:
    for key in APPROVES:
        require(by, key, None)


def _refuse_before_an_approved_month(shop: Shop, month: dt.date, job: uuid.UUID | None = None) -> None:
    # Months are approved in order (A3), so one before an approved month is closed, with no payslip of its own or with
    # one: Juma's first day moved to 1 November, November approved, and the day moved back to October, whose days then
    # say he is owed. Nothing pays them by themselves: they are mended in a later month (WAGE-9).
    if is_closed(shop, month, job):
        raise ValidationError("A later month's pay is approved.", code="pay_run.later_month_approved")


def _refuse_if_stopped(stops: ToApprove) -> None:
    # What an approval waits for, one at a time, the first that holds: the earlier month first, as its days come first.
    # Each with what the page's sentence names; the sheet has shown them all already (ToApprove).
    if stops.earlier is not None:
        raise ValidationError(
            "An earlier month's pay is still open.",
            code="pay_run.earlier_month_open",
            params={"month": f"{stops.earlier:%Y-%m}"},
        )
    if stops.waiting:
        raise ValidationError(
            "A day still waits for a decision.", code="pay_run.days_waiting", params=_named(stops.waiting)
        )
    if stops.no_rate:
        raise ValidationError(
            "A day to pay has no daily rate.", code="pay_run.days_without_rate", params=_named(stops.no_rate)
        )


def _named(days: list[OpenDay]) -> dict[str, Any]:
    # How many such days there are, and the first of them: "Juma · Alhamisi 12/11".
    return {"count": len(days), "name": days[0].display_name, "date": days[0].date.isoformat()}


def _keep(
    month: dt.date,
    run: PayRun | None,
    lines: list[tuple[WorkerPay, list[AttendanceDay]]],
    given: Mapping[uuid.UUID, list[tuple[dt.date, Decimal]]],
    by: StaffMember,
    *,
    ids: Iterable[uuid.UUID] = (),
) -> list[Payslip]:
    # The payslips of a month, each worker's line with their days; their lines; and their days marked as paid. Each in
    # one statement, but the marks, one a worker. `ids`: the payslips' own, where the client made them.
    made = iter(ids)
    slips = [
        Payslip(
            id=next(made, None) or uuid.uuid7(),
            shop_id=by.shop_id,
            staff_id=line.staff_id,
            month=month,
            pay_run=run,
            total=line.total,
            created_by=by,
        )
        for line, _ in lines
    ]
    # An INSERT, as bulk_create always is: an id another row holds, or a payslip there is already, clashes on the
    # table's own rules, loudly, and never overwrites it (03 §5.4).
    Payslip.objects.bulk_create(slips)
    PayslipLine.objects.bulk_create(
        row
        for slip, (line, _) in zip(slips, lines, strict=True)
        for row in _payslip_lines(slip, line.pay, line.carried_from, given.get(line.staff_id, []), by)
    )
    for slip, (_, days) in zip(slips, lines, strict=True):
        # Every day the book answered of the job, the absent and the off ones too: they were paid nothing, and that is
        # as final. From here the table refuses any change of them (FrozenTrigger). The edit history keeps each mark,
        # with who approved (ADR-0036).
        AttendanceDay.objects.filter(pk__in=[day.pk for day in days]).update(payslip=slip)
        for day in days:
            if day._state.adding:
                # Today's, not kept yet: an INSERT, marked from its first moment.
                day.payslip = slip
                day.save(force_insert=True)
    return slips


def _payslip_lines(
    slip: Payslip, pay: Pay, carried_from: dt.date | None, given: list[tuple[dt.date, Decimal]], by: StaffMember
) -> list[PayslipLine]:
    # A worker's pay as the lines its payslip keeps, in the order the page lists them: what its days paid, then what
    # comes off, each with its minus, an advance a line. copy_negate, never a minus, which rounds to the digits the
    # thread keeps.
    kinds = {PaidAs.FULL: PayslipLineKind.FULL, PaidAs.HALF: PayslipLineKind.HALF}
    parts: list[dict[str, Any]] = [
        {"kind": kinds[line.paid_as], "days": line.days, "each": line.each, "amount": line.amount} for line in pay.lines
    ]
    if pay.fined_days:
        parts.append({"kind": PayslipLineKind.FINES, "days": pay.fined_days, "amount": pay.fines.copy_negate()})
    if pay.meal_days:
        parts.append({"kind": PayslipLineKind.MEALS, "days": pay.meal_days, "amount": pay.meals.copy_negate()})
    parts += [{"kind": PayslipLineKind.ADVANCE, "date": day, "amount": amount.copy_negate()} for day, amount in given]
    if carried_from is not None:
        parts.append({"kind": PayslipLineKind.CARRIED, "date": carried_from, "amount": pay.carried.copy_negate()})
    rows = [
        PayslipLine(shop_id=slip.shop_id, payslip=slip, position=position, created_by=by, **part)
        for position, part in enumerate(parts, start=1)
    ]
    if add_up(row.amount for row in rows) != slip.total:
        # Its lines are what a worker checks their pay by: a payslip they don't add up to is a bug in our code, and
        # nothing of the month is kept.
        raise ValueError("A payslip's lines don't add up to its total.")
    return rows
