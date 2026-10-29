"""apps/people/tests/test_staff_audit.py — a staff member's status changes are written to the audit trail
(02 §5, §13; T3).

Suspending someone, bringing them back and marking them as left each need a reason (rule 7). Each writes one
AuditEvent with it (apps/control/services.py, audit), in the action's own transaction, so the action and its
line are kept together or not at all:

    who       action            subject   reason                 before                 after
    Staff A   staff.suspend     Asha      Hakuja kazini siku 3   status: active         status: suspended
    Staff A   staff.unsuspend   Asha      Amerudi kazini         status: suspended      status: active
    (nobody)  staff.leave       Asha      Amehamia Moshi         status: active,        status: left,
                                                                 left_on: (none)        left_on: 2026-10-01

Every test works inside `shop_context(shop)`, as a visit will. Fake data only: the repo is public (03 §10).
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.control.models import AuditAction, AuditEvent
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, StaffStatus, User
from apps.people.services import add_staff, mark_left, suspend, unsuspend
from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

# Dates in the past: a leaving date can't be in the future.
START = date(2026, 3, 2)
LEFT_ON = date(2026, 10, 1)


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    user = User.objects.create_user(full_name="Asha Demo")
    with shop_context(shop_a):
        return add_staff(shop=shop_a, user=user, display_name="Asha", started_on=START, by=None)


def lines_about(staff: StaffMember) -> list[AuditEvent]:
    # The lines about one job, oldest first: ids are UUIDv7, which follow the order they were made in
    # (ADR-0007). "staff" is the job's type code (apps/core/links.py), which never changes once stored.
    return list(AuditEvent.objects.filter(subject_type="staff", subject_id=staff.pk).order_by("id"))


def test_suspend_writes_audit_event(shop_a: Shop, asha: StaffMember, staff_a: StaffMember) -> None:
    # The manager (Staff A) suspends Asha: one line, with who, why and what changed.
    with shop_context(shop_a):
        suspend(asha, by=staff_a, reason=" Hakuja kazini siku 3 ")
        [line] = lines_about(asha)
        assert AuditEvent.objects.count() == 1
        assert (line.action, line.created_by_id) == (AuditAction.STAFF_SUSPEND, staff_a.pk)
        # Trimmed: the reason is kept as the words, not the spaces around them.
        assert line.reason == "Hakuja kazini siku 3"
        assert (line.before, line.after) == ({"status": "active"}, {"status": "suspended"})
        # The line names Asha's job, and loads it back through the shop guard.
        assert line.subject == asha


def test_unsuspend_and_leave_write_audit_events(shop_a: Shop, asha: StaffMember, staff_a: StaffMember) -> None:
    with shop_context(shop_a):
        asha = suspend(asha, by=staff_a, reason="Hakuja kazini siku 3")
        asha = unsuspend(asha, by=staff_a, reason="Amerudi kazini")
        # by=None: the superuser marks her as left, and the superuser is nobody's staff (PPL-2).
        mark_left(asha, left_on=LEFT_ON, by=None, reason="Amehamia Moshi")
        lines = lines_about(asha)

    assert [(line.action, line.created_by_id, line.reason) for line in lines] == [
        (AuditAction.STAFF_SUSPEND, staff_a.pk, "Hakuja kazini siku 3"),
        (AuditAction.STAFF_UNSUSPEND, staff_a.pk, "Amerudi kazini"),
        (AuditAction.STAFF_LEAVE, None, "Amehamia Moshi"),
    ]
    assert (lines[1].before, lines[1].after) == ({"status": "suspended"}, {"status": "active"})
    # The leaving date is part of what changed, kept as text, as the API sends a date.
    assert (lines[2].before, lines[2].after) == (
        {"status": "active", "left_on": None},
        {"status": "left", "left_on": "2026-10-01"},
    )


def test_refused_action_writes_no_audit_event(shop_a: Shop, asha: StaffMember, staff_a: StaffMember) -> None:
    # A refused action writes no line, and a line that can't be written undoes its action: one transaction holds
    # both, so they are kept together or not at all.
    with shop_context(shop_a):
        # Refused by the action's own rules: Asha is active, so she can't be brought back; a reason of only
        # spaces; a leaving date ahead.
        with pytest.raises(ValidationError):
            unsuspend(asha, by=staff_a, reason="Amerudi kazini")
        with pytest.raises(ValidationError):
            suspend(asha, by=staff_a, reason="   ")
        with pytest.raises(ValidationError):
            mark_left(asha, left_on=date(2099, 1, 1), by=staff_a, reason="Atahamia Moshi")

        # Refused by the line itself: a reason longer than the trail keeps. The suspension it came with, already
        # saved inside the action's transaction, is undone with it.
        with pytest.raises(ValidationError) as refused:
            suspend(asha, by=staff_a, reason="a" * 501)
        assert [error.code for error in refused.value.error_dict["reason"]] == ["max_length"]

        assert StaffMember.objects.get(pk=asha.pk).status == StaffStatus.ACTIVE
        assert not AuditEvent.objects.exists()
