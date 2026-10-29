"""apps/control/models.py — the control tables. For now the flags: one review queue for every difference and
every offline rule break (02 §13, big idea 4).

A Flag says that what should be there and what is there don't match, and someone must say why. E4's cash-up:
the Dawa drawer should hold 163,000, Asha counts 160,000, so a flag for −3,000 names Asha and the Dawa side.
Its subject is the row it is about, a drawer's day, a stock count, a sale, named by a short type code and a
UUID (apps/core/links.py), because one column can't link to rows of many tables.

A flag only moves forward: open → explained → resolved | dismissed, and it may close straight from open
(Jack, 29 Oct 2026; 02 v1.8). Each step is a FlagNote, with who, when and the words: every explanation is
kept, one per person or more, and none can be edited. FlagPerson links a flag to each staff member it
names, and is append-only too: who a flag names is part of the fact. apps/control/services.py raises flags
and moves them; nothing else writes these tables.

`control` is layer 0, beside `core`, so every app can raise flags (ADR-0035). It imports only `core`: it
names the tables of `shops` and `people` by text ("shops.Side"), which is not an import (03 §5.1).
"""

from django.db import models

from apps.core.links import TYPE_CODE_MAX_LENGTH, TYPE_CODE_SHAPE, load_link
from apps.core.models import AppendOnly, ShopScoped


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
    # amounts: a transaction code used twice, a device's missing records.
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
