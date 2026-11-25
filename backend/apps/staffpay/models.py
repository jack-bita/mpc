"""apps/staffpay/models.py — the attendance book: one line per clock-in or clock-out, made on a shop laptop and
pushed later (ATT-1; 02 §12).

    who    in/out  laptop          laptop's time  trusted time  check
    Asha   in      Laptop ya Dawa  07:20          07:20         device_ok
    Juma   in      Laptop ya Dawa  07:30          —             unverified
    Juma   out     —               —              18:45         entered     added by Baba: "Alisahau kubonyeza Toka"

A ledger: a line is written once, by the clock document's saving code (apps/staffpay/documents.py), or by a manager in
the office for a tap a worker forgot (ATT-13), and never changed or deleted, only voided once, with who and why (T2,
ADR-0021). A late fine is worked out from these lines (ATT-4), so each keeps the laptop's own time, the evidence about
it, and the time the server trusts; a line entered in the office has no laptop, and keeps who entered it and why.

It also owns the names of what a day was (DayStatus): on time, late, half, absent, off or needs review, which the
day's rule answers (apps/staffpay/calculations.py), and of why a day needs review (ReviewReason, ATT-5); and the book of
days (AttendanceDay, ATT-10), one row per worker
per day, which keeps each answer with the rules it used:

    who    date        status        fine    in     out
    Asha   Mon 16 Nov  late          500.00  07:50  18:45
    Asha   Sun 22 Nov  off           0.00    —      —
    Juma   Mon 16 Nov  needs_review  0.00    07:20  —

and, with each, the worker's share of that date's meal money (`meal_share`, WAGE-7). The events are the truth and the
days only answers worked out from them: a day is worked out again, from its taps and its date's rules, as often as it
is asked, until its pay run is approved (WAGE-3). Beside the answer, a day keeps a manager's or the owner's decision
(ATT-6), which the book never writes, and why an absent worker was away (AbsenceType):

    who    date        book says     decided   absence      fine  by    why
    Juma   Mon 16 Nov  needs_review  on_time   —            0.00  Baba  Alisahau kubonyeza Toka
    Asha   Tue 17 Nov  absent        absent    office_duty  0.00  Baba  Alienda benki

And each worker's daily pay rate, dated (PayRate, WAGE-1), a ledger like the events: a raise is a new row from its day,
and the old one stays, so a month with a raise on the 15th pays each day at its own rate (WAGE-2):

    who    from        rate        shares meals
    Juma   10 Nov      10,000.00   yes
    Juma   15 Nov      12,000.00   yes

And the day's meal money (MealMoney, WAGE-7), a ledger too: what the shop spent on the workers' meals on one day, which
they pay for out of their pay, crossed out with a reason when typed wrong, and typed again:

    date    amount     note              typed by   crossed out
    23 Nov   5,000.00  Unga na maharage  Asha
    23 Nov  30,000.00  Nyama             Asha       by Baba: "Sifuri moja zaidi"
    23 Nov   3,000.00  Nyama             Asha
"""

from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import models
from django.db.models.functions import Floor

from apps.control.facts import FlagFacts, FlaggedTap
from apps.core.models import AppendOnly, CounterRecord, ShopScoped


class ClockKind(models.TextChoices):
    # What the worker tapped: Ingia or Toka.
    IN = "in", "In"
    OUT = "out", "Out"


class TimeCheck(models.TextChoices):
    # How far the line's time can be trusted (02 §12).
    SERVER = "server", "The server's time"  # sent at once: the server's time of the tap, its arrival less the wait
    DEVICE_OK = "device_ok", "The laptop's time, checked"  # sent later, and no sign its clock moved
    UNVERIFIED = "unverified", "Not verified"  # a sign its clock moved: a manager decides
    # Entered in the office by a manager, for a tap the worker forgot (ATT-13): the minute they typed, trusted, as the
    # person who may fix attendance says so. An Ingia added at 07:50 takes the late fine, as a real tap would.
    ENTERED = "entered", "Entered in the office"


class NoPhoto(models.TextChoices):
    # Why a tap has no photo (ATT-3). A tap is never refused for want of one, as nobody may lose a day's pay to a camera
    # (Jack: A): it is kept, and says why, for a manager to see beside the day (ATT-5). Empty when its photo came: the
    # photo itself is an Attachment pinned to the line (apps/control/models.py), not a column, so one fact lives once.
    NO_CAMERA = "no_camera", "No camera"  # the laptop has none, or the browser found none
    BLOCKED = "blocked", "Camera blocked"  # someone told the browser to block it: a manager may want to ask who
    FAILED = "failed", "Camera failed"  # it started and broke, or the photo couldn't be made: a bug or a broken camera
    # Version 1 of the clock-in, from an app with no camera yet: the server's word, never a laptop's choice.
    OLD_APP = "old_app", "App before photos"
    DEMO = "demo", "Demo"  # on the demo a visitor's face never leaves their laptop (Jack: A)
    # Entered in the office by a manager (ATT-13): no laptop, so no camera, ever. The server's word, never a laptop's.
    ENTERED = "entered", "Entered in the office"


class DayStatus(models.TextChoices):
    # What one worker's day was (02 §12). ATT-4's rule gives every one but `off` (apps/staffpay/calculations.py);
    # the book of days (AttendanceDay, below) gives `off`, and keeps each day's status as one of these.
    ON_TIME = "on_time", "On time"  # a full day
    LATE = "late", "Late"  # a full day, less the fine of its arrival
    HALF = "half", "Half day"  # half the day's pay, less the fine of a late morning arrival (the owner, ATT-4)
    ABSENT = "absent", "Absent"  # no tap: unpaid, unless a manager marks office duty (ATT-6)
    OFF = "off", "Off"  # a Sunday or a closed day: the shop is shut, nobody is paid (ATT-8)
    NEEDS_REVIEW = "needs_review", "Needs review"  # the owner's dharura: a manager or the owner decides it (ATT-6)


class ReviewReason(models.TextChoices):
    # Why a day needs a person's decision (ATT-5): the one line the month page shows beside it, "Juma · Alhamisi 12/11 ·
    # hakuna Toka", so the owner knows what to look at before he opens the day. One reason a day: the first that holds,
    # in this order. The book's own first (apps/staffpay/services.py), as each asks whether the day is paid at all,
    # whatever its times say; then the rule's (apps/staffpay/calculations.py), in the order the rule reads a day.
    OUTSIDE_JOB = "outside_job", "Outside the job's days"  # a tap before the first day or after the last (ATT-11)
    CLOSED_DAY = "closed_day", "The shop was closed"  # a tap on a day the shop closed, a funeral (ATT-10)
    NOT_WORKING = "not_working", "Suspended or gone"  # a tap the offline laptop let through after a suspension (ATT-11)
    CLOCK_DISAGREES = "clock_disagrees", "A later tap disagrees"  # its laptop's clock may have moved (ATT-11)
    TIME_UNKNOWN = "time_unknown", "Time not trusted"  # a tap whose time can't be trusted (`unverified`, ATT-1)
    NO_IN = "no_in", "No Ingia"  # a Toka, and no Ingia before it
    CAME_LATE = "came_late", "Came late"  # in from 08:30 and before 12:00, or after 13:00: the owner's dharura
    NO_OUT = "no_out", "No Toka"  # an Ingia, and no Toka after it
    LEFT_EARLY = "left_early", "Left early"  # out before closing, outside the half day's windows


class AbsenceType(models.TextChoices):
    # Why a worker wasn't there, on a day a manager or the owner decides absent (ATT-6, 02 §12). Only a person can say
    # it: no tap tells the bank errand from a no-show, so the book's own `absent` keeps none. The pay reads it (WAGE-2).
    OFFICE_DUTY = "office_duty", "Office duty"  # out on the shop's own work, sent to the bank: paid as a full day
    PERMISSION = "permission", "Permission"  # allowed to stay away: unpaid
    NO_SHOW = "no_show", "No-show"  # away with no word: unpaid


# What a manager may decide a day was (ATT-6): a full day, a late one, a half day, or absent with its kind. Never `off`,
# which is the shop's calendar (a Sunday, a closed day), nor `needs_review`, which is what a decision ends.
DECIDED = [DayStatus.ON_TIME, DayStatus.LATE, DayStatus.HALF, DayStatus.ABSENT]


class DayChoice(models.TextChoices):
    # The six choices of the sheet a manager decides a day in (ATT-6), in the sheet's order: *Siku kamili*,
    # *Amechelewa*, *Nusu siku*, then the three absences. Not a column: each is kept as a decided status and, for an
    # absence, its kind (DECISION_OF), so the pay reads one status, whatever the sheet called it.
    ON_TIME = "on_time", "Full day"
    LATE = "late", "Late"
    HALF = "half", "Half day"
    OFFICE_DUTY = "office_duty", "Office duty"
    PERMISSION = "permission", "Permission"
    NO_SHOW = "no_show", "No-show"


# Each choice as the day keeps it: the decided status, and the absence's kind, or "" for none.
DECISION_OF: dict[DayChoice, tuple[DayStatus, str]] = {
    DayChoice.ON_TIME: (DayStatus.ON_TIME, ""),
    DayChoice.LATE: (DayStatus.LATE, ""),
    DayChoice.HALF: (DayStatus.HALF, ""),
    DayChoice.OFFICE_DUTY: (DayStatus.ABSENT, AbsenceType.OFFICE_DUTY),
    DayChoice.PERMISSION: (DayStatus.ABSENT, AbsenceType.PERMISSION),
    DayChoice.NO_SHOW: (DayStatus.ABSENT, AbsenceType.NO_SHOW),
}


# The type checker's Django plugin calls the two bases' get_next_by_created_at() a clash, as on PushedDocument
# (apps/sync/models.py): one and the same method, from ShopScoped. Ignored on this line only.
class AttendanceEvent(AppendOnly, CounterRecord):  # type: ignore[misc]
    # One tap of Ingia or Toka. AppendOnly first, so its save() and delete() run first and refuse a change;
    # CounterRecord gives the laptop, its number for the line and both clocks (03 §5.3). created_by (ShopScoped):
    # who tapped, on the laptop, by their PIN (X3); or, on a tap entered in the office, who entered it (ATT-13), as
    # created_by names whoever made any row: so no `entered_by` column, one fact kept once.

    # A tap a manager enters in the office (ATT-13) has no laptop: none made it, numbered it or timed it. So three of
    # the facts CounterRecord gives every counter record may be empty here, on this table alone: Django lets a table
    # write over a field it takes from an abstract base. The time it was entered is `received_at`, which stays, the
    # server's clock as the line is kept. Which line is whose, a laptop's with all of them or the office's with none,
    # is a rule below (Meta). The type checker holds a field written over to its base's type, which is never empty,
    # so each of the three lines tells it this table's may be.
    device = models.ForeignKey(  # type: ignore[assignment]
        "people.Device",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        db_index=False,
    )
    device_seq = models.PositiveBigIntegerField(null=True, blank=True, editable=False)  # type: ignore[assignment]
    client_time = models.DateTimeField(null=True, blank=True, editable=False)  # type: ignore[assignment]

    # Whose attendance it is: on a laptop's tap, the one who tapped; on one entered in the office (ATT-13), the worker
    # it was entered for, as the manager who entered it is `created_by`. A column of its own for that, as a ledger's
    # lines can't be filled in later. PROTECT: nothing is deleted (rule 7). No index of its own: indexes lead with
    # `shop`, and the one the book of days reads a month by is below (Meta).
    staff = models.ForeignKey("people.StaffMember", on_delete=models.PROTECT, related_name="+", db_index=False)
    kind = models.CharField(max_length=3, choices=ClockKind)
    # The time the server trusts, and how far (TimeCheck): for a clock-in sent at once, the server's time of the tap,
    # the push's arrival less the wait on the laptop, which is the laptop's time less its clock's error
    # (`client_time - clock_error`); the laptop's own (`client_time`) for one sent later with no sign its clock moved;
    # none when a sign says it did, so a manager decides (ATT-6). A rule below holds the three together.
    trusted_time = models.DateTimeField(null=True, blank=True)
    time_check = models.CharField(max_length=10, choices=TimeCheck)
    # The evidence about the laptop's clock, kept as it was read (02 §12), so a manager can see why a line wasn't
    # trusted: the last server time the laptop had seen when the worker tapped, and how far off the laptop's clock
    # was as it sent the push (its clock minus the server's: 40 minutes slow is minus 40 minutes).
    # Both empty on a tap entered in the office, which no laptop clock timed (ATT-13).
    last_server_time = models.DateTimeField(null=True, blank=True)
    clock_error = models.DurationField(null=True, blank=True)
    # The record this tap's time disagrees with (ATT-11): the laptop's record numbered just before it, whose time is
    # later. Juma's Toka says 18:45, then Asha's says 18:30: a clock moved between the two, and the server can't tell
    # whose, so hers is `unverified`, and its flag names him too (ATT-1's review). A flag names people, not records, so
    # the tap keeps that record's id here, for the book to send his day to review as well (Jack, ATT-11: A). The
    # record's own id, as the laptop made it, not its line's in the answer log: a tap's id when it is one, but it can
    # be any record the laptop made, a sale once SALE-2 comes, so no foreign key, and only a tap's id sends a day.
    # Empty for every other tap, and for those saved before ATT-11, as a ledger's lines are never filled in later.
    disagrees_with = models.UUIDField(null=True, blank=True)
    # Why the tap has no photo, or empty when its photo came (NoPhoto, ATT-3). Written once with the line, as the rest
    # of it is: a photo that arrives late changes nothing here, as its row is the one that waits (CTRL-3).
    no_photo = models.CharField(max_length=9, choices=NoPhoto, blank=True)
    # Why a manager entered the tap in the office (ATT-13), "Alisahau kubonyeza Toka"; empty on a laptop's tap, whose
    # worker tapped it themselves. Written once with the line, as the rest of it is.
    entry_reason = models.TextField(blank=True)
    # The void stamp (03 §5.6): empty while the line counts, filled once when it is voided, then frozen, as the
    # trigger in this table's migration makes PostgreSQL hold it. A clock-in tapped twice by mistake is voided, never
    # deleted (T3). Who voided it: a staff member, as created_by is; PROTECT, as nothing is deleted. That they are of
    # this line's shop is the void service's check (T1, ATT-13): the database can't hold it with one column. The fourth
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
            # The trusted time fits its check, and only the three checks there are: the server's time of the tap for a
            # line sent at once, the laptop's for one kept, none for one not verified. Each kept time is said to be
            # there too: in a database rule, a comparison with an empty value is "unknown", and "unknown" passes. The
            # server's is written as two times compared, `client_time - trusted_time = clock_error`: "a time less a
            # length of time" steps whole days in the session's time zone, so a restore run in a zone with summer time
            # would find a laptop's year-long clock error an hour off and refuse the line (ATT-1's second review).
            models.CheckConstraint(
                condition=(
                    models.Q(
                        time_check=TimeCheck.SERVER,
                        trusted_time__isnull=False,
                        clock_error=models.F("client_time") - models.F("trusted_time"),
                    )
                    | models.Q(
                        time_check=TimeCheck.DEVICE_OK, trusted_time__isnull=False, trusted_time=models.F("client_time")
                    )
                    | models.Q(time_check=TimeCheck.UNVERIFIED, trusted_time__isnull=True)
                    # Entered in the office (ATT-13): the minute the manager typed, its only time.
                    | models.Q(time_check=TimeCheck.ENTERED, trusted_time__isnull=False)
                ),
                name="staffpay_attendanceevent_trusted_time_fits_its_check",
            ),
            # A void says who and why (T3), as CORE-3's Watch out asks of each void table: the void rule only checks
            # that the stamp is filled once. All three empty, or all three filled.
            models.CheckConstraint(
                condition=(
                    models.Q(voided_at__isnull=True, voided_by__isnull=True, void_reason="")
                    # A reason holds at least one letter, figure or sign: spaces alone are no reason (ATT-1's review).
                    | models.Q(voided_at__isnull=False, voided_by__isnull=False, void_reason__regex=r"\S")
                ),
                name="staffpay_attendanceevent_void_complete",
            ),
            # Only a tap whose time isn't trusted names a record it disagrees with (ATT-11): a tap with a trusted time
            # naming one would be a bug in the saving code, which keeps the record only for that sign.
            models.CheckConstraint(
                condition=models.Q(disagrees_with__isnull=True) | models.Q(time_check=TimeCheck.UNVERIFIED),
                name="staffpay_attendanceevent_disagrees_only_unverified",
            ),
            # Only the reasons there are, or none (ATT-3). Whether a photo came can't be a rule here: its row is in
            # another table, and comes in the same transaction, after the line it is pinned to.
            models.CheckConstraint(
                condition=models.Q(no_photo__in=["", *NoPhoto.values]), name="staffpay_attendanceevent_no_photo_known"
            ),
            # A line is a laptop's or the office's, never half of each (ATT-13). A laptop's has every fact a laptop
            # gives, its laptop, its number, its clock and the evidence about it, and no entry reason, check or photo
            # reason of the office's. The office's has none of those facts, says who entered it and why (T3), with a
            # reason that isn't spaces alone, as a void's, and is `entered` by its check and by its photo reason. Each
            # fact said to be there or not, never compared with an empty one: a comparison with an empty value is
            # "unknown", which a rule lets through, so the trusted time's rule alone would let an office line pass as
            # `device_ok`, its laptop time empty.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        device__isnull=False,
                        device_seq__isnull=False,
                        client_time__isnull=False,
                        last_server_time__isnull=False,
                        clock_error__isnull=False,
                        entry_reason="",
                    )
                    & ~models.Q(time_check=TimeCheck.ENTERED)
                    & ~models.Q(no_photo=NoPhoto.ENTERED)
                )
                | models.Q(
                    device__isnull=True,
                    device_seq__isnull=True,
                    client_time__isnull=True,
                    last_server_time__isnull=True,
                    clock_error__isnull=True,
                    created_by__isnull=False,
                    entry_reason__regex=r"\S",
                    time_check=TimeCheck.ENTERED,
                    no_photo=NoPhoto.ENTERED,
                ),
                name="staffpay_attendanceevent_from_a_laptop_or_the_office",
            ),
        ]
        # How the book of days finds a month of taps (ATT-10): the shop's lines by the time the server trusts, from
        # the shop's midnight starting the month to the one ending it. Without it, that read would search every
        # shop's lines. Leads with `shop`, as every index does. The few with no trusted time (`unverified`) are read
        # by the laptop's time instead, the only one they have; they are rare, so they need no index of their own.
        indexes = [
            models.Index(fields=["shop", "trusted_time"], name="staffpay_event_by_trusted_time"),
            # How the book finds, for each tap of a month, whether a later tap disagrees with it (ATT-11): the shop's
            # lines by the record they disagree with. Only the lines that keep one, as few do (a laptop's clock that
            # moved), so the index stays small however many taps the shop keeps.
            models.Index(
                fields=["shop", "disagrees_with"],
                name="staffpay_event_by_disagreement",
                condition=models.Q(disagrees_with__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.client_time:%Y-%m-%d %H:%M}"

    def flag_facts(self) -> FlagFacts:
        # What a flag about this tap says on its page (CTRL-4): whose, which, and the day to open, on the shop's own
        # calendar, by the book's own rule (tap_day): 00:30 on Monday in Arusha is still Sunday in UTC. Imported here,
        # not at the top: calculations.py imports this file, and each would wait for the other.
        from apps.staffpay.calculations import tap_day

        day = tap_day(self.trusted_time, self.client_time, ZoneInfo(self.shop.timezone))
        return FlagFacts(tap=FlaggedTap(staff=self.staff_id, kind=self.kind, day=day))


class AttendanceDay(ShopScoped):
    # One worker's day, as the book keeps it (ATT-10, 02 §12): what ATT-4's rule answered from that day's taps and
    # that day's rules, with the rules copied (T4), so a fine the owner raises next month leaves this month's days as
    # they were. ShopScoped (CORE-2) gives `id`, `shop`, `created_at`, `created_by` and the guard on reads;
    # `created_by` is always empty, as only the book writes a day, and the book is the system, not a person.
    #
    # Not a ledger: a day is worked out again freely until its pay run is approved (WAGE-3), as what it is worked out
    # from can still change after it is kept: a tap comes late, from a laptop that was offline; a manager voids a tap
    # (ATT-13); a job's first or last day is moved (PPL-10). Never a rule: a rule never starts on a day gone by
    # (setting.date_past, SHOP-3), and the book keeps only days gone by. So its row changes, and the edit history's
    # trigger in this table's migration keeps each change (ADR-0036): Asha's 16 Nov went from needs review to on time,
    # the day her Toka arrived from a laptop that had been offline. The trigger writes nothing when a day comes out the
    # same.
    # A manager's decision (ATT-6) sits in columns of its own, beside what the book worked out, and the book never
    # writes them (it writes only WORKED_OUT, apps/staffpay/services.py), so what the system said stays visible (A2):
    # "Siku kamili, uamuzi wa Baba · Mfumo ulisema: inahitaji uamuzi". Not Editable all the same: a version of the
    # whole row would move each time the book worked the day out again, and refuse a manager's decision for a change
    # he never saw. Two managers deciding at once are kept apart by the decision each saw (decide_day).
    # Never deleted (rule 7): nothing links to a day yet, so PROTECT can't keep it, and a trigger in the same migration
    # refuses a DELETE instead. A day that no longer counts, as its job's first day was moved later (PPL-10), keeps its
    # row, and the book no longer answers it.
    # Not on the laptops: no laptop works out a day (03 §6.6), and a worker's pay never sits on a shared device
    # (03 §6.1), so the book writes no line in the change log.
    #
    # A later card adds the lock of an approved pay run, with its migration (WAGE-3).

    # Whose day it is: a job, not a person, as an event's `staff` is. A person who left and is hired again the same day
    # has two jobs, so two days on that date, each read from its own taps (PPL-11). PROTECT: nothing is deleted.
    # No index of its own: the one-day-per-job rule below is one, and leads with `shop`.
    staff = models.ForeignKey("people.StaffMember", on_delete=models.PROTECT, related_name="+", db_index=False)
    # The day, on the shop's own calendar (02 §1), never a UTC date: Asha's tap at 21:30 UTC on Monday is Tuesday's.
    date = models.DateField()
    status = models.CharField(max_length=12, choices=DayStatus)
    # Taken off the day's pay: a late arrival's fine, copied from the rule's answer, never worked out here. Money, so
    # numeric(14,2) (rule 3, 03 §9).
    fine = models.DecimalField(max_digits=14, decimal_places=2)
    # The two taps the rule read: the first Ingia, and the first Toka after it, which ends the day (ATT-4). Minutes on
    # the shop's clock, with no seconds, as the counter showed them; empty when there was none, or none with a time
    # the server trusts. For a manager to see beside the day (ATT-5), not facts: the taps themselves are the events.
    first_in = models.TimeField(null=True, blank=True)
    first_out = models.TimeField(null=True, blank=True)
    # The day's rules as the rule read them (DayRules, apps/staffpay/calculations.py): the seven times and the two
    # fines, each as text ("07:35", "500.00"), so no amount ever passes through a float (rule 3). A copy (T4), never
    # read back as the rules: the rules are the settings, and their history is theirs. Empty on an off day, a Sunday or
    # a closed day nobody tapped on, which reads no rule, and only there, as a rule below holds. A closed day with a
    # tap keeps them, as it keeps its taps' minutes, for the owner or a manager who decides it (Jack, ATT-10).
    rules_used = models.JSONField(default=dict, blank=True)
    # Why the day needs a decision (ReviewReason, ATT-5), worked out with the rest of the day, and empty on every other
    # day. Empty too on a day to decide kept before ATT-5, as the column came empty on every row already there, until
    # the book works that day out again and writes its reason (a reason is one of the day's answers, WORKED_OUT).
    review_reason = models.CharField(max_length=15, choices=ReviewReason, blank=True)

    # The worker's part of the date's meal money (WAGE-7, 02 §15, 14): worked out with the day, so a worker's meals up
    # to any day are a sum of days already worked out, and one who leaves on the 15th is paid at once. One of the book's
    # answers (WORKED_OUT): it moves when money is typed or crossed out, when any worker's day of the date is decided or
    # its taps fixed, and when a pay rate is typed, as the date is then split again. 0 on every day with nothing to
    # share, and on all but one of a person's days of one date (_sharing, apps/staffpay/services.py). Money, so
    # numeric(14,2) (rule 3).
    meal_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # A manager's or the owner's decision on the day (ATT-6, 02 §12's `override`): what the day was, whatever the book
    # worked out. Empty until someone decides; whole once they do (a rule below). Deciding again writes over it, and the
    # edit history's trigger keeps the decision before (ADR-0036), as it keeps every change of this row.
    # What they decided: one of DECIDED.
    decided_status = models.CharField(max_length=12, choices=DayStatus, blank=True)
    # Why the worker was away, on a day decided absent, and only there: office duty is paid, the other two are not.
    absence_type = models.CharField(max_length=11, choices=AbsenceType, blank=True)
    # The fine of a day decided late or half, read from the day's first Ingia and the rules it used (day_choices,
    # apps/staffpay/calculations.py; T4), and kept: a tap that comes later doesn't change what was decided. 0 on the
    # other decisions. Money, so numeric(14,2) (rule 3).
    decided_fine = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # Who decided: a job of this shop, never the day's own worker (decide_day, T1). PROTECT: nothing is deleted. No
    # index: nothing searches days by who decided them, and nothing is deleted, so PROTECT never has to.
    decided_by = models.ForeignKey(
        "people.StaffMember", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    # Why, in their own words: "Alisahau kubonyeza Toka". Every decision says why (rule 7's who, when and why).
    decision_reason = models.TextField(blank=True)

    class Meta(ShopScoped.Meta):
        # Built on ShopScoped.Meta, so `objects`, with the guard, stays the default manager (CORE-2). No error codes on
        # these rules: only the book writes what a day was, and only decide_day writes a decision, after its own checks
        # with their codes, so a broken rule is a bug in our code, a server error and a log line, never a person's
        # mistake (ADR-0032).
        constraints = [
            # One day per job and date, however often the book runs: two managers opening the month at once, or the
            # night's job beside them, end with the same row (an upsert keyed by these three). Leads with `shop`, then
            # `date`, so it is also the index a month of the shop's days is read by.
            models.UniqueConstraint(
                fields=["shop", "date", "staff"], name="staffpay_attendanceday_one_per_job_and_date"
            ),
            # The day fits its status, and only the statuses there are, as each branch names its own. Off or absent:
            # no fine and no tap read. On time: no fine, and both taps. Late or half: both taps, and a fine of 0 or
            # more (a shop starts with no fine, ATT-2; the morning's half keeps a late arrival's fine, the owner).
            # Needs review: no fine, as a manager decides the day (ATT-6), with or without taps. A fine is never empty
            # (NOT NULL), so no comparison here meets an empty value, which a database rule lets pass.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[DayStatus.OFF, DayStatus.ABSENT],
                        fine=0,
                        first_in__isnull=True,
                        first_out__isnull=True,
                    )
                    | models.Q(status=DayStatus.ON_TIME, fine=0, first_in__isnull=False, first_out__isnull=False)
                    | models.Q(
                        status__in=[DayStatus.LATE, DayStatus.HALF],
                        fine__gte=0,
                        first_in__isnull=False,
                        first_out__isnull=False,
                    )
                    | models.Q(status=DayStatus.NEEDS_REVIEW, fine=0)
                ),
                name="staffpay_attendanceday_fits_its_status",
            ),
            # The rules kept with a day exactly when the rule read them: every day but an off one, a Sunday or a closed
            # day nobody tapped on, which reads none. A day for review keeps them too, for whoever decides it (Jack,
            # ATT-10). So a day that lost its copy, or an off day that gained one, is a bug the database refuses, as
            # the copy is what a later fix of the day reads its fine from (T4, ATT-6). `{}` is JSON's empty object.
            models.CheckConstraint(
                condition=(
                    models.Q(status=DayStatus.OFF, rules_used={})
                    | (~models.Q(status=DayStatus.OFF) & ~models.Q(rules_used={}))
                ),
                name="staffpay_attendanceday_rules_kept_unless_off",
            ),
            # A share is never below 0, which would pay a worker for eating, and never on an off day, which is nobody's
            # (WAGE-7), whatever was decided on it. No more than that: who shares reads the decision where there is one
            # (meal_part, apps/staffpay/calculations.py), and a decision is written a moment before the book's next
            # working out moves the share (decide_day), so a rule tying the two would refuse a manager's decision.
            models.CheckConstraint(
                condition=models.Q(meal_share=0) | (models.Q(meal_share__gt=0) & ~models.Q(status=DayStatus.OFF)),
                name="staffpay_attendanceday_meal_share",
            ),
            # A reason only on a day to decide, and only one of the reasons there are (ATT-5): a reason on an on-time
            # day would put it on the month page's list for nothing. Not the other way: a day to decide kept before
            # ATT-5 has none until the book works it out again, so "every day to decide has one" would refuse the rows
            # already there, and the migration with them.
            models.CheckConstraint(
                condition=(
                    models.Q(review_reason="")
                    | models.Q(status=DayStatus.NEEDS_REVIEW, review_reason__in=ReviewReason.values)
                ),
                name="staffpay_attendanceday_reason_only_to_decide",
            ),
            # A decision is whole or none (ATT-6): all six parts empty, or what, its fine, who, when and why all filled,
            # as a void's stamp is. Each filled part said to be there, as a comparison with an empty value passes a
            # rule. A reason holds at least one character that isn't a space: spaces alone are no reason (as a void's).
            models.CheckConstraint(
                condition=(
                    models.Q(
                        decided_status="",
                        absence_type="",
                        decided_fine__isnull=True,
                        decided_by__isnull=True,
                        decided_at__isnull=True,
                        decision_reason="",
                    )
                    | models.Q(
                        decided_status__in=DECIDED,
                        decided_fine__isnull=False,
                        decided_by__isnull=False,
                        decided_at__isnull=False,
                        decision_reason__regex=r"\S",
                    )
                ),
                name="staffpay_attendanceday_decision_whole_or_none",
            ),
            # And it fits what was decided: absent, with its kind, and no fine; a full day, no fine; late or half, a
            # fine of 0 or more, as the book's own (a shop starts with no fine, ATT-2). An absence kind only on an
            # absent decision. An empty decision passes here, and the rule above holds it whole.
            models.CheckConstraint(
                condition=(
                    models.Q(decided_status="")
                    | models.Q(decided_status=DayStatus.ABSENT, absence_type__in=AbsenceType.values, decided_fine=0)
                    | models.Q(decided_status=DayStatus.ON_TIME, absence_type="", decided_fine=0)
                    | models.Q(
                        decided_status__in=[DayStatus.LATE, DayStatus.HALF], absence_type="", decided_fine__gte=0
                    )
                ),
                name="staffpay_attendanceday_decision_fits_its_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date:%Y-%m-%d} {self.status}"


class PayRate(AppendOnly):
    # One worker's pay for a day, from a day on (WAGE-1, 02 §12): "from 10 Nov, Juma earns 10,000 a day". A dated rule,
    # so a ledger (rule 2), as a Setting is: a raise is a new row from its day and the old one stays, so a month with a
    # raise on the 15th pays the 10th to the 14th at the old rate. AppendOnly (CORE-3) refuses a second save() and any
    # delete() in Python, and the trigger in this table's migration refuses the same in PostgreSQL (ADR-0021). A rate
    # typed wrong is mended by a new row for the same day: of two rows on one day the one written last counts, as for a
    # setting (02 §4), and the slip stays in the history. Who set it is the row's `created_by` (ShopScoped).
    # Never on a laptop: a worker's pay never sits on a shared device (03 §6.1), so the service writes no line in the
    # change log, and no sync answer carries one. Written only by set_pay_rate (apps/staffpay/services.py), which asks
    # who may; read for a span by rates_between (apps/staffpay/selectors.py).

    # Whose rate: a job, not a person, as a day's `staff` is: a person who left and was hired again has a new job, and
    # its rates start afresh (PPL-11). PROTECT: nothing is deleted. No index of its own: the lookup below leads with
    # `shop`, then the job.
    staff = models.ForeignKey("people.StaffMember", on_delete=models.PROTECT, related_name="+", db_index=False)
    # Money, so numeric(14,2) and a Decimal, never a float (rule 3, 03 §9); above 0 and in whole shillings, as the rules
    # below hold.
    daily_rate = models.DecimalField(max_digits=14, decimal_places=2)
    # Whether the worker pays a share of the day's meals (WAGE-7): every worker does but the cook, who makes them. On
    # the rate, as it is dated too: a worker who becomes the cook mid-month pays a share up to that day and none after.
    shares_meals = models.BooleanField(default=True)
    # The shop's day the rate starts on: a business date, not a moment (02 §1). Any day of the job, gone by or still to
    # come; never before the job's first day, which the service checks, as the job's first day can be fixed (PPL-10).
    effective_from = models.DateField()
    # Why the rate changed, in the owner's own words ("Ameongezewa"); optional, as a first rate needs no reason.
    note = models.CharField(max_length=200, blank=True)

    class Meta(AppendOnly.Meta):
        # Built on AppendOnly.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2). Each rule
        # carries the code the page translates (ADR-0032), as the model's own checks (full_clean) name it to the
        # person who typed the amount; the database holds the same rules for whatever writes past them.
        constraints = [
            # A day's pay is more than nothing: a rate of 0 would pay a worker nothing while they came every day.
            models.CheckConstraint(
                condition=models.Q(daily_rate__gt=0),
                name="staffpay_payrate_above_zero",
                violation_error_code="pay_rate.amount_invalid",
            ),
            # Whole shillings, as every money rule is (Jack, 16 Nov 2026): 10,000.50 is a typo, and every screen writes
            # money with formatMoney, which has no cents. FLOOR of a whole amount is the amount itself.
            models.CheckConstraint(
                condition=models.Q(daily_rate=Floor("daily_rate")),
                name="staffpay_payrate_whole_shillings",
                violation_error_code="pay_rate.amount_invalid",
            ),
        ]
        indexes = [
            # The reads a rate is asked by: a month of the shop's rates, job by job and day by day (rates_between), and
            # one job's history, newest first (the worker's page). Leads with `shop`, as every index does (03 §9).
            models.Index(fields=["shop", "staff", "effective_from"], name="staffpay_payrate_lookup"),
        ]

    def __str__(self) -> str:
        return f"{self.daily_rate} from {self.effective_from}"


# The most one row of meal money may be (WAGE-7): see its rule below.
MOST_MEAL_MONEY = Decimal("10000000.00")


class MealMoney(AppendOnly):
    # What the shop spent on the workers' meals on one day (WAGE-7, 02 §12): the cook makes them at the shop, and the
    # workers pay for their own, out of their pay (spec §8.1). Typed each day by whoever holds meals.record, a key the
    # owner gives to whoever he chooses (Jack, 15 Nov 2026). A day may have several, flour in the morning and meat at
    # noon: its money is the sum of its rows not voided. The whole shop's, not a side's: the workers of both sides eat
    # together. Who typed it is the row's `created_by` (ShopScoped).
    # Money, so a ledger (rule 2, T2): written once, never changed or deleted. AppendOnly (CORE-3) refuses a second
    # save() and any delete() in Python, and the trigger in this table's migration refuses the same in PostgreSQL
    # (ADR-0021), all but the void stamp, filled once: a wrong amount is voided, with who, when and why, and the right
    # one typed. Never on a laptop: what a worker pays for meals is part of their pay, and pay never sits on a shared
    # device (03 §6.1), so the services write no line in the change log, and no sync answer carries one. Written only by
    # record_meal_money and void_meal_money (apps/staffpay/services.py), which ask who may.

    # The day of the meals, on the shop's own calendar: a business date, not a moment (02 §1). Today's or an earlier
    # working day's, which the service checks: a forgotten day is typed later.
    date = models.DateField()
    # Money, so numeric(14,2) and a Decimal, never a float (rule 3, 03 §9); above 0, in whole shillings and at most ten
    # million, as the rules below hold.
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    # What it bought, in the person's own words ("Unga na maharage"); optional.
    note = models.CharField(max_length=200, blank=True)
    # The void stamp (03 §5.6): empty while the row counts, filled once when it is crossed out, then frozen, as the
    # trigger makes PostgreSQL hold it. The same shape as a clock-in's. That whoever voids is of this row's shop is the
    # void service's check (T1): the database can't hold it with one column. The fourth part, `void_approval`, comes
    # with the Approval table (R1), if a void of meal money ever needs one.
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "people.StaffMember", on_delete=models.PROTECT, null=True, blank=True, related_name="+", db_index=False
    )
    void_reason = models.TextField(blank=True)

    class Meta(AppendOnly.Meta):
        # Built on AppendOnly.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2). The amount's
        # three rules carry the codes the page translates (ADR-0032), as the model's own checks (full_clean) name it to
        # the person who typed it; the database holds the same rules for whatever writes past them.
        constraints = [
            # A day's meals cost more than nothing. A row below 0 would give the workers money back, and nobody could
            # tell why: a wrong row is voided instead.
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="staffpay_mealmoney_above_zero",
                violation_error_code="meal_money.amount_invalid",
            ),
            # Whole shillings, as every amount a person types (Jack, 16 Nov 2026). FLOOR of a whole amount is itself.
            models.CheckConstraint(
                condition=models.Q(amount=Floor("amount")),
                name="staffpay_mealmoney_whole_shillings",
                violation_error_code="meal_money.amount_invalid",
            ),
            # No more than ten million: more than any day's meals, so a slip of the zeros, and an amount so big that the
            # sum of a few could pass what a column of money holds and stop the month from opening. A technical guard,
            # never a shop's rule: a day that truly costs more is typed in two rows.
            models.CheckConstraint(
                condition=models.Q(amount__lte=MOST_MEAL_MONEY),
                name="staffpay_mealmoney_at_most",
                violation_error_code="meal_money.amount_too_big",
            ),
            # Every worker pays a share of it, so it never stands with nobody's name on it. No code, here or on the next
            # rule: the route always knows who sent the request, so such a row is a bug in our code, never a person's
            # mistake.
            models.CheckConstraint(
                condition=models.Q(created_by__isnull=False), name="staffpay_mealmoney_typed_by_someone"
            ),
            # A void says who and why (T2), as CORE-3's Watch out asks of each void table: the void rule only checks
            # that the stamp is filled once. All three empty, or all three filled, the reason with at least one
            # character that isn't a space.
            models.CheckConstraint(
                condition=(
                    models.Q(voided_at__isnull=True, voided_by__isnull=True, void_reason="")
                    | models.Q(voided_at__isnull=False, voided_by__isnull=False, void_reason__regex=r"\S")
                ),
                name="staffpay_mealmoney_void_complete",
            ),
        ]
        indexes = [
            # How a span's money is read, the page's month (WAGE-7) and the book's (work_out_days), and a day's. Leads
            # with `shop`, as every index does (03 §9).
            models.Index(fields=["shop", "date"], name="staffpay_mealmoney_by_date"),
        ]

    def __str__(self) -> str:
        return f"{self.date:%Y-%m-%d} {self.amount}"
