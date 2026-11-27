"""apps/staffpay/services/correction.py — a mistake found after a month's pay was approved, put right in a later
month's pay (WAGE-10, 02 §12, A3): Marekebisho.

Baba approves November on 1 December. On the 3rd he finds Juma's November was 9,000 short: a day he came was counted
absent. November never changes (A3), as Juma may already hold its cash, so Baba opens Juma's December and adds + 9,000,
"Novemba: siku ya 12/11 haikuhesabiwa" (record_correction). December's pay adds it, and its payslip keeps it as a line
of its own once December is approved, so both months say what they paid. One typed wrong is crossed out, with who,
when and why, and typed again (void_correction).

Only whoever approves pay types or crosses out one (Jack: A): pay.approve with the two keys of pay, on the whole shop,
the keys of the approval itself (APPROVES), as a correction changes what a worker is owed with no cash to show for it,
unlike an advance. Never on one's own pay, by the person. None for one who left whose pay is approved: no later pay of
theirs will be made, so the owner pays them by hand (Jack: A).

A file of its own, as it asks the approval's keys (approval.py), and money.py, which the month's pay reads (pay.py),
can't take from the approval without a circle. No line in the change log: pay never sits on a shared device (03 §6.1).
"""

import datetime as dt
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.tenancy import ShopMismatch
from apps.people.models import StaffMember
from apps.people.permissions import require
from apps.shops.models import Shop
from apps.staffpay.models import MOST_CORRECTION, PayCorrection
from apps.staffpay.selectors import why_no_correction
from apps.staffpay.services.approval import APPROVES
from apps.staffpay.services.book import refuse_if_closed
from apps.staffpay.services.money import DEMO_MONEY_VOID_REASONS

# On the demo, the ready reasons a correction is typed with, kept as their codes, which the page says in words: *Siku
# haikuhesabiwa* (a day the pay left out) and *Alilipwa zaidi* (paid too much). Every visitor logs in as the same
# Meneja (OPS-3), so a reason typed would show to every visitor after, signed by the shared manager, until the
# morning's seed. One crossed out takes Advansi's ready reason, *Kiasi kimekosewa* (DEMO_MONEY_VOID_REASONS).
DEMO_CORRECTION_REASONS = ("day_not_counted", "paid_too_much")
DEMO_CORRECTION_VOID_REASONS = DEMO_MONEY_VOID_REASONS


def record_correction(
    staff: StaffMember, *, correction_id: uuid.UUID, month: dt.date, amount: Decimal, reason: str, by: StaffMember
) -> PayCorrection:
    """Put right a mistake of a month already approved in a month still open (WAGE-10, 02 §12): Juma's November 9,000
    short, + 9,000 in his December. `month`: any day of the month whose pay takes it, the one whose page it is typed
    on. `amount`: what it adds (above 0) or takes off (below 0). `correction_id`: the client's (ADR-0007), so the
    route answers a request sent twice with the row it made (CreateOnceMixin). `by`: who types it, with pay.approve
    and the two keys of pay on the whole shop, never the worker themself. Refuses, for the whole request, as the page
    offers none of these: one's own (correction.own); one who left whose pay is approved (correction.left_paid); a
    month to come (correction.month_to_come); one the job didn't run in (correction.outside_job); a worker with no
    daily pay in that month (correction.not_paid_by_day); one whose pay is approved (pay.day_approved). And, beside
    their boxes, all together: an amount of 0 or with cents (correction.amount_invalid), or past ten million either
    way (correction.amount_too_big); no reason (correction.reason_missing), or on the demo a reason not a ready one
    (demo.ready_reasons). Returns the row as saved."""
    # A job of another shop correcting this shop's pay is a bug in the calling code (T1), never a person's mistake: the
    # route finds both in the one shop open. A server error, before anything is read.
    if by.shop_id != staff.shop_id:
        raise ShopMismatch("record_correction was given a person of another shop.")
    first = month.replace(day=1)
    # Spaces around a reason say nothing, and "  " is no reason.
    reason = reason.strip()
    # Not a recording_changes block: a correction writes no line in the change log, as no laptop gets one (03 §6.1).
    with transaction.atomic():
        by, staff = _locked(by, staff)
        # Never one's own (Jack: A): a manager who approves pay alone in the shop would raise their own on their own
        # word. By the person, not the job: someone hired again (PPL-11) has two jobs, and neither's is theirs to mend.
        if staff.user_id == by.user_id:
            raise ValidationError("Nobody corrects their own pay.", code="correction.own")
        shop = Shop.objects.get(pk=staff.shop_id)
        # What the page never offers, one at a time, the first that holds: each says the month takes no correction for
        # this worker, so there is no box to name. Read under the job's lock, one of those the approval takes: one
        # typed while Baba approves December waits, and then finds it approved.
        _refuse_the_month(shop, staff, first)
        # The boxes, all together, so a person who got two wrong sees both at once, each beside its own (ADR-0040).
        errors: dict[str, list[ValidationError]] = {}
        # As the table's rules hold: named here, beside the amount's box, where the table's own would name the whole
        # row. to_integral_value() drops the places without rounding the check away: 9000.50 is not whole.
        if amount == 0 or amount != amount.to_integral_value():
            errors["amount"] = [
                ValidationError("A correction is a whole amount, never 0.", code="correction.amount_invalid")
            ]
        elif abs(amount) > MOST_CORRECTION:
            errors["amount"] = [
                ValidationError("A correction is at most ten million.", code="correction.amount_too_big")
            ]
        if not reason:
            errors["reason"] = [ValidationError("A correction says why.", code="correction.reason_missing")]
        elif settings.DEMO_SEED and reason not in DEMO_CORRECTION_REASONS:
            errors["reason"] = [ValidationError("On the demo, pick a ready reason.", code="demo.ready_reasons")]
        if errors:
            raise ValidationError(errors)
        row = PayCorrection(
            id=correction_id,
            shop_id=staff.shop_id,
            staff=staff,
            month=first,
            amount=amount,
            reason=reason,
            created_by=by,
        )
        # The row's own checks last, as a guard on what the boxes above already asked: a reason too long, an id taken.
        row.full_clean()
        # An INSERT, never an UPDATE: an id another row holds clashes, loudly, and never overwrites it (03 §5.4).
        row.save(force_insert=True)
    return row


def void_correction(correction: PayCorrection, *, reason: str, by: StaffMember) -> PayCorrection:
    """Cross out a correction typed wrong (WAGE-10, 02 §12, T2): + 90,000 for + 9,000, "Kiasi kimekosewa". The row
    stays, voided once with who, when and why, and counts for nothing; the right one is typed again. Never brought
    back. `by`: who crosses it out, with the keys that type one, whoever typed it, and never the worker it corrects. A
    row crossed out already, by this request sent twice or by someone a moment before, is answered as it was crossed
    out, never stamped again (CORE-3's Watch out). Refuses: one's own (correction.own); one of a month whose pay is
    approved (pay.day_approved), as its payslip holds it; and, beside the reason's box, no reason
    (correction.reason_missing), or on the demo a reason not the ready one (demo.ready_reasons). Returns the row as
    saved."""
    # Who voids is a staff member of the row's own shop (T1): the void rule in the database checks only that the stamp
    # is filled whole, so this is the check it can't make with one column.
    if by.shop_id != correction.shop_id:
        raise ShopMismatch("void_correction was given a person of another shop.")
    reason = reason.strip()
    with transaction.atomic():
        by, staff = _locked(by, StaffMember.objects.get(pk=correction.staff_id))
        # Never one's own (Jack: A): crossing out a deduction raises one's own pay. By the person, as typing one is.
        if staff.user_id == by.user_id:
            raise ValidationError("Nobody crosses out a correction of their own pay.", code="correction.own")
        # Read afresh under the lock: one crossed out already is answered as it is, whatever was approved since. One
        # still counting, of a month approved, is a line of its payslip now, and stays (A3).
        if PayCorrection.objects.get(pk=correction.pk).voided_at is None:
            refuse_if_closed(Shop.objects.get(pk=correction.shop_id), correction.month, correction.staff_id)
        if not reason:
            raise ValidationError(
                {"reason": [ValidationError("A correction crossed out says why.", code="correction.reason_missing")]}
            )
        if settings.DEMO_SEED and reason not in DEMO_CORRECTION_VOID_REASONS:
            raise ValidationError(
                {"reason": [ValidationError("On the demo, pick the ready reason.", code="demo.ready_reasons")]}
            )
        # The stamp, filled once, by one guarded UPDATE, as an advance's (void_advance): only while the row is not
        # crossed out, so two voids never both write it. Never save(), which AppendOnly refuses; the void trigger lets
        # this UPDATE change the stamp and nothing else (ADR-0021).
        PayCorrection.objects.filter(pk=correction.pk, voided_at__isnull=True).update(
            voided_at=timezone.now(), voided_by=by, void_reason=reason
        )
        # Read back as it is now: crossed out by this request, or by the same one sent before, its answer lost, or by
        # someone a moment before, whose stamp the page is then shown.
        return PayCorrection.objects.get(pk=correction.pk)


def ready_correction_reasons() -> list[str]:
    # The ready reasons a correction is typed with, on the demo alone; anywhere else the person's own words.
    return list(DEMO_CORRECTION_REASONS) if settings.DEMO_SEED else []


def ready_correction_void_reasons() -> list[str]:
    # The same for crossing one out.
    return list(DEMO_CORRECTION_VOID_REASONS) if settings.DEMO_SEED else []


def _locked(by: StaffMember, staff: StaffMember) -> tuple[StaffMember, StaffMember]:
    # Who acts, asked before anything is locked, so someone without a key sets nothing to work and holds nobody up; then
    # their own row and the job's, locked, and asked again of their own row: Baba takes Meneja's key away while Meneja
    # taps Hifadhi. Taking a key holds Meneja's job's row, which this waits for, so asked only before it, a key he no
    # longer holds would correct a pay for good (AUTH-8's order, as the approval keeps it). The job's row as it is now,
    # as its first or last day may have just moved (PPL-10), and as the approval of a month locks every job (WAGE-3).
    # Both in the order of their ids, the order the approval's lock takes them (lock_jobs): taken the other way round,
    # this and an approval could each hold one row the other waits for. FOR NO KEY UPDATE, the light lock (backend
    # rules).
    _ask_who_corrects(by)
    rows = {
        row.pk: row
        for row in StaffMember.objects.filter(pk__in={by.pk, staff.pk}).order_by("pk").select_for_update(no_key=True)
    }
    by, staff = rows[by.pk], rows[staff.pk]
    _ask_who_corrects(by)
    return by, staff


def _ask_who_corrects(by: StaffMember) -> None:
    # The approval's own keys, on the whole shop (Jack: A).
    for key in APPROVES:
        require(by, key, None)


def _refuse_the_month(shop: Shop, staff: StaffMember, first: dt.date) -> None:
    # What the page never offers, the first that holds: the one rule the page reads too (why_no_correction), so the two
    # never disagree.
    code = why_no_correction(shop, staff, first)
    if code is not None:
        raise ValidationError(_WHY_NOT[code], code=code)


# Each refusal's words, for the logs and the tests: the page says its own, by the code (ADR-0040).
_WHY_NOT = {
    "correction.left_paid": "This worker left, and their pay is approved.",
    "correction.month_to_come": "A correction is never of a month to come.",
    "correction.outside_job": "A correction is of a month the worker had this job.",
    "correction.not_paid_by_day": "This worker has no daily pay in this month.",
    "pay.day_approved": "The pay of this day is approved.",
}
