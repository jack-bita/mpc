"""apps/control/tests/test_audit.py — tests for the audit trail's first book: what a person did, and why
(02 §13, 03 §5.16).

A service that does an important action writes one AuditEvent with it, in the same transaction:

    when          who       action          subject      reason                 before → after
    29 Oct 10:15  Staff A   staff.suspend   Asha's job   Hakuja kazini siku 3   active → suspended

Nobody edits or deletes a line, in Python or in PostgreSQL (T2, ADR-0021). The people tests prove that the
staff actions write theirs (apps/people/tests/test_staff_audit.py). `control` may not import `people`
(ADR-0035), not even in its tests, so here the test-only probe Note stands in for Asha's staff row, with a type
code of its own for the length of each test (apps/core/links.py). The staff come from backend/conftest.py,
typed by what they are to `control`: Actors. Fake data only: the repo is public (03 §10).
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Model
from django.db.transaction import TransactionManagementError

from apps.control.models import AuditAction, AuditEvent
from apps.control.services import audit
from apps.core.links import LINK_TYPES
from apps.core.models import AppendOnlyError
from apps.core.tenancy import Actor, ShopMismatch, shop_context
from tests.probe.models import Note

pytestmark = pytest.mark.django_db

REASON = "Hakuja kazini siku 3"


@pytest.fixture(autouse=True)
def note_has_a_code(monkeypatch: pytest.MonkeyPatch) -> None:
    # monkeypatch puts the list back as it was after each test, so the code never reaches the real list.
    monkeypatch.setitem(LINK_TYPES, "probe_note", "probe.Note")


@pytest.fixture
def asha_job(shop_a: Model) -> Note:
    # Stands in for Asha's staff row (apps/people/models.py, StaffMember).
    note = Note(shop_id=shop_a.pk, text="Asha, muuzaji")
    note.save()
    return note


def write_line(
    subject: Note,
    *,
    by: Actor | None,
    reason: str = REASON,
    action: AuditAction = AuditAction.STAFF_SUSPEND,
    **changes: Any,
) -> AuditEvent:
    # As a service writes it: inside the action's own transaction, which audit() needs.
    with transaction.atomic():
        return audit(action=action, subject=subject, reason=reason, by=by, **changes)


def test_audit_records_who_what_and_why(shop_a: Model, asha_job: Note, staff_a: Actor) -> None:
    # One line: who acted (`created_by`), when (`created_at`), what (`action`), on which row (a type code and
    # its UUID), why, and what changed. The reason is trimmed, as a flag's note is.
    with shop_context(shop_a):
        written = write_line(
            asha_job, by=staff_a, reason=f"  {REASON} ", before={"status": "active"}, after={"status": "suspended"}
        )
        line = AuditEvent.objects.get(pk=written.pk)
        assert (line.shop_id, line.created_by_id, line.action) == (shop_a.pk, staff_a.staff_id, "staff.suspend")
        assert (line.subject_type, line.subject_id, line.reason) == ("probe_note", asha_job.pk, REASON)
        assert (line.before, line.after) == ({"status": "active"}, {"status": "suspended"})
        assert line.created_at is not None
        # The row it is about loads back from its two columns, through the shop guard.
        assert line.subject == asha_job

        # The system acts too, in a nightly job: nobody is named. Money and dates are kept as text, as the API
        # sends them, so a price change (CTRL-5) is never read back as a float (ADR-0024).
        written = write_line(asha_job, by=None, before={"price": Decimal("1500.00")}, after={"on": date(2026, 10, 29)})
        line = AuditEvent.objects.get(pk=written.pk)
        assert line.created_by_id is None
        assert (line.before, line.after) == ({"price": "1500.00"}, {"on": "2026-10-29"})


@pytest.mark.parametrize(
    ("reason", "code"),
    [("", "audit.reason_required"), ("   ", "audit.reason_required"), ("a" * 501, "max_length")],
    ids=["empty", "spaces", "too_long"],
)
def test_audit_needs_a_reason(shop_a: Model, asha_job: Note, staff_a: Actor, reason: str, code: str) -> None:
    # T3: an action is kept with who, when and why. Spaces alone say no more than nothing. Each problem with the
    # words is filed under their field, `reason`, so a screen shows it beside the box they were typed in
    # (03 §5.10): no words at all, or more than the trail keeps.
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            write_line(asha_job, by=staff_a, reason=reason)
        assert [error.code for error in refused.value.error_dict["reason"]] == [code]
        assert not AuditEvent.objects.exists()


def test_audit_stays_in_one_shop(shop_a: Model, shop_b: Model, asha_job: Note, staff_b: Actor) -> None:
    # T1: a line, and every row it links to, belong to one shop. Each of these is a bug in the calling code,
    # refused before anything is written.
    with shop_context(shop_a):
        # Shop B's staff member acting on shop A's row.
        with pytest.raises(ShopMismatch):
            write_line(asha_job, by=staff_b)
        # A row never saved: a generic link has no foreign key, so nothing else would notice it points at nothing.
        with pytest.raises(ValueError, match="saved"):
            write_line(Note(shop_id=shop_a.pk, text="Bado"), by=None)
    # Shop B's visit can't write a line about shop A's row.
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        write_line(asha_job, by=staff_b)

    with shop_context(shop_a):
        assert not AuditEvent.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_audit_needs_a_transaction(shop_a: Model, asha_job: Note, staff_a: Actor) -> None:
    # An action and its line are kept together or not at all: a suspension kept without its reason, or a reason
    # kept for a suspension that was undone, would each tell a false story. So audit() runs only inside the
    # action's own transaction. This test runs without the transaction pytest wraps every other test in
    # (transaction=True), so the call below really is outside one; its tables are emptied afterwards, which the
    # append-only trigger allows (apps/core/operations.py).
    with shop_context(shop_a):
        with pytest.raises(TransactionManagementError, match="transaction"):
            audit(action=AuditAction.STAFF_SUSPEND, subject=asha_job, reason=REASON, by=staff_a)
        assert not AuditEvent.objects.exists()


def test_unknown_audit_action_refused(shop_a: Model, asha_job: Note) -> None:
    # One list of actions (AuditAction), so the owner's trail (CTRL-5) never meets one it can't name.
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            write_line(asha_job, by=None, action="staff.fire")  # type: ignore[arg-type]
        assert [error.code for error in refused.value.error_dict["action"]] == ["invalid_choice"]
        assert not AuditEvent.objects.exists()


@pytest.mark.parametrize(
    ("rule", "changes"),
    [
        # An action no screen knows: audit() refuses it first (invalid_choice).
        ("control_auditevent_action_known", {"action": "staff.fire"}),
        # A line with no why: audit() trims and refuses it first (audit.reason_required).
        ("control_auditevent_reason_not_blank", {"reason": ""}),
        # A table's code with a capital and a space: link_type_of hands out codes from the list only.
        ("control_auditevent_subject_type_shape", {"subject_type": "Probe Note"}),
    ],
    ids=["unknown_action", "blank_reason", "bad_type_code"],
)
def test_database_refuses_bad_audit_rows(asha_job: Note, rule: str, changes: dict[str, str]) -> None:
    # audit() refuses each of these before the database is asked, so no other test reaches the database's own
    # rule: dropped from the migration, it would leave every test green. Here the row is saved directly, as a bug
    # or SQL typed by hand would, past audit() and every check: the database is the last guard (03 §5.6).
    row = {
        "shop_id": asha_job.shop_id,
        "action": AuditAction.STAFF_SUSPEND,
        "subject_type": "probe_note",
        "subject_id": asha_job.pk,
        "reason": REASON,
    } | changes
    with pytest.raises(IntegrityError, match=rule), transaction.atomic():
        AuditEvent(**row).save()


def test_audit_rows_append_only(shop_a: Model, asha_job: Note, staff_a: Actor) -> None:
    # T2: nobody edits or deletes a line, in Python or in PostgreSQL (ADR-0021). The manager's reason stays as
    # written, whoever reads the trail later.
    with shop_context(shop_a):
        line = write_line(asha_job, by=staff_a)

    line.reason = "Alichelewa mara moja"
    with pytest.raises(AppendOnlyError):
        line.save()
    with pytest.raises(AppendOnlyError):
        line.delete()
    # Plain SQL, which no model code sees: only the trigger is left to refuse it. (The table's name comes from
    # the model, not from outside, so building the SQL with it is safe; the values are parameters.)
    table = AuditEvent._meta.db_table
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET reason = %s WHERE id = %s", ["Alichelewa mara moja", line.pk])
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", [line.pk])

    line.refresh_from_db()
    assert line.reason == REASON
