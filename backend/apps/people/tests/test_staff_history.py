"""apps/people/tests/test_staff_history.py — a staff member's job keeps the history of its edits (03 §5.16,
ADR-0036).

The manager suspends Asha, then marks her as left. Each change writes two lines, one in each book of the audit
trail: the action with its reason (AuditEvent, test_staff_audit.py), and what changed in her row, written by
PostgreSQL's own trigger (EditEvent):

    who       before                               after
    Staff A   status: active                       status: suspended
    Staff A   status: suspended, left_on: (none)   status: left, left_on: 2026-10-01

A PIN reset shows as a new `pin_changed_at` only: the PIN's hash never leaves its column (03 §5.9). The office
visit that names who acts comes with the staff screen (PPL-4), so acting_as() opens it here, as the base view
will (apps/core/acting.py). Fake data only: the repo is public (03 §10).
"""

from datetime import date, datetime

import pytest

from apps.control.models import AuditEvent, EditEvent
from apps.core.acting import acting_as
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.services import add_staff, mark_left, set_pin, suspend
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


def history_of(staff: StaffMember) -> list[EditEvent]:
    # A job's history, oldest first: ids are UUIDv7, which follow the order they were made in (ADR-0007).
    return list(EditEvent.objects.filter(subject_type="staff", subject_id=staff.pk).order_by("id"))


def test_staff_edit_recorded_with_person(shop_a: Shop, asha: StaffMember, staff_a: StaffMember) -> None:
    with shop_context(shop_a), acting_as(staff_a):
        asha = suspend(asha, by=staff_a, reason="Hakuja kazini siku 3")
        mark_left(asha, left_on=LEFT_ON, by=staff_a, reason="Amehamia Moshi")
        edits = history_of(asha)
        lines = AuditEvent.objects.filter(subject_id=asha.pk).count()

    # Only what changed, each value as text: the leaving date as the API sends a date.
    assert [(edit.created_by_id, edit.before, edit.after) for edit in edits] == [
        (staff_a.pk, {"status": "active"}, {"status": "suspended"}),
        (staff_a.pk, {"status": "suspended", "left_on": None}, {"status": "left", "left_on": "2026-10-01"}),
    ]
    # And the other book: each action's line, with its reason.
    assert lines == 2


def test_pin_hash_never_copied_to_history(shop_a: Shop, asha: StaffMember, staff_a: StaffMember) -> None:
    with shop_context(shop_a), acting_as(staff_a):
        set_pin(asha, "4826", by=staff_a)
        [edit] = history_of(asha)
        asha = StaffMember.objects.get(pk=asha.pk)

    # The reset shows, with who did it and when the PIN changed, read back as the very time stored.
    assert edit.created_by_id == staff_a.pk
    assert edit.before == {"pin_changed_at": None}
    assert set(edit.after) == {"pin_changed_at"}
    assert datetime.fromisoformat(edit.after["pin_changed_at"]) == asha.pin_changed_at
    # The hash shows nowhere: not as a field, and not as a value.
    assert asha.pin_hash
    assert asha.pin_hash not in f"{edit.before} {edit.after}"
