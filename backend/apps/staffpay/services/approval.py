"""apps/staffpay/services/approval.py — approving a month's pay (WAGE-3; 02 §12, A3): the one moment it is kept.

    1 Dec, Baba reads November, 432,000 for three workers, and approves it:
        PayRun Novemba, by Baba
        Payslip Asha 152,000, Baraka 148,000, Juma 132,000, each with its lines, added up to the very total he read
        and each of their days of November marked as paid, which nothing changes from then on

What is kept is what the page showed (pay.py), worked out once more inside the book's lock, so no part of it moves
between the reading and the keeping; and only if every total is still the one the person saw. Refused while anything
would be missing from it: a day that waits (Jack: A), a day with no rate, an earlier month still open, a month not over.
Never undone: a mistake found later is an adjustment in a later month (A3, WAGE-9). Handing out the money is WAGE-9's.

No line in the change log, here or on any of the rows: no laptop keeps a payslip (03 §6.1).
"""

import datetime as dt
import uuid
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.permissions import Permission
from apps.core.tenancy import ShopMismatch
from apps.people.models import StaffMember
from apps.people.permissions import require
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.calculations import PaidAs, Pay, add_up
from apps.staffpay.models import AttendanceDay, PayRun, Payslip, PayslipLine, PayslipLineKind
from apps.staffpay.selectors import advances_by_job
from apps.staffpay.services.book import lock_jobs, month_span
from apps.staffpay.services.pay import OpenDay, ToApprove, WorkerPay, draft_of, read_parts, run_of, what_stops

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
    pay on the whole shop. Refuses: a month approved already (pay_run.already_approved), one not over yet
    (pay_run.month_not_over), one with nobody to pay (pay_run.nobody), one while an earlier month is open
    (pay_run.earlier_month_open), a day that waits for a decision (pay_run.days_waiting), a day to pay with no rate
    (pay_run.days_without_rate), and totals that are no longer those seen (pay_run.totals_moved). The shop must be open.
    Returns the run as saved."""
    # A job of another shop approving this shop's pay is a bug in the calling code (T1), never a person's mistake: the
    # route finds both in the one shop open. A server error, before anything is read.
    if by.shop_id != shop.pk:
        raise ShopMismatch("approve_month was given a person of another shop.")
    first, last = month_span(month)
    with transaction.atomic():
        # First, so someone without a key sets nothing to work; read afresh, so one taken away a moment ago counts.
        _ask_who_approves(by)
        # The book's lock, before anything the pay is made of is read, and held until the run is kept: a decision, a
        # tap, a rate, an advance or meal money sent now waits, and then finds the month approved. And two people
        # approving at once take turns here: the second finds the run.
        lock_jobs(shop)
        if run_of(shop, first) is not None:
            raise ValidationError("This month's pay is approved already.", code="pay_run.already_approved")
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
            run,
            [line for line in draft.workers if line.approval is None],
            parts.over,
            advances_by_job(shop, first, last),
            by,
        )
    return run


def _ask_who_approves(by: StaffMember) -> None:
    for key in APPROVES:
        require(by, key, None)


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
    run: PayRun,
    lines: list[WorkerPay],
    days: Mapping[uuid.UUID, Iterable[AttendanceDay]],
    given: Mapping[uuid.UUID, list[tuple[dt.date, Decimal]]],
    by: StaffMember,
) -> None:
    # The payslips of a month, their lines, and their days marked as paid. Each in one statement, but the marks, one a
    # worker.
    slips = {
        line.staff_id: Payslip(
            shop_id=run.shop_id, staff_id=line.staff_id, month=run.month, pay_run=run, total=line.total, created_by=by
        )
        for line in lines
    }
    Payslip.objects.bulk_create(slips.values())
    PayslipLine.objects.bulk_create(
        row
        for line in lines
        for row in _payslip_lines(slips[line.staff_id], line.pay, line.carried_from, given.get(line.staff_id, []), by)
    )
    for job, slip in slips.items():
        # Every day the book answered of the job, the absent and the off ones too: they were paid nothing, and that is
        # as final. From here the table refuses any change of them (FrozenTrigger). The edit history keeps each mark,
        # with who approved (ADR-0036).
        AttendanceDay.objects.filter(pk__in=[day.pk for day in days.get(job, [])]).update(payslip=slip)


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
