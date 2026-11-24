"""apps/control/models.py — the control tables: the flags, one review queue for every difference and every
offline rule break (02 §13, big idea 4); and the audit trail's two books, what a person did and why, and what
changed in each office record (03 §5.16).

A Flag says that what should be there and what is there don't match, and someone must say why. E4's cash-up:
the Dawa drawer should hold 163,000, Asha counts 160,000, so a flag for −3,000 names Asha and the Dawa side.
Its subject is the row it is about, a drawer's day, a stock count, a sale, named by a short type code and a
UUID (apps/core/links.py), because one column can't link to rows of many tables.

A flag only moves forward: open → explained → resolved | dismissed, and it may close straight from open
(Jack, 29 Oct 2026; 02 v1.8). Each step is a FlagNote, with who, when and the words: every explanation is
kept, one per person or more, and none can be edited. FlagPerson links a flag to each staff member it
names, and is append-only too: who a flag names is part of the fact. apps/control/services.py raises flags
and moves them; nothing else writes these tables.

An AuditEvent is one important action, written by the service that does it, in the same transaction: the
manager suspends Asha, and one line keeps who, when, what changed and why ("Hakuja kazini siku 3"). Like a flag's
notes, its lines are append-only. apps/control/services.py writes them (audit) and nothing else does.

An EditEvent is one change to an office record, written by PostgreSQL itself, so no code path can skip it: the
owner renames the side "Dawa" to "Dawa za Mifugo", and a trigger writes who, when, and the name before and after
(apps/control/operations.py, ADR-0036). No Python code writes this table.

An Attachment is one photo or file on a record (02 §13, CTRL-3): Asha's photo as she clocks in at 07:55. Its record
reaches the server first, with the photo's label, and the row waits; the file follows when the laptop can send it,
and is checked against the label. Its file only moves forward, waiting → kept → removed, and the row is never deleted:
a removed photo's row keeps who removed it, when and why (rule 7). apps/control/services.py writes it.

`control` is layer 0, beside `core`, so every app can raise flags and write audit lines (ADR-0035). It imports
only `core`: it names the tables of `shops` and `people` by text ("shops.Side"), which is not an import (03 §5.1).
"""

from dataclasses import dataclass
from typing import Any, NoReturn

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.links import load_link
from apps.core.models import AppendOnly, AppendOnlyError, ShopScoped
from apps.core.permissions import Permission
from apps.core.type_codes import TYPE_CODE_MAX_LENGTH, TYPE_CODE_SHAPE


# Outside Flag so that its Meta can read the values, as StaffStatus is (apps/people/models.py).
class FlagKind(models.TextChoices):
    # 02 §13's list. A new kind is a new line here and a migration, since the database rule below names
    # every kind. The words a screen shows live in sw.json and en.json (ADR-0032).
    CASH_DIFFERENCE = "cash_difference", "Cash difference"
    COUNT_DIFFERENCE = "count_difference", "Count difference"
    DELIVERY_DIFFERENCE = "delivery_difference", "Delivery difference"
    TRANSFER_DIFFERENCE = "transfer_difference", "Transfer difference"
    NEGATIVE_STOCK = "negative_stock", "Negative stock"
    DUPLICATE_CODE = "duplicate_code", "Duplicate transaction code"
    LATE_RECORD = "late_record", "Late record"
    UNVERIFIED_TIME = "unverified_time", "Unverified time"
    MISSING_CLOCK_OUT = "missing_clock_out", "Missing clock-out"
    SUSPENDED_STAFF_ACTIVITY = "suspended_staff_activity", "Suspended staff activity"
    DEVICE_GAP = "device_gap", "Device gap"
    BALANCE_MISMATCH = "balance_mismatch", "Balance mismatch"
    OPEN_BAG_DIFFERENCE = "open_bag_difference", "Open bag difference"
    PRODUCTION_LOSS = "production_loss", "Production loss"
    TOTAL_MISMATCH = "total_mismatch", "Total mismatch"
    PERMISSION_BREAK = "permission_break", "Permission break"
    DRAWER_CONFLICT = "drawer_conflict", "Drawer conflict"
    # A document a laptop pushed that the server can't save: a type or version it doesn't take, a wrong shape, a maker
    # not of this shop, an id already taken (SYNC-4). Its subject is the document's line in the answer log.
    INVALID_DOCUMENT = "invalid_document", "Invalid document"


class FlagStatus(models.TextChoices):
    OPEN = "open", "Open"
    EXPLAINED = "explained", "Explained"
    # Final, both: a real difference dealt with, or no real problem (the money was found).
    RESOLVED = "resolved", "Resolved"
    DISMISSED = "dismissed", "Dismissed"


class FlagStep(models.TextChoices):
    # What a note did to its flag. Each value is also the status the flag has after it: a note never opens
    # a flag, only raise_flag does.
    EXPLAINED = FlagStatus.EXPLAINED.value, "Explained"
    RESOLVED = FlagStatus.RESOLVED.value, "Resolved"
    DISMISSED = FlagStatus.DISMISSED.value, "Dismissed"


# Wide enough for any amount (12 digits and 2 places, as money is stored) and any quantity (11 digits and 3
# places), so storing a fact never fails: an offline record that broke a rule is accepted, then flagged
# (02 §1, big idea 7). Which one a flag holds follows from its kind: TZS for a cash difference, the product's
# base unit for a count.
_NUMBER_DIGITS = 15
_NUMBER_PLACES = 3


class Flag(ShopScoped):
    # ShopScoped (CORE-2) gives `id`, `shop`, `created_at`, `created_by` (who raised it; empty when the
    # system did, as it mostly does) and the guard on reads.

    kind = models.CharField(max_length=30, choices=FlagKind)
    # The row the flag is about: its table's code (apps/core/links.py) and its id. No foreign key can
    # point at rows of many tables, so the database can't check this link: raise_flag does.
    subject_type = models.CharField(max_length=TYPE_CODE_MAX_LENGTH)
    subject_id = models.UUIDField()
    # What the system worked out, and what a person recorded. Empty, both, for kinds that are facts, not
    # amounts: a transaction code used twice. A device's missing records keep the number the server waited
    # for and the one that came (SYNC-5), so the difference is how many are missing.
    expected = models.DecimalField(max_digits=_NUMBER_DIGITS, decimal_places=_NUMBER_PLACES, null=True, blank=True)
    actual = models.DecimalField(max_digits=_NUMBER_DIGITS, decimal_places=_NUMBER_PLACES, null=True, blank=True)
    # actual − expected, worked out by PostgreSQL as the row is written and stored with it (db_persist). One
    # fact kept in one place (02 v1.7): typed in by the code, it could one day disagree with the two numbers.
    # Below zero when something is missing (E4: −3,000). One more digit than the two numbers, since the gap
    # between two large ones can be larger than either. Django reads it back as it saves the row.
    difference = models.GeneratedField(
        expression=models.F("actual") - models.F("expected"),
        output_field=models.DecimalField(max_digits=_NUMBER_DIGITS + 1, decimal_places=_NUMBER_PLACES),
        db_persist=True,
    )
    # The side the difference belongs to, so each side's people see their own flags (X1). Empty for one of
    # the whole shop. T1: raise_flag checks it belongs to the flag's shop. Named, not imported (ADR-0035).
    # PROTECT: nothing is deleted (rule 7). related_name="+": a side's flags are read through Flag.objects.
    # db_index=False: indexes lead with `shop` (03 §9), and the review screen's own index comes with it
    # (CTRL-4).
    side = models.ForeignKey(
        "shops.Side", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    # The staff members the flag names: who held the drawer, who sold loose kg in the window (E9). Kept as
    # rows of FlagPerson, which has a shop like every shop row (T1), not in Django's own link table, which
    # would have none and would CASCADE (rule 7). For reading only, as PaymentAccount.sides is: raise_flag
    # writes the rows. Its `remove()`, `clear()` and `set()` would delete link rows with no who, when or why,
    # and PROTECT doesn't stop them; FlagPerson's trigger does. through_fields: FlagPerson links to
    # StaffMember twice, by `staff` and by the `created_by` every shop row has, so Django is told which of the
    # two this is.
    people = models.ManyToManyField(
        "people.StaffMember", through="FlagPerson", through_fields=("flag", "staff"), related_name="+"
    )
    status = models.CharField(max_length=10, choices=FlagStatus, default=FlagStatus.OPEN)

    class Meta(ShopScoped.Meta):
        # Builds on ShopScoped.Meta, so `objects`, with the guard, stays the default manager (CORE-2).
        # The database is the last guard (03 §5.6); raise_flag checks the same rules first (full_clean).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=FlagKind.values),
                name="control_flag_kind_known",
                violation_error_code="flag.kind_unknown",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=FlagStatus.values),
                name="control_flag_status_known",
                violation_error_code="flag.status_unknown",
            ),
            # The list of codes lives in code, where the database can't see it, but a code's shape it can
            # check, as with a setting's key.
            models.CheckConstraint(
                condition=models.Q(subject_type__regex=TYPE_CODE_SHAPE),
                name="control_flag_subject_type_shape",
                violation_error_code="flag.subject_type_invalid",
            ),
            # A difference needs both numbers. One alone would show a flag with a difference of nothing.
            models.CheckConstraint(
                condition=models.Q(expected__isnull=True, actual__isnull=True)
                | models.Q(expected__isnull=False, actual__isnull=False),
                name="control_flag_numbers_paired",
                violation_error_code="flag.numbers_unpaired",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} ({self.status})"

    @property
    def subject(self) -> ShopScoped:
        # The row the flag is about, loaded from its two columns through the shop guard, so it needs the
        # flag's shop open (apps/core/links.py).
        return load_link(self.subject_type, self.subject_id)


class FlagPerson(AppendOnly):
    # One staff member a flag names. The table behind Flag.people, with a `shop` like every shop row (T1).
    # Written as a row of this table by raise_flag, never through `flag.people.add()`, which knows nothing
    # of the shop. Never changed or deleted: who a flag names is part of the fact (E4's flag names Asha).
    # AppendOnly (CORE-3) refuses a second save() and any delete() in Python, and the trigger in this
    # table's migration refuses the same in PostgreSQL (ADR-0021), `flag.people.clear()` included.

    # PROTECT: nothing is deleted (rule 7). db_index=False: the unique rule below indexes (shop, flag, staff).
    flag = models.ForeignKey(Flag, on_delete=models.PROTECT, related_name="+", db_index=False)
    # Named, not imported (ADR-0035). T1: raise_flag checks the person belongs to the flag's shop.
    staff = models.ForeignKey("people.StaffMember", on_delete=models.PROTECT, related_name="+", db_index=False)

    class Meta(AppendOnly.Meta):
        # Built on AppendOnly.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2).
        constraints = [
            # Named once: a person named twice would be asked to explain twice, and counted twice in a
            # report of who is flagged most. The message is there for the code's sake, as on Side's letter.
            models.UniqueConstraint(
                fields=["shop", "flag", "staff"],
                name="control_flagperson_once",
                violation_error_code="flag.person_twice",
                violation_error_message="This flag already names this person.",
            ),
        ]


class FlagNote(AppendOnly):
    # One step of a flag, in a person's own words (Jack, 29 Oct 2026; 02 v1.8): an explanation, or the note
    # that closes it. Who wrote it is `created_by` and when is `created_at`, from ShopScoped. AppendOnly
    # (CORE-3) refuses a second save() and any delete() in Python, and the trigger in this table's migration
    # refuses the same in PostgreSQL (ADR-0021): Asha's words stay as she wrote them, whoever reads them later.

    # PROTECT: nothing is deleted (rule 7). db_index=False: the index in Meta reads a flag's notes in order.
    flag = models.ForeignKey(Flag, on_delete=models.PROTECT, related_name="+", db_index=False)
    step = models.CharField(max_length=10, choices=FlagStep)
    # Long enough for a few sentences on a phone; a limit, so a pasted page can't fill the review screen.
    text = models.CharField(max_length=500)

    class Meta(AppendOnly.Meta):
        # Built on AppendOnly.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(step__in=FlagStep.values),
                name="control_flagnote_step_known",
                violation_error_code="flag.step_unknown",
            ),
            # Rule 7: every step says why. The services trim the words first, so spaces alone are refused too.
            models.CheckConstraint(
                condition=~models.Q(text=""),
                name="control_flagnote_text_not_blank",
                violation_error_code="flag.note_required",
            ),
        ]
        indexes = [
            # The review screen's question: this flag's notes, oldest first. Leads with `shop` (03 §9).
            models.Index(fields=["shop", "flag", "created_at"], name="control_flagnote_by_flag"),
        ]

    def __str__(self) -> str:
        return f"{self.step}: {self.text}"


class AuditAction(models.TextChoices):
    # What a person did (02 §13), as a code: a screen shows it in the person's language (ADR-0032). A new action
    # is a new line here and a migration, since the database rule below names every action, as FlagKind's does.
    # Each card adds the actions its services write: CTRL-5 adds cancels, approvals, price changes and voids.
    STAFF_SUSPEND = "staff.suspend", "Staff member suspended"
    STAFF_UNSUSPEND = "staff.unsuspend", "Staff member brought back"
    STAFF_LEAVE = "staff.leave", "Staff member left"
    # A worker's details fixed (PPL-10): their full name, phone, nickname, job title or first day, each before and
    # after, with who and why. The person's own details have no edit history, as a person belongs to no shop (ADR-0036).
    STAFF_DETAILS_CHANGED = "staff.details_changed", "Staff member's details fixed"
    # A first or forgotten password, set face to face (AUTH-6): who did it and why, never the password (ADR-0038).
    STAFF_TEMPORARY_PASSWORD = "staff.temporary_password", "Temporary password set"
    # A device stopped, perhaps stolen, and let work again (AUTH-1): each with who and why (rule 7).
    DEVICE_BLOCK = "device.block", "Device blocked"
    DEVICE_UNBLOCK = "device.unblock", "Device unblocked"
    # Days the shop is closed (ATT-8): a closure cancelled before its first day, and its last day moved, each with who
    # and why, as both change who is paid (rule 7).
    CLOSURE_CANCEL = "closure.cancel", "Closure cancelled"
    CLOSURE_LAST_DAY = "closure.last_day", "Closure's last day moved"


class AuditEvent(AppendOnly):
    # One thing a person did, and why (02 §13): the manager suspends Asha because she missed three days of work.
    # ShopScoped (CORE-2) gives `id`, `shop`, `created_at` (02's `at`) and `created_by` (02's `actor`: who acted,
    # empty when the system did, or the superuser, who is nobody's staff). AppendOnly (CORE-3) refuses a second
    # save() and any delete() in Python, and the trigger in this table's migration refuses the same in PostgreSQL
    # (ADR-0021): the reason stays as written, whoever reads the trail later. Written only by audit()
    # (apps/control/services.py), inside the action's own transaction. One of 02's columns comes later: `approval`,
    # with the Approval table (02 v1.9).

    # X3: the device the visit came from, the one the edit history names too. Empty for a visit with no device: a
    # password on a person's own phone, a nightly job. Named, not imported: `control` is layer 0 (ADR-0035). PROTECT:
    # nothing is deleted (rule 7). editable=False: no form or API field takes it. db_index=False: indexes lead with
    # `shop`, and nothing is deleted, so PROTECT never has to search this column.
    device = models.ForeignKey(
        "people.Device",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        db_index=False,
    )
    action = models.CharField(max_length=40, choices=AuditAction)
    # The row the action was done to: its table's code (apps/core/links.py) and its id, as a flag's subject. No
    # foreign key can point at rows of many tables, so the database can't check this link: audit() does.
    subject_type = models.CharField(max_length=TYPE_CODE_MAX_LENGTH)
    subject_id = models.UUIDField()
    # What the action changed, field by field: {"status": "active"} before, {"status": "suspended"} after. Empty
    # for an action that changes no field. DjangoJSONEncoder writes a Decimal or a date as text, the way the API
    # sends them, so an amount is never read back as a float (ADR-0024).
    before = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    # Why (T3). As long as a flag's note: a few sentences on a phone, and a limit, so a pasted page can't fill
    # the owner's trail.
    reason = models.CharField(max_length=500)

    class Meta(AppendOnly.Meta):
        # Built on AppendOnly.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2).
        # The database is the last guard (03 §5.6); audit() checks the same rules first.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action__in=AuditAction.values),
                name="control_auditevent_action_known",
                violation_error_code="audit.action_unknown",
            ),
            # The list of codes lives in code, where the database can't see it, but a code's shape it can check.
            models.CheckConstraint(
                condition=models.Q(subject_type__regex=TYPE_CODE_SHAPE),
                name="control_auditevent_subject_type_shape",
                violation_error_code="audit.subject_type_invalid",
            ),
            # T3: every action says why. audit() trims the words first, so spaces alone are refused too.
            models.CheckConstraint(
                condition=~models.Q(reason=""),
                name="control_auditevent_reason_not_blank",
                violation_error_code="audit.reason_required",
            ),
        ]
        indexes = [
            # The owner's trail of one record (CTRL-5): every line about Asha's job, oldest first. Leads with
            # `shop` (03 §9).
            models.Index(fields=["shop", "subject_type", "subject_id", "created_at"], name="control_audit_by_subject"),
        ]

    def __str__(self) -> str:
        return f"{self.action}: {self.reason}"

    @property
    def subject(self) -> ShopScoped:
        # The row the action was done to, loaded from its two columns through the shop guard, so it needs the
        # line's shop open (apps/core/links.py).
        return load_link(self.subject_type, self.subject_id)


class EditEvent(AppendOnly):
    # One change to one office row (02 §13, 03 §5.16): the owner renames the side "Dawa" to "Dawa za Mifugo".
    # Written only by the trigger control_record_edit_v2(), after the row's UPDATE, in the same transaction
    # (apps/control/operations.py, ADR-0036): never by Python, so no service, bulk update() or admin page can
    # change an office row without leaving one. ShopScoped (CORE-2) gives `id` (a UUIDv7 PostgreSQL makes),
    # `shop` (the edited row's), `created_at` (when) and `created_by` (who acted, as the visit told PostgreSQL:
    # apps/core/acting.py; empty outside a visit, when the system acted). AppendOnly (CORE-3) refuses a second
    # save() and any delete() in Python, and the trigger in this table's migration refuses the same in PostgreSQL
    # (ADR-0021).

    # X3: the device the visit came from, as AuditEvent's: empty for a visit with no device. Named, not imported, and
    # PROTECT, editable=False and db_index=False, for the same reasons.
    device = models.ForeignKey(
        "people.Device",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        db_index=False,
    )
    # The row that changed: its table's code (apps/core/links.py) and its id, as an audit line's subject.
    subject_type = models.CharField(max_length=TYPE_CODE_MAX_LENGTH)
    subject_id = models.UUIDField()
    # Only the fields that changed, each value as text, as the API sends it: {"name": "Dawa"} before,
    # {"name": "Dawa za Mifugo"} after. A field that became empty is null. Never a PIN hash: its table's trigger
    # skips it, so a reset shows only `pin_changed_at`.
    before = models.JSONField()
    after = models.JSONField()

    class Meta(AppendOnly.Meta):
        # Built on AppendOnly.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2).
        constraints = [
            # The trigger takes its type code from the migration that switched a table's history on, which
            # RecordEdits checks too; the database checks it once more.
            models.CheckConstraint(
                condition=models.Q(subject_type__regex=TYPE_CODE_SHAPE),
                name="control_editevent_subject_type_shape",
                violation_error_code="edit.subject_type_invalid",
            ),
        ]
        indexes = [
            # The owner's trail of one record (CTRL-5), as AuditEvent's. Leads with `shop` (03 §9).
            models.Index(fields=["shop", "subject_type", "subject_id", "created_at"], name="control_edit_by_subject"),
        ]

    def __str__(self) -> str:
        return f"{self.subject_type} {self.subject_id}: {self.before} → {self.after}"

    def save(self, *args: Any, **kwargs: Any) -> NoReturn:
        # The history is written only by its trigger (ADR-0036): a row saved from Python, even a new one, would be
        # a change nobody made. So save() always refuses, as AppendOnly's delete() does.
        raise AppendOnlyError("EditEvent rows are written only by the database's trigger (ADR-0036).")

    @property
    def subject(self) -> ShopScoped:
        # The row that changed, loaded from its two columns through the shop guard (apps/core/links.py).
        return load_link(self.subject_type, self.subject_id)


class AttachmentKind(models.TextChoices):
    # What a photo is of. A fixed list, checked by the database too, as each kind says which record it is pinned to
    # and who may open it (ATTACHMENT_KINDS, below). A new kind is a new line here, a line below, and a migration that
    # rebuilds the rule, as a new flag kind is. A kind whose record doesn't exist yet (the supplier's paper on a
    # delivery, a receipt on an expense) comes with that record's card (STK-4, CASH-2).
    # Asha's photo as she taps Ingia (ATT-3).
    CLOCK_PHOTO = "clock_photo", "Clock-in photo"
    # A worker's face, on their own page in the office (PPL-9) and on their tile on every laptop (PPL-14).
    STAFF_PHOTO = "staff_photo", "Staff photo"


class AttachmentType(models.TextChoices):
    # What a file may be: the two kinds of photo a laptop makes when it shrinks one (03 §5.13: longest side 1,600 px,
    # about 150 KB), and a browser shows. The upload route checks the file's first bytes against this, not its name
    # (CTRL-3). A PDF or a spreadsheet joins with the card that first needs one (DATA-3's imports).
    JPEG = "image/jpeg", "JPEG"
    WEBP = "image/webp", "WebP"


# The largest file kept: 1 MB. A photo shrunk on the laptop is about 150 KB, so this leaves room for a busy picture
# and still refuses a photo nobody shrank (a phone's own, 3 to 5 MB) or anything else sent by mistake. Read before the
# file is (the upload route asks the request's length first), so a 50 MB upload is refused unread.
LARGEST_FILE = 1024 * 1024


@dataclass(frozen=True)
class KindRule:
    # What one kind of attachment is pinned to, and who may open it.
    # The type code of the table its record is in (apps/core/links.py): "attendance_event" for a clock-in photo.
    subject_type: str
    # The key that opens it, held on the whole shop (CTRL-3's office route); None when anyone working at the shop
    # may, as for a face, which every laptop's PIN tiles show (PPL-14).
    opened_with: Permission | None


# Kind → its rule (CTRL-3's defaults, kept by the cards that first used them, ATT-3 and PPL-9).
ATTACHMENT_KINDS: dict[AttachmentKind, KindRule] = {
    # A clock-in photo proves who tapped Ingia: it is for whoever fixes attendance (the owner, a manager he gives the
    # key), not for the other workers. On the whole shop: a worker's attendance is the shop's, not a side's.
    AttachmentKind.CLOCK_PHOTO: KindRule("attendance_event", Permission.ATTENDANCE_MANAGE),
    # A worker's face is for the PIN tiles of every laptop of the shop (PPL-14), so anyone working there may see it.
    AttachmentKind.STAFF_PHOTO: KindRule("staff", None),
}


def attachment_file_name(attachment: Attachment, _given: str) -> str:
    # Where the storage keeps the file (apps/core/storage.py): its shop's id, then its own id. Never the name the
    # laptop gave the file, nor a person's name: a path is no place for personal data (03 §10), and the same id is
    # the same file, so a second try writes over the first (ADR-0007). A function of its own, not a lambda, as the
    # migration names it by its import path.
    return f"{attachment.shop_id}/{attachment.pk}"


class Attachment(ShopScoped):
    # One photo or file on one record (02 §13): Asha's clock-in photo, a worker's face. ShopScoped (CORE-2) gives `id`
    # (made where the photo is taken, ADR-0007, so the record that names it and the file sent after it agree on it),
    # `shop`, `created_at`, `created_by` (who took it or added it) and the guard on reads.
    # Edit history (RecordEditsV2, in the migration): the file's arrival and its removal are edits of this row, so both
    # land in the history with the device or the person, beside the row's own columns for them.
    # Never deleted (NoDeleteTrigger, in the migration): nothing links to an attachment, so PROTECT can't stop a delete,
    # and a photo's row must outlive its photo, to say that there was one, and who removed it (rule 7).

    kind = models.CharField(max_length=20, choices=AttachmentKind)
    # The record it is pinned to: its table's code (apps/core/links.py) and its id, as a flag's subject. No foreign
    # key can point at rows of many tables, so the database can't check this link: expect_attachment does.
    subject_type = models.CharField(max_length=TYPE_CODE_MAX_LENGTH)
    subject_id = models.UUIDField()
    # The label, as the record that brought it declared it: what the file is, how many bytes, and its SHA-256, a
    # fingerprint that changes if one byte does. The file that comes later must match all three (the upload route),
    # so a broken upload, or another file sent under this id, is refused instead of kept.
    content_type = models.CharField(max_length=20, choices=AttachmentType)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    # X3: the laptop the photo was taken on, as an audit line names its device. Empty for one added on an office
    # screen (PPL-9's worker's photo, from the owner's phone). Named, not imported: `control` is layer 0 (ADR-0035).
    # PROTECT: nothing is deleted (rule 7). db_index=False: indexes lead with `shop`.
    device = models.ForeignKey(
        "people.Device", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    # The file itself, through the storage (apps/core/storage.py): its name there, `<shop id>/<attachment id>`. Empty
    # while it waits, and again once removed.
    file = models.FileField(upload_to=attachment_file_name, max_length=100, blank=True)
    # When the file arrived. Kept after a removal: the history of the photo says it came, then went.
    received_at = models.DateTimeField(null=True, blank=True)
    # The file's removal, with who, when and why (rule 7): ATT-7's nightly job, 90 days after the pay run (03 §5.13),
    # as the system (no one), or later a person. PROTECT and db_index=False, as for `device`.
    file_removed_at = models.DateTimeField(null=True, blank=True)
    file_removed_by = models.ForeignKey(
        "people.StaffMember", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    # As long as an audit line's reason (AuditEvent).
    file_removed_reason = models.CharField(max_length=500, blank=True)

    class Meta(ShopScoped.Meta):
        # Built on ShopScoped.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2). The database
        # is the last guard (03 §5.6); the services check the same rules first. These codes stop a bug in our own code,
        # as the label comes from our app. Since ATT-3 the push sends them, for a clock-in whose photo's label one
        # refuses (apps/staffpay/documents.py), so the counter shows them with words of its own (needs-attention.tsx),
        # and those it sends have their two sentences (errors.test.ts): not_an_image, too_big, empty, sha256_invalid.
        # kind_unknown and subject_type_invalid no push can send, as the clock-in's shape and saving code pick both.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=AttachmentKind.values),
                name="control_attachment_kind_known",
                violation_error_code="attachment.kind_unknown",
            ),
            models.CheckConstraint(
                condition=models.Q(subject_type__regex=TYPE_CODE_SHAPE),
                name="control_attachment_subject_type_shape",
                violation_error_code="attachment.subject_type_invalid",
            ),
            models.CheckConstraint(
                condition=models.Q(content_type__in=AttachmentType.values),
                name="control_attachment_type_known",
                violation_error_code="attachment.not_an_image",
            ),
            # At least one byte, and no more than LARGEST_FILE: an empty file is no photo.
            models.CheckConstraint(
                condition=models.Q(size__gte=1),
                name="control_attachment_not_empty",
                violation_error_code="attachment.empty",
            ),
            models.CheckConstraint(
                condition=models.Q(size__lte=LARGEST_FILE),
                name="control_attachment_not_too_big",
                violation_error_code="attachment.too_big",
            ),
            # A SHA-256 is 64 hex digits, written in lower case, as Python's hexdigest() and the laptop write it. One
            # way only, so the upload's fingerprint and the label's compare as plain text.
            models.CheckConstraint(
                condition=models.Q(sha256__regex=r"^[0-9a-f]{64}$"),
                name="control_attachment_sha256_shape",
                violation_error_code="attachment.sha256_invalid",
            ),
            # The file's three states, and nothing between them:
            #   waiting   no file, not received, not removed
            #   kept      a file, received, not removed
            #   removed   no file, removed (received or not: a photo that never came can be removed too)
            # So a file is there exactly when it arrived and wasn't removed since.
            models.CheckConstraint(
                condition=(~models.Q(file="") & models.Q(received_at__isnull=False, file_removed_at__isnull=True))
                | (models.Q(file="") & (models.Q(received_at__isnull=True) | models.Q(file_removed_at__isnull=False))),
                name="control_attachment_file_once_received",
                violation_error_code="attachment.file_state_invalid",
            ),
            # Rule 7: a removal always says why, and only a removal has a why and a who.
            models.CheckConstraint(
                condition=models.Q(file_removed_at__isnull=False) & ~models.Q(file_removed_reason="")
                | models.Q(file_removed_at__isnull=True, file_removed_reason="", file_removed_by__isnull=True),
                name="control_attachment_removal_says_why",
                violation_error_code="attachment.reason_required",
            ),
        ]
        indexes = [
            # The question every screen that shows a record's photos asks: this record's attachments. Leads with
            # `shop` (03 §9).
            models.Index(fields=["shop", "subject_type", "subject_id"], name="control_attachment_by_subject"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} ({self.file_state})"

    @property
    def file_state(self) -> str:
        # Which of the three states the rule above allows the row is in.
        if self.file_removed_at is not None:
            return "removed"
        return "kept" if self.file else "waiting"

    @property
    def subject(self) -> ShopScoped:
        # The record it is pinned to, loaded from its two columns through the shop guard (apps/core/links.py).
        return load_link(self.subject_type, self.subject_id)
