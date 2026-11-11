"""apps/staffpay/models.py — the attendance book: one line per clock-in or clock-out, made on a shop laptop and
pushed later (ATT-1; 02 §12).

    who    in/out  laptop          laptop's time  trusted time  check
    Asha   in      Laptop ya Dawa  07:20          07:20         device_ok
    Juma   in      Laptop ya Dawa  07:30          —             unverified

A ledger: a line is written once, by the clock document's saving code (apps/staffpay/documents.py), and never
changed or deleted, only voided once, with who and why (T2, ADR-0021). A late fine is worked out from these lines
(ATT-4), so each keeps the laptop's own time, the evidence about it, and the time the server trusts.
"""

from django.db import models

from apps.core.models import AppendOnly, CounterRecord


class ClockKind(models.TextChoices):
    # What the worker tapped: Ingia or Toka.
    IN = "in", "In"
    OUT = "out", "Out"


class TimeCheck(models.TextChoices):
    # How far the line's time can be trusted (02 §12).
    SERVER = "server", "The server's time"  # sent at once: the server's own clock
    DEVICE_OK = "device_ok", "The laptop's time, checked"  # sent later, and no sign its clock moved
    UNVERIFIED = "unverified", "Not verified"  # a sign its clock moved: a manager decides


# The type checker's Django plugin calls the two bases' get_next_by_created_at() a clash, as on PushedDocument
# (apps/sync/models.py): one and the same method, from ShopScoped. Ignored on this line only.
class AttendanceEvent(AppendOnly, CounterRecord):  # type: ignore[misc]
    # One tap of Ingia or Toka. AppendOnly first, so its save() and delete() run first and refuse a change;
    # CounterRecord gives the laptop, its number for the line and both clocks (03 §5.3). created_by (ShopScoped):
    # who tapped, on the laptop, by their PIN (X3).

    # Whose attendance it is: today always the one who tapped. A column of its own all the same, as a manager
    # entering a missed clock-in for someone (ATT-6) writes a line about another person, and a ledger's lines can't
    # be filled in later. PROTECT: nothing is deleted (rule 7). No index of its own: indexes lead with `shop`, and
    # ATT-4 adds the one it reads a month by.
    staff = models.ForeignKey("people.StaffMember", on_delete=models.PROTECT, related_name="+", db_index=False)
    kind = models.CharField(max_length=3, choices=ClockKind)
    # The time the server trusts, and how far (TimeCheck): the server's own clock as the push arrived (`received_at`)
    # for a clock-in sent at once; the laptop's (`client_time`) for one sent later with no sign its clock moved; none
    # when a sign says it did, so a manager decides (ATT-6). A rule below holds the three together.
    trusted_time = models.DateTimeField(null=True, blank=True)
    time_check = models.CharField(max_length=10, choices=TimeCheck)
    # The evidence about the laptop's clock, kept as it was read (02 §12), so a manager can see why a line wasn't
    # trusted: the last server time the laptop had seen when the worker tapped, and how far off the laptop's clock
    # was as it sent the push (its clock minus the server's: 40 minutes slow is minus 40 minutes).
    last_server_time = models.DateTimeField()
    clock_error = models.DurationField()
    # The void stamp (03 §5.6): empty while the line counts, filled once when it is voided, then frozen, as the
    # trigger in this table's migration makes PostgreSQL hold it. A clock-in tapped twice by mistake is voided, never
    # deleted (T3). Who voided it: a staff member, as created_by is; PROTECT, as nothing is deleted. That they are of
    # this line's shop is the void service's check (T1, ATT-6): the database can't hold it with one column. The fourth
    # part, `void_approval`, comes with the Approval table (R1), in a migration of its own.
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "people.StaffMember", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    void_reason = models.TextField(blank=True)

    class Meta(AppendOnly.Meta, CounterRecord.Meta):
        # Both bases' Meta, so the guard stays the default manager (CORE-1, ADR-0042). No error codes on these rules:
        # only the clock document's saving code writes a line, so a broken rule is a bug in our code, a server error
        # and a log line, never a person's mistake (ADR-0032).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=ClockKind.values), name="staffpay_attendanceevent_kind_known"
            ),
            # The trusted time fits its check, and only the three checks there are: the server's clock for a line sent
            # at once, the laptop's for one kept, none for one not verified. Each kept time is said to be there too:
            # in a database rule, a comparison with an empty value is "unknown", and "unknown" passes.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        time_check=TimeCheck.SERVER, trusted_time__isnull=False, trusted_time=models.F("received_at")
                    )
                    | models.Q(
                        time_check=TimeCheck.DEVICE_OK, trusted_time__isnull=False, trusted_time=models.F("client_time")
                    )
                    | models.Q(time_check=TimeCheck.UNVERIFIED, trusted_time__isnull=True)
                ),
                name="staffpay_attendanceevent_trusted_time_fits_its_check",
            ),
            # A void says who and why (T3), as CORE-3's Watch out asks of each void table: the void rule only checks
            # that the stamp is filled once. All three empty, or all three filled.
            models.CheckConstraint(
                condition=(
                    models.Q(voided_at__isnull=True, voided_by__isnull=True, void_reason="")
                    | (models.Q(voided_at__isnull=False, voided_by__isnull=False) & ~models.Q(void_reason=""))
                ),
                name="staffpay_attendanceevent_void_complete",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.client_time:%Y-%m-%d %H:%M}"
