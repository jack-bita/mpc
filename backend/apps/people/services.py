"""apps/people/services.py — every write to the people tables, one function per action (ADR-0015).

For now a staff member's working life at one shop (02 §5): they are added, suspended, brought back and
marked as left; their PIN joins in the next step. Each action runs in one transaction, checks that every
row it links to belongs to the same shop (T1), and refuses a broken rule with a ValidationError that
carries a code (ADR-0032); CORE-6's error handler will turn it into the API's error shape.

Callers open shop_context(shop) first: full_clean and the unique checks read through the guarded
`objects` (CORE-2).
"""

import uuid
from datetime import date
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.people.models import StaffMember, StaffStatus, User
from apps.shops.models import Shop


def _check_same_shop(shop_id: uuid.UUID, by: StaffMember | None) -> None:
    # T1: a row of shop A only points at rows of shop A. The guard watches reads, not writes (CORE-2),
    # so a manager of shop B named here would get past it.
    if by is not None and by.shop_id != shop_id:
        raise ValidationError("The person acting belongs to another shop.", code="staff.other_shop")


def add_staff(
    *,
    shop: Shop,
    user: User,
    display_name: str,
    job_title: str = "",
    started_on: date | None = None,
    by: StaffMember | None,
) -> StaffMember:
    """Give a person a job at a shop. `by`: who adds them; None for the system or the superuser."""
    _check_same_shop(shop.pk, by)
    if started_on is None:
        # Today in the shop's own time zone (02 §1), not the server's UTC.
        started_on = timezone.localdate(timezone=ZoneInfo(shop.timezone))
    staff = StaffMember(shop=shop, user=user, display_name=display_name, job_title=job_title, started_on=started_on)
    with transaction.atomic():
        # Every field, clean() and the rules in Meta, before anything is written: a clash comes back
        # as a code. Two adds at the very same moment can both pass this; the database's unique
        # index then refuses the second.
        staff.full_clean()
        staff.save()
    return staff


def _check_reason(reason: str) -> None:
    # Rule 7: a suspension or a leaving is always recorded with who, when and why. CTRL-2 writes the
    # reason to the audit trail; until then nothing calls these actions (the staff screen is PPL-4).
    if not reason.strip():
        raise ValidationError("A reason is required.", code="staff.reason_required")


def _locked(staff: StaffMember) -> StaffMember:
    # The row read again, and locked until the transaction ends (SELECT ... FOR UPDATE). Two managers
    # acting on Asha at the same moment take turns, and the second sees what the first one wrote, not
    # the old copy on their screen.
    return StaffMember.objects.select_for_update().get(pk=staff.pk)


def suspend(staff: StaffMember, *, by: StaffMember | None, reason: str) -> StaffMember:
    """Stop an active person working for a while. Their PIN stops working (AUTH-4)."""
    _check_same_shop(staff.shop_id, by)
    _check_reason(reason)
    with transaction.atomic():
        staff = _locked(staff)
        if staff.status != StaffStatus.ACTIVE:
            raise ValidationError("Only an active staff member can be suspended.", code="staff.not_active")
        staff.status = StaffStatus.SUSPENDED
        staff.full_clean()
        staff.save(update_fields=["status"])
    return staff


def unsuspend(staff: StaffMember, *, by: StaffMember | None, reason: str) -> StaffMember:
    """Let a suspended person work again."""
    _check_same_shop(staff.shop_id, by)
    _check_reason(reason)
    with transaction.atomic():
        staff = _locked(staff)
        if staff.status != StaffStatus.SUSPENDED:
            raise ValidationError("Only a suspended staff member can come back.", code="staff.not_suspended")
        staff.status = StaffStatus.ACTIVE
        staff.full_clean()
        staff.save(update_fields=["status"])
    return staff


def mark_left(staff: StaffMember, *, left_on: date, by: StaffMember | None, reason: str) -> StaffMember:
    """Record that a person left on `left_on`. Final: if they come back, add_staff gives them a new job."""
    _check_same_shop(staff.shop_id, by)
    _check_reason(reason)
    with transaction.atomic():
        staff = _locked(staff)
        if staff.status == StaffStatus.LEFT:
            raise ValidationError("This person has already left.", code="staff.left")
        staff.status = StaffStatus.LEFT
        staff.left_on = left_on
        # The rules in Meta refuse a leaving date before the start date (staff.left_before_start).
        staff.full_clean()
        staff.save(update_fields=["status", "left_on"])
    return staff
