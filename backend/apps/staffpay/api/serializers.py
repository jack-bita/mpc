"""apps/staffpay/api/serializers.py — how a worker's pay rates, a month of attendance and a worker's own month look in
the API (WAGE-1, ATT-5, ATT-12; 03 §5.10).

Thin: they describe fields and check their shape. A rate is set through set_pay_rate (apps/staffpay/services.py), which
asks who may and checks the amount and the day; the rates in force are read by the selectors (ADR-0015). The route
answers a rate (PayRateSerializer), takes a new one (PayRateCreateSerializer), and lists a worker's, with the one in
force today (PayRatesAnswer), for the worker named in the address (PayRatesQuery). Money travels as strings (rule 3).

And the month page's month (AttendanceMonthAnswer, ATT-5), worked out by attendance_month
(apps/staffpay/services.py), for the month named in the address (AttendanceMonthQuery). And a worker's own month, their
calendar's days and each tap (WorkerAttendanceAnswer, ATT-12), worked out by worker_attendance, for the same month,
each day with its decision and what it may be decided as (ATT-6). And a decision on a day (DecideDaySerializer, ATT-6),
which decide_day checks and keeps, answered as the day shows it (DayDecisionSerializer).
"""

import re
from datetime import date
from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.core.api.ids import uuid7_only
from apps.core.api.times import ZonedDateTimeField
from apps.people.models import StaffMember
from apps.staffpay.models import DECIDED, AbsenceType, ClockKind, DayChoice, DayStatus, NoPhoto, PayRate, ReviewReason
from apps.staffpay.services import DEMO_REASONS, PhotoState


class WorkerField(serializers.PrimaryKeyRelatedField[StaffMember]):
    """A worker, sent by their job's id: one of the visit's shop. Any other id is "not found" (does_not_exist), another
    shop's worker and an id no shop has alike, so the answer never tells that such a worker exists (03 §5.4). Whether
    the person may set this worker's rate is the service's own check, after this one."""

    def get_queryset(self) -> QuerySet[StaffMember]:
        # Read on each visit, inside the visit's open shop, through the guard: named in the field's arguments, the jobs
        # would be asked for while the module loads, with no shop open, and the guard would raise (CORE-2). Every job
        # of the shop: a worker belongs to the whole shop, not to a side.
        return StaffMember.objects.all()


class PayRateSerializer(serializers.ModelSerializer[PayRate]):
    # A rate as the worker's page reads it. No `shop`: it is always the visit's own. `set_by` is the nickname the page
    # shows, read through the row's `created_by`; None for one the system set, as the demo's seed does.
    set_by = serializers.CharField(source="created_by.display_name", allow_null=True, read_only=True)

    class Meta:
        model = PayRate
        fields = ["id", "staff", "daily_rate", "shares_meals", "effective_from", "note", "set_by", "created_at"]
        read_only_fields = fields


class PayRateCreateSerializer(serializers.ModelSerializer[PayRate]):
    # What the page sends for a new rate, with the id it made itself (ADR-0007). The amount's shape is checked here (a
    # number, at most two places); whether it is whole and above 0, and the day, are set_pay_rate's to check, each
    # beside its box in its own code (pay_rate.amount_invalid, pay_rate.before_first_day).
    staff = WorkerField()

    class Meta:
        model = PayRate
        fields = ["id", "staff", "daily_rate", "shares_meals", "effective_from", "note"]
        extra_kwargs = {
            # Required, and a UUIDv7, as for a new rule (SettingCreateSerializer): the route looks the id up itself.
            "id": {"required": True, "validators": [uuid7_only]},
            # Required: the page always says, so a form that forgot the question never makes the cook pay for meals.
            "shares_meals": {"required": True},
        }


class PayRatesQuery(serializers.Serializer[Any]):
    # Whose rates: a job's id, in the address (?staff=…). One that is no id is refused under `staff` (400 invalid).
    staff = serializers.UUIDField(help_text="The worker's job.")


# many=False, as for the settings' and closures' answers (apps/shops/api/serializers.py): the answer is one object, not
# a list, though the route's action is `list`; without it the schema, and so the app's types, would say a list of them.
@extend_schema_serializer(many=False)
class PayRatesAnswer(serializers.Serializer[Any]):
    # A worker's rates, newest first, as the page's history shows them; the shop's today, from which the form's date
    # starts; and the one in force today, which the page shows first ("Sasa"), or none: worked out here, on the shop's
    # own date, as a phone's date can be wrong.
    today = serializers.DateField()
    in_force = serializers.UUIDField(allow_null=True, help_text="The rate in force on the shop's today, or none.")
    rates = PayRateSerializer(many=True)


# A month as the address and the answer write it: four figures, a dash, two figures (01 to 12). The page writes the same
# (isMonth, frontend/src/features/attendance/attendance-month.ts).
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
# No month before this one: no shop's attendance can be in it, and near the calendar's first day a month's first
# midnight in Arusha, three hours ahead of UTC, falls before UTC's first day, which the database can't be asked for.
FIRST_MONTH = date(2000, 1, 1)


@extend_schema_field({"type": "string", "pattern": MONTH_PATTERN, "example": "2026-11"})
class MonthField(serializers.Field[date, str, str, Any]):
    """A month, "2026-11", read as its first day and written back as "2026-11". Strict, where a date field reading
    "%Y-%m" took "2026-1" too, and its description said a whole date, "2026-11-01", which the route never took nor sent
    (ATT-5's review)."""

    default_error_messages = {"invalid": "A month is written as 2026-11, from 2000-01 on."}

    def to_internal_value(self, data: Any) -> date:
        if not isinstance(data, str) or not re.fullmatch(MONTH_PATTERN, data):
            self.fail("invalid")
        month = date(int(data[:4]), int(data[5:7]), 1)
        if month < FIRST_MONTH:
            self.fail("invalid")
        return month

    def to_representation(self, value: date) -> str:
        return value.strftime("%Y-%m")


class AttendanceMonthQuery(serializers.Serializer[Any]):
    # Which month, in the address (?month=2026-11), as the page keeps it. Anything else, a day, "2026-13" or "2026-1",
    # is refused under `month` (400 invalid), and the month page never sends one.
    month = MonthField(help_text="The month, as 2026-11.")


class WorkerMonthSerializer(serializers.Serializer[Any]):
    # One worker's line: their job, the nickname the page shows, and how many days of the month were each kind. No
    # amount: a manager who fixes attendance sees who is paid by the day, never what (WAGE-1's review).
    staff = serializers.UUIDField(source="staff_id")
    display_name = serializers.CharField()
    on_time = serializers.IntegerField()
    late = serializers.IntegerField()
    half = serializers.IntegerField()
    absent = serializers.IntegerField()
    needs_review = serializers.IntegerField()


class DayToDecideSerializer(serializers.Serializer[Any]):
    # One day a person must decide: whose, which, and why (ATT-5), with the two taps the rule read, as minutes on the
    # shop's clock, "09:10", for "alifika saa 09:10". The reason is one of the book's codes, which the page says in
    # its language (ADR-0040).
    staff = serializers.UUIDField(source="staff_id")
    display_name = serializers.CharField(source="staff.display_name")
    date = serializers.DateField()
    reason = serializers.ChoiceField(choices=ReviewReason.choices, source="review_reason")
    first_in = serializers.TimeField(format="%H:%M", allow_null=True)
    first_out = serializers.TimeField(format="%H:%M", allow_null=True)


# One object, not a list, as for the pay rates' answer above.
@extend_schema_serializer(many=False)
class AttendanceMonthAnswer(serializers.Serializer[Any]):
    # The month page's answer (ATT-5): which month, as "2026-11"; the shop's today, so the page says this month's counts
    # reach yesterday, on the shop's own date, as a phone's can be wrong; a line per worker; and the days to decide.
    month = MonthField()
    today = serializers.DateField()
    working_day_over = serializers.BooleanField(
        help_text="Whether a working day of the month is over: with none, nobody is listed for want of a day."
    )
    workers = WorkerMonthSerializer(many=True)
    to_decide = DayToDecideSerializer(many=True)


class DayDecisionSerializer(serializers.Serializer[Any]):
    # A person's decision on a day (ATT-6), as the day shows it: "Siku kamili · uamuzi wa Baba, 20/11 · Sababu: …". What
    # was decided, one of the four a person may decide; the absence's kind on an absent day, else null; its fine, a
    # string (rule 3); who, by nickname; when, which the page sends back as `replaces` when it decides again; and why.
    # On the demo the reason is a ready one's code (`forgot_toka`), which the page says in words.
    status = serializers.ChoiceField(choices=[(status.value, status.label) for status in DECIDED])
    absence_type = serializers.ChoiceField(choices=AbsenceType.choices, allow_null=True)
    fine = serializers.DecimalField(max_digits=14, decimal_places=2)
    by = serializers.CharField()
    at = serializers.DateTimeField()
    reason = serializers.CharField()


class DayOptionSerializer(serializers.Serializer[Any]):
    # One line of the sheet (ATT-6): a choice and the fine it takes, worked out on the server from the day's first Ingia
    # and its own rules (day_choices), so the sheet shows "Amechelewa · faini 500" with no sum of its own.
    choice = serializers.ChoiceField(choices=DayChoice.choices)
    fine = serializers.DecimalField(max_digits=14, decimal_places=2)


class WorkerDaySerializer(serializers.Serializer[Any]):
    # One of a worker's days, as their calendar marks it (ATT-12): what it was, why it waits on a day to decide (one of
    # the book's codes, which the page says in its language, ADR-0040), else null, and its fine, a string (rule 3). The
    # fine is the shop's own rule, which anyone working there may read; never the worker's rate or the day's pay. And
    # the two taps the rule read, as minutes on the shop's clock, for "alifika saa 09:10", as DayToDecide sends them.
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=DayStatus.choices)
    reason = serializers.ChoiceField(choices=ReviewReason.choices, allow_null=True)
    fine = serializers.DecimalField(max_digits=14, decimal_places=2)
    first_in = serializers.TimeField(format="%H:%M", allow_null=True)
    first_out = serializers.TimeField(format="%H:%M", allow_null=True)
    # A person's decision, beside what the book said, which stays (A2), or null; and what the day may be decided as,
    # in the sheet's order: none on an off day, or on the viewer's own month (ATT-6).
    decision = DayDecisionSerializer(allow_null=True)
    choices = DayOptionSerializer(many=True)


class TapPhotoSerializer(serializers.Serializer[Any]):
    # A tap's photo: the id the photo route opens (`/api/v1/control/attachments/{id}/file/`, CTRL-3), and whether its
    # file came, hasn't come yet, or was taken away. The page shows a photo only when it is `kept`.
    id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=PhotoState.choices)


# Why a tap itself is in doubt (ATT-11): the two of the book's reasons a single tap can carry. The others are a day's.
TAP_DOUBTS = [(reason.value, reason.label) for reason in (ReviewReason.NOT_WORKING, ReviewReason.CLOCK_DISAGREES)]


class AttendanceTapSerializer(serializers.Serializer[Any]):
    # One tap, as the day under the calendar shows it: "Ingia 07:20 asubuhi · Laptop ya Dawa", then its photo or why it
    # has none. Minutes on the shop's clock, "07:20", worked out on the server, so a phone in another zone never moves
    # them; `time` null for a tap whose time the server doesn't trust, which shows its laptop's own (`laptop_time`).
    id = serializers.UUIDField()
    date = serializers.DateField()
    kind = serializers.ChoiceField(choices=ClockKind.choices)
    time = serializers.TimeField(format="%H:%M", allow_null=True)
    laptop_time = serializers.TimeField(format="%H:%M")
    laptop = serializers.CharField()
    photo = TapPhotoSerializer(allow_null=True)
    no_photo = serializers.ChoiceField(choices=NoPhoto.choices, allow_null=True)
    doubt = serializers.ChoiceField(choices=TAP_DOUBTS, allow_null=True)


# One object, not a list, as for the month's answer above.
@extend_schema_serializer(many=False)
class WorkerAttendanceAnswer(serializers.Serializer[Any]):
    # A worker's month, as their calendar shows it (ATT-12): which month; the shop's today, which the calendar marks
    # (•), on the shop's own date; the worker's line, as the month page counts it; their first and last day, for a
    # day outside them to say why; each day the book answers for them, up to yesterday; and each tap of the month,
    # today's too. No amount but the fines: a manager who fixes attendance sees no one's pay (WAGE-1's review).
    month = MonthField()
    today = serializers.DateField()
    worker = WorkerMonthSerializer()
    started_on = serializers.DateField()
    left_on = serializers.DateField(allow_null=True)
    days = WorkerDaySerializer(many=True)
    taps = AttendanceTapSerializer(many=True)
    yours = serializers.BooleanField(
        help_text="Whether the month is the viewer's own: then none of its days is theirs to decide (ATT-6)."
    )
    ready_reasons = serializers.ListField(
        child=serializers.ChoiceField(choices=DEMO_REASONS),
        help_text="On the demo, the ready reasons a decision may take, as codes; elsewhere none (ATT-6).",
    )


class DecideDaySerializer(serializers.Serializer[Any]):
    # A decision on a day, as the sheet sends it (ATT-6): one of the sheet's six choices; why, in the person's own
    # words, or a ready reason's code on the demo; and when the decision the page showed was made, or null for none,
    # so a decision made meanwhile by someone else is never written over (409). The reason may come empty here:
    # decide_day refuses it with its own code (day.reason_missing), beside the box, as it refuses the rest.
    choice = serializers.ChoiceField(choices=DayChoice.choices)
    reason = serializers.CharField(max_length=200, allow_blank=True)
    # A time the server sent, sent back: with its zone, as every time a client sends must name one (ATT-1's review).
    replaces = ZonedDateTimeField(allow_null=True)
