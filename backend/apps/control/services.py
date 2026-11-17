"""apps/control/services.py — every write to the control tables, one function per action (ADR-0015): the flags,
the audit trail, and the attachments.

raise_flag writes a flag with the people it names, all or nothing. The other three move it forward, each
with a note in a person's own words, who and when kept with it (Jack, 29 Oct 2026; 02 v1.8):

    open ──explain_flag──▶ explained ──resolve_flag / dismiss_flag──▶ resolved | dismissed   (final)
      └────────────────────resolve_flag / dismiss_flag─────────────────▶

explain_flag may be called again and again: each person a flag names may explain it, and every explanation
is kept. Each step names the person who took it: a flag is raised by the system as often as not, but only a
person explains or closes one, and never one who is named on it. Nothing moves a flag back, and nothing
touches a closed one. One exception, Jack's (SYNC-5; 02 v1.22): resolve_flag_by_system closes a missing-number
flag once its records arrive, with a note of the system's own, naming no person.

audit() writes one line of the audit trail (03 §5.16): who did what to which row, what it changed, and why. The
service that does the action calls it inside its own transaction, so the action and its line are kept together
or not at all. The line also names the device the visit came from (X3). No service passes it: audit() reads the note
the edit history's trigger reads (apps/core/acting.py), so no service can forget it, and the two books can't name
different devices for one action (Jack, AUTH-8; 02 v1.7: one fact, one answer).

expect_attachment writes an attachment's row, waiting for its file (CTRL-3): Asha's clock-in reaches the server with
her photo's label (what it is, how many bytes, its fingerprint), and the row says a photo is coming. The record's own
saving code calls it, in the record's transaction, so the row arrives with the record that names it (ATT-3).
receive_attachment_file then takes the file itself, when the laptop can send it, checks it against the label, and keeps
it; the same file sent again, or a file already removed, changes nothing, so a laptop may always send again.
remove_attachment_file is the hook for retention rules: it takes the file away and keeps the row, with who, when and
why (rule 7). ATT-7's nightly job calls it for clock-in photos 90 days after their pay run is approved (03 §5.13).

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

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import connection, models, transaction
from django.db.transaction import TransactionManagementError
from django.utils import timezone

from apps.control.models import (
    ATTACHMENT_KINDS,
    LARGEST_FILE,
    Attachment,
    AttachmentKind,
    AttachmentType,
    AuditAction,
    AuditEvent,
    Flag,
    FlagKind,
    FlagNote,
    FlagPerson,
    FlagStatus,
    FlagStep,
    attachment_file_name,
)
from apps.core.acting import acting_as, current_device_id
from apps.core.links import link_type_of
from apps.core.models import ShopScoped
from apps.core.tenancy import ALL_SHOPS, Actor, ShopMismatch, current_shop, shop_context

# A flag in one of these takes no more notes: it is closed for good.
_CLOSED = {FlagStatus.RESOLVED, FlagStatus.DISMISSED}

# The kinds the system closes by itself, each with the code of the note it writes (Jack, SYNC-5; 02 v1.22): a
# missing-number flag, once every record it waited for has come. A code, not words: a person's note is kept as they
# wrote it, in their language, but the system has no language of its own, so the review screen shows the code's
# sentence in the reader's (ADR-0040; the sentences come with that screen, CTRL-4). Every other kind waits for a person.
SYSTEM_NOTES = {FlagKind.DEVICE_GAP: "flag.device_gap_filled"}


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
            device_id=current_device_id(shop_id),
        )
    )


def resolve_flag_by_system(flag: Flag) -> Flag:
    """Close `flag` as the system, with the note its kind names in SYSTEM_NOTES and no person: for a flag whose
    problem went away by itself, as a missing number that arrives late (02 v1.22). Refused for any other kind. A
    flag already closed, by a manager or by another push, is handed back as it is, with no second note."""
    code = SYSTEM_NOTES.get(FlagKind(flag.kind))
    if code is None:
        # A bug in the calling code: every other flag is closed by a person (02 §13, v1.8).
        raise ValueError(f"A {flag.kind} flag is closed by a person, never by the system.")
    if flag.kind == FlagKind.DEVICE_GAP and not _waits_for_records(flag):
        # A device's numbers that went back (a reset: `expected` above `actual`) wait for no record, so none can close
        # the flag: a person looks at what happened. Refused here too, not only by the push, which never asks.
        raise ValueError("A device_gap of numbers gone back is closed by a person, never by the system.")
    _check_shop(flag.shop_id, None)
    with transaction.atomic():
        # Read again and locked, as a person's step is (_step): a manager closing it at this moment takes turns with
        # the system, and the second finds it closed.
        fresh = Flag.objects.select_for_update().get(pk=flag.pk)
        if fresh.status in _CLOSED:
            return fresh
        # No `created_by`: the system acted. The note is kept for good, like every note (ADR-0021), so the owner sees
        # why the flag closed, and when.
        _saved(FlagNote(shop_id=fresh.shop_id, flag=fresh, step=FlagStep.RESOLVED, text=code))
        fresh.status = FlagStatus.RESOLVED
        # Only the status changed, as in _step: only its rule is checked again.
        fresh.full_clean(exclude=[field.name for field in Flag._meta.fields if field.name != "status"])
        fresh.save(update_fields=["status"])
    return fresh


def expect_attachment(
    *,
    id: uuid.UUID,
    kind: str,
    subject: ShopScoped,
    content_type: str,
    size: int,
    sha256: str,
    by: Actor,
    device: ShopScoped | None = None,
) -> Attachment:
    """Write the row of a photo that is coming: its `id`, made where it was taken (ADR-0007); its `kind`; the record
    it is pinned to (`subject`, a saved row of the open shop); its label, as the record declared it (`content_type`,
    `size` in bytes, `sha256` in lower-case hex); who took it (`by`, a person); and the laptop it was taken on
    (`device`), or None on an office screen. The file comes later, through the upload route (CTRL-3), and must match
    the label. Call it inside the record's own transaction, so the row is kept with the record or not at all."""
    # The row belongs to its record's shop: shop A's clock-in gets a photo of shop A.
    shop_id = subject.shop_id
    _check_shop(shop_id, by)
    # A photo is always taken by someone: a device alone has nobody to name, and the row's `created_by` is kept for
    # good, as a flag's note is.
    if by.staff_id is None:
        raise ValueError("An attachment is added by a person: a device alone is no person.")
    # A generic link has no foreign key, so the database can't check that it points at a row (as in raise_flag).
    if subject._state.adding:
        raise ValueError(f"An attachment's record must be a saved row; this {type(subject).__name__} was never saved.")
    # T1: the laptop is the record's shop's too.
    if device is not None and device.shop_id != shop_id:
        raise ShopMismatch("The device belongs to another shop than the attachment.")
    # A kind the list doesn't know. Filed under `kind`, as the database's rule would file it, and asked first: the
    # kind says which record it may be pinned to, below.
    if kind not in AttachmentKind.values:
        unknown = ValidationError("This kind of attachment is not known.", code="attachment.kind_unknown")
        raise ValidationError({"kind": unknown})
    # A file that isn't one of the photos a laptop makes. Asked here, not left to full_clean, whose choice check would
    # answer first with Django's general `invalid_choice`: the upload route refuses the same with this code (CTRL-3),
    # and the laptop sets the photo aside by it, so both say it one way.
    if content_type not in AttachmentType.values:
        not_an_image = ValidationError("Only a JPEG or a WebP photo is kept.", code="attachment.not_an_image")
        raise ValidationError({"content_type": not_an_image})
    # Each kind is pinned to one table's records (ATTACHMENT_KINDS): a clock-in photo on a staff member, not on a
    # clock-in, would be opened with the wrong key. The calling code picks both, so a mismatch is its bug, not a
    # person's mistake. UnknownLinkType when the subject's table has no code at all (apps/core/links.py).
    expected_table = ATTACHMENT_KINDS[AttachmentKind(kind)].subject_type
    subject_type = link_type_of(subject)
    if subject_type != expected_table:
        raise ValueError(f"A {kind} is pinned to a {expected_table!r} record, not to a {subject_type!r} one.")
    return _saved(
        Attachment(
            id=id,
            shop_id=shop_id,
            kind=kind,
            subject_type=subject_type,
            subject_id=subject.pk,
            content_type=content_type,
            size=size,
            sha256=sha256,
            device_id=None if device is None else device.pk,
            created_by_id=by.staff_id,
        )
    )


# The fields a file's arrival changes.
_FILE_FIELDS = ("file", "received_at")


def receive_attachment_file(attachment_id: uuid.UUID, *, content: bytes) -> Attachment:
    """Keep the file of the attachment `attachment_id`, of the open shop, once it matches the label its record brought:
    a JPEG or a WebP by its first bytes, of that type, that many bytes, that SHA-256. The same file sent again, after
    a first answer that was lost, changes nothing; so does any file sent for an attachment whose file was removed, so
    the laptop can drop its copy either way. Attachment.DoesNotExist for an id the open shop doesn't hold, another
    shop's included, or one whose record hasn't arrived yet: the route answers "not found", and the laptop tries again
    after its next push."""
    with transaction.atomic():
        # Locked until the transaction ends (SELECT ... FOR UPDATE), and read through the guard, so only the open shop's
        # rows are found (T1). Two copies of one upload at once (two tabs, or a tab and the service worker) take turns:
        # the second finds the file the first kept, and changes nothing.
        attachment = Attachment.objects.select_for_update().get(pk=attachment_id)
        if attachment.file_removed_at is not None:
            # Removed already (90 days after its pay run, or never arrived and given up on): nothing is kept again.
            return attachment
        _check_file(attachment, content)
        if attachment.file:
            # Kept already, and this copy matched the label, so it is the same file: the first send's answer was lost.
            return attachment
        # The file first, then the row (CTRL-3's card): if the row's save failed after the file was written, a retry
        # writes over that file under the same name, and no row ever names a file that isn't there. On the demo the file
        # is a row of the same transaction, and goes back with it.
        attachment.file.save(attachment_file_name(attachment, ""), ContentFile(content), save=False)
        attachment.received_at = timezone.now()
        # Only the file and its time changed: only the rules about them are checked again, not every rule of the label.
        attachment.full_clean(
            exclude=[field.name for field in Attachment._meta.fields if field.name not in _FILE_FIELDS]
        )
        attachment.save(update_fields=list(_FILE_FIELDS))
    return attachment


# The fields a file's removal changes: the file, and who removed it, when and why.
_REMOVAL_FIELDS = ("file", "file_removed_at", "file_removed_by", "file_removed_reason")


def remove_attachment_file(attachment: Attachment, *, reason: str, by: Actor | None = None) -> Attachment:
    """Take the file of `attachment`, of the open shop, away for good, and keep its row, with who (`by`, a person, or
    None for the system, as ATT-7's nightly job), when and why: the retention rule wants the photo gone, not hidden,
    and the row still says there was one (rule 7). A photo that never arrived can be removed too, so a late upload is
    dropped. Removing one already removed changes nothing, so a nightly job may run twice."""
    _check_shop(attachment.shop_id, by)
    # A device alone is no person: the row would keep a remover with no name for good.
    if by is not None and by.staff_id is None:
        raise ValueError("A file is removed by a person, or by the system: a device alone is no person.")
    # Rule 7: always why. Trimmed first: spaces alone say no more than nothing. Filed under the reason's field, as the
    # database's own rule would be.
    reason = reason.strip()
    if not reason:
        required = ValidationError("A reason is required.", code="attachment.reason_required")
        raise ValidationError({"file_removed_reason": required})
    with transaction.atomic():
        # Locked, as a file's arrival is (receive_attachment_file): an upload and a removal at once take turns.
        fresh = Attachment.objects.select_for_update().get(pk=attachment.pk)
        if fresh.file_removed_at is not None:
            return fresh
        # The file's name and its storage, kept for after the commit. Empty for a photo that never arrived.
        name, storage, shop_id = fresh.file.name, fresh.file.storage, fresh.shop_id
        # No file: the empty name, as a waiting row has.
        fresh.file = ""
        fresh.file_removed_at = timezone.now()
        fresh.file_removed_by_id = None if by is None else by.staff_id
        fresh.file_removed_reason = reason
        fresh.full_clean(exclude=[field.name for field in Attachment._meta.fields if field.name not in _REMOVAL_FIELDS])
        # Saved with `by` told to PostgreSQL, as the closures' and the staff services' saves are: the edit history's
        # line then names the person the row names, even outside an office visit (02 v1.7: one fact, one answer;
        # apps/core/acting.py). With `by` None, the system acts, and nobody is told.
        with acting_as(by) if by is not None else nullcontext():
            fresh.save(update_fields=list(_REMOVAL_FIELDS))
        if name:
            # The row first, the file only once the row's change is kept for good (CTRL-3's card): Django runs this
            # after the transaction commits, and never if it rolls back. Deleted inside the transaction instead, a
            # rollback would bring the row back as "kept", naming a file that is gone. The other way, the worst left
            # is a file no row names, if the delete fails after the commit: nothing serves it, and a later clean-up
            # job can find such leftovers. Opened in the file's own shop: by then, the caller's may have closed.
            transaction.on_commit(lambda: _delete_stored(storage, name, shop_id))
    return fresh


def _delete_stored(storage: Any, name: str, shop_id: uuid.UUID) -> None:
    # The storage checks a name's shop against the one open (apps/core/storage.py).
    with shop_context(shop_id):
        storage.delete(name)


def _check_file(attachment: Attachment, content: bytes) -> None:
    # The file against its label (CTRL-3). Each refusal names no field: it is about the whole file. The route reads a
    # file's length before the file itself, so a file over the limit rarely gets here; checked again, as a request with
    # no length still reaches here.
    if len(content) > LARGEST_FILE:
        raise ValidationError("A file is kept up to 1 MB.", code="attachment.too_big")
    sniffed = _image_type_of(content)
    if sniffed is None:
        raise ValidationError("Only a JPEG or a WebP photo is kept.", code="attachment.not_an_image")
    # Another file than the one the record named: a photo damaged on the way, cut short, or another photo sent under
    # this id. Its fingerprint tells, whatever its size. A file of the right bytes but of another type than its label
    # says can only be a label the laptop wrote wrong; it is refused too, as kept it would be served as the wrong type.
    if (
        len(content) != attachment.size
        or hashlib.sha256(content).hexdigest() != attachment.sha256
        or sniffed != attachment.content_type
    ):
        raise ValidationError("This file is not the one its record names.", code="attachment.file_differs")


def _image_type_of(content: bytes) -> AttachmentType | None:
    # What a file is, by its first bytes, never by its name or what the request says it is: every JPEG starts with the
    # bytes FF D8 FF, and every WebP with "RIFF", its length in four bytes, then "WEBP".
    if content.startswith(b"\xff\xd8\xff"):
        return AttachmentType.JPEG
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return AttachmentType.WEBP
    return None


def _waits_for_records(gap: Flag) -> bool:
    # A device_gap waits for records when the number the server awaited is below the one that came: the numbers between
    # are the missing ones. Above it, the device's count went back, and nothing is missing.
    return gap.expected is not None and gap.actual is not None and gap.expected < gap.actual


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
        # Read again and locked until the transaction ends (SELECT ... FOR UPDATE). Two managers closing the same flag
        # at once take turns, and the second sees that the first has closed it, not the open copy still on their screen.
        # A full lock, unlike editing()'s (apps/core/editing.py): only a step of this flag links a note to it, and that
        # step holds this very lock, so no other row is left waiting.
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
