"""apps/control/services.py — every write to the control tables, one function per action (ADR-0015): the flags,
and the audit trail.

raise_flag writes a flag with the people it names, all or nothing. The other three move it forward, each
with a note in a person's own words, who and when kept with it (Jack, 29 Oct 2026; 02 v1.8):

    open ──explain_flag──▶ explained ──resolve_flag / dismiss_flag──▶ resolved | dismissed   (final)
      └────────────────────resolve_flag / dismiss_flag─────────────────▶

explain_flag may be called again and again: each person a flag names may explain it, and every explanation
is kept. Each step names the person who took it: a flag is raised by the system as often as not, but only a
person explains or closes one, and never one who is named on it. Nothing moves a flag back, and nothing
touches a closed one.

audit() writes one line of the audit trail (03 §5.16): who did what to which row, what it changed, and why. The
service that does the action calls it inside its own transaction, so the action and its line are kept together
or not at all.

A broken rule is a ValidationError with a code (ADR-0032), which the API's error handler
(apps/core/api/errors.py) will turn into its error shape when the review screen comes (CTRL-4); a bug in the
calling code, such as a row of another shop, is ShopMismatch, a server error.

`control` is layer 0 and may import only `core` (ADR-0035), so the services can't name a Side or a
StaffMember. The caller passes in what they need, as ADR-0035 says: the subject and the side as rows
(ShopScoped), the people and who acts as Actors (apps/core/tenancy.py), anything with a `shop_id` and a
`staff_id`, as a staff member has. So each T1 check compares shop ids, with no query.

Callers open shop_context(shop) first, or system_context() in a nightly job: full_clean and the unique
checks read through the guarded `objects` (CORE-2).
"""

import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection, models, transaction
from django.db.transaction import TransactionManagementError

from apps.control.models import AuditAction, AuditEvent, Flag, FlagKind, FlagNote, FlagPerson, FlagStatus, FlagStep
from apps.core.links import link_type_of
from apps.core.models import ShopScoped
from apps.core.tenancy import ALL_SHOPS, Actor, ShopMismatch, current_shop

# A flag in one of these takes no more notes: it is closed for good.
_CLOSED = {FlagStatus.RESOLVED, FlagStatus.DISMISSED}


def raise_flag(
    *,
    kind: FlagKind,
    subject: ShopScoped,
    expected: Decimal | None = None,
    actual: Decimal | None = None,
    side: ShopScoped | None = None,
    people: Sequence[Actor] = (),
    by: Actor | None,
) -> Flag:
    """Write a flag about `subject`, a saved row of the shop the flag belongs to: what should be there
    (`expected`) and what is (`actual`), both or neither; the side it belongs to, if any; and the staff
    members it names. `by`: who acts as it is raised; None when the system raises it, as it mostly does
    (posting a device's records, a nightly check)."""
    # The flag belongs to its subject's shop: a drawer's day of shop A gets a flag of shop A.
    shop_id = subject.shop_id
    _check_shop(shop_id, by)
    # A generic link has no foreign key, so the database can't check that it points at a row: an unsaved
    # one would leave the flag pointing at nothing. `_state.adding` is Django's own flag on a row object:
    # True until it is saved (apps/core/models.py, AppendOnly.save).
    if subject._state.adding:
        raise ValueError(f"A flag's subject must be a saved row; this {type(subject).__name__} was never saved.")
    # T1: the side belongs to the flag's shop. full_clean then checks it is a side at all: the id of a row
    # of another table is not one of shops_side's.
    if side is not None and side.shop_id != shop_id:
        raise ShopMismatch("The side belongs to another shop than the flag.")
    staff_ids = _staff_ids(shop_id, people)
    created_by_id = None if by is None else by.staff_id

    flag = Flag(
        shop_id=shop_id,
        kind=kind,
        # UnknownLinkType when the subject's table has no code yet: the card that raises flags about it adds
        # one (apps/core/links.py).
        subject_type=link_type_of(subject),
        subject_id=subject.pk,
        expected=expected,
        actual=actual,
        side_id=None if side is None else side.pk,
        created_by_id=created_by_id,
    )
    # One transaction, so a flag never exists without the people it names.
    with transaction.atomic():
        _saved(flag)
        for staff_id in staff_ids:
            _saved(FlagPerson(shop_id=shop_id, flag=flag, staff_id=staff_id, created_by_id=created_by_id))
    return flag


def explain_flag(flag: Flag, *, text: str, by: Actor, note_id: uuid.UUID | None = None) -> Flag:
    """Say why the difference happened. The first explanation moves an open flag to explained; each person
    the flag names may add their own, and all are kept. `note_id`: the id the phone made for the note
    (ADR-0007), if it made one, so the same request sent twice writes it once."""
    return _step(flag, FlagStep.EXPLAINED, text=text, by=by, note_id=note_id)


def resolve_flag(flag: Flag, *, text: str, by: Actor, note_id: uuid.UUID | None = None) -> Flag:
    """Close the flag: a real difference, dealt with ("Asha will pay the 3,000 tomorrow"). Straight from open
    too, when a manager finds the reason themselves. `note_id` as for explain_flag."""
    return _step(flag, FlagStep.RESOLVED, text=text, by=by, note_id=note_id)


def dismiss_flag(flag: Flag, *, text: str, by: Actor, note_id: uuid.UUID | None = None) -> Flag:
    """Close the flag: no real problem after all ("the money was under the drawer's tray"). `note_id` as for
    explain_flag."""
    return _step(flag, FlagStep.DISMISSED, text=text, by=by, note_id=note_id)


def audit(
    *,
    action: AuditAction,
    subject: ShopScoped,
    reason: str,
    by: Actor | None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Write down that `by` did `action` to `subject`, a saved row of the open shop, and why. `before` and
    `after`: the fields the action changed, as they were and as they are ({"status": "active"} →
    {"status": "suspended"}). `by`: who acted; None when the system did, or the superuser. Call it inside the
    action's own transaction, after the change is saved."""
    # The action and its line are kept together or not at all: a suspension kept without its line, or a line kept
    # for a suspension that was undone, would each tell a false story. Django is inside a transaction exactly
    # when it is inside an atomic block (its default, autocommit, runs each query as its own), so a caller that
    # forgot one is a bug, refused before anything is written.
    if not connection.in_atomic_block:
        raise TransactionManagementError("audit() runs inside the action's own transaction (transaction.atomic()).")
    # The line belongs to its subject's shop: shop A's staff member gets a line of shop A.
    shop_id = subject.shop_id
    _check_shop(shop_id, by)
    # A generic link has no foreign key, so the database can't check that it points at a row (as in raise_flag).
    if subject._state.adding:
        raise ValueError(f"An audit line's subject must be a saved row; this {type(subject).__name__} was never saved.")
    # T3: always why. Trimmed first: spaces alone say no more than nothing, and the database would take them.
    # Filed under the words' field, `reason`, as full_clean files words too long for it.
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": ValidationError("A reason is required.", code="audit.reason_required")})
    # ADR-0024: amounts are Decimal, never float. A float is stored as a JSON number and read back as a float,
    # already off (0.1 + 0.2 is 0.30000000000000004), so a price change's line would show the owner a wrong price.
    # Refused at any depth, before anything is written: a bug in the calling code, so a TypeError, not a code.
    if _holds_a_float(before) or _holds_a_float(after):
        raise TypeError("audit() keeps amounts as Decimal, never float (ADR-0024).")
    return _saved(
        AuditEvent(
            shop_id=shop_id,
            action=action,
            # UnknownLinkType when the subject's table has no code yet: the card that audits its rows adds one
            # (apps/core/links.py).
            subject_type=link_type_of(subject),
            subject_id=subject.pk,
            before=before,
            after=after,
            reason=reason,
            created_by_id=None if by is None else by.staff_id,
        )
    )


def _step(flag: Flag, step: FlagStep, *, text: str, by: Actor, note_id: uuid.UUID | None) -> Flag:
    # The one way a flag moves: a note, then the status the note's step names. Every step keeps who
    # (`created_by`), when (`created_at`) and why (the note): rule 7.
    _check_shop(flag.shop_id, by)
    # Who is always a person. A note is never edited (ADR-0021), so one written with no name would stay
    # nameless for good. `by` is never None (the type says so); a device alone has no staff member to name.
    if by.staff_id is None:
        raise ValueError("A flag's step is taken by a person: a device alone is no person.")
    # Trimmed first: a note of only spaces says no more than none, and the database would take it. Filed under
    # the words' field, `text`, as the note's own check files words too long for it: the review screen shows
    # either beside the box they were typed in (03 §5.10).
    text = text.strip()
    if not text:
        raise ValidationError({"text": ValidationError("A note is required.", code="flag.note_required")})
    with transaction.atomic():
        # Read again and locked until the transaction ends (SELECT ... FOR UPDATE), as editing() does
        # (apps/core/editing.py). Two managers closing the same flag at once take turns, and the second
        # sees that the first has closed it, not the open copy still on their screen.
        fresh = Flag.objects.select_for_update().get(pk=flag.pk)
        # The same step sent again, after a double tap or a dropped network: its note is already here, so the
        # flag is handed back as it is, with no second note, which could never be deleted (03 §5.5). Asked
        # before the closed check: a close sent twice gets the closed flag back, as the first time, not
        # "this flag is closed". Asked under the lock, so two copies sent at once take turns, and the second
        # finds the first's note. Through the guard, so only this shop's notes are seen: an id taken in
        # another shop fails at the insert instead, as any create's does (CORE-6, `id.taken`).
        if note_id is not None:
            sent_before = FlagNote.objects.filter(pk=note_id).first()
            if sent_before is not None:
                if sent_before.flag_id != fresh.pk:
                    # Not this step sent again, but another flag's note.
                    raise ValidationError("This id is already another flag's note.", code="id.taken")
                return fresh
        # The status only moves forward: every step leads to explained or to a final status, and a closed
        # flag takes none.
        if fresh.status in _CLOSED:
            raise ValidationError("This flag is closed.", code="flag.closed")
        # A person the flag names may explain it, but never decide it (Jack, at CTRL-1's review; 02 v1.8):
        # Asha closing her own drawer's shortage with "no problem" would hide it from the owner. Someone else
        # closes it; who may is `flag.review` on the flag's side, which the review screen checks (CTRL-4).
        if step is not FlagStep.EXPLAINED and FlagPerson.objects.filter(flag=fresh, staff_id=by.staff_id).exists():
            raise ValidationError("A person this flag names can't close it.", code="flag.own_flag")
        written = FlagNote(shop_id=fresh.shop_id, flag=fresh, step=step, text=text, created_by_id=by.staff_id)
        if note_id is not None:
            # The phone's id, not a new one, so the next copy of this request finds the note above.
            written.id = note_id
        _saved(written)
        # Each step's value is the status it leads to (apps/control/models.py, FlagStep).
        fresh.status = FlagStatus(step.value)
        # Only the status changed, so only its own rule is checked again (control_flag_status_known). Every
        # other field was checked when the flag was raised, and the trigger keeps them as they were
        # (apps/control/operations.py): checking them all again cost a dozen queries a step.
        fresh.full_clean(exclude=[field.name for field in Flag._meta.fields if field.name != "status"])
        fresh.save(update_fields=["status"])
    return fresh


def _holds_a_float(value: object) -> bool:
    # A float anywhere in what an action changed: a value, or inside a dict or a list of them.
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_holds_a_float(inner) for inner in value.values())
    if isinstance(value, list | tuple):
        return any(_holds_a_float(inner) for inner in value)
    return False


def _check_shop(shop_id: uuid.UUID, by: Actor | None) -> None:
    # T1: an action works inside one shop. The guard watches reads, not writes (CORE-2), so these checks are
    # the service's own. Both catch a bug in the calling code, not a person's mistake, so they raise
    # ShopMismatch, a server error, before anything is written.
    # 1. The row's shop (a flag's, or an audit line's) is the one this visit opened. Otherwise full_clean's
    #    checks would read the open shop's rows while the rows are written into another shop. A nightly job,
    #    under system_context(), has every shop open; no shop open at all raises NoShopSelected.
    open_shop = current_shop()
    if open_shop is not ALL_SHOPS and open_shop != shop_id:
        raise ShopMismatch("The row's shop is not the one open.")
    # 2. Who acts belongs to that shop too: shop B's staff can't explain shop A's flag, nor suspend its staff.
    if by is not None and by.shop_id != shop_id:
        raise ShopMismatch("The one acting belongs to another shop than the row.")


def _staff_ids(shop_id: uuid.UUID, people: Sequence[Actor]) -> list[uuid.UUID]:
    # The staff members a flag names, each once, in the order given: a seller who took two payments in the
    # window may be passed twice, and is named once (the database's rule control_flagperson_once).
    staff_ids: list[uuid.UUID] = []
    for person in people:
        # A device alone acts for its shop but is no person (03 §5.4): it has nobody to explain anything.
        if person.staff_id is None:
            raise ValueError("A flag names people: a device alone is no person.")
        # T1: everyone named works at the flag's shop.
        if person.shop_id != shop_id:
            raise ShopMismatch("A person named belongs to another shop than the flag.")
        if person.staff_id not in staff_ids:
            staff_ids.append(person.staff_id)
    return staff_ids


def _saved[M: models.Model](row: M) -> M:
    # Every field, clean() and the rules in Meta, before the row is written: an unknown kind or a lone number
    # comes back as a code instead of a database error (ADR-0032).
    row.full_clean()
    row.save()
    return row
