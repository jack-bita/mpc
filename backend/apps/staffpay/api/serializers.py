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
which decide_day checks and keeps, answered as the day shows it (DayDecisionSerializer). And a manager's fixes to the
taps (ATT-13): a tap added (AddTapSerializer) and a tap crossed out (VoidTapSerializer), which add_tap and void_tap
check and keep, each answered as the day shows the tap (TapAnswer).

And the day's meal money (WAGE-7): the days of a span, with their total (MealMoneyDaysAnswer), worked out by
meal_money_days, for the span in the address (MealMoneyQuery); and a row typed (RecordMealMoneySerializer) or crossed
out (VoidMealMoneySerializer), which record_meal_money and void_meal_money check and keep, each answered as the day's
page shows it (MealMoneyAnswer).
"""

import re
from datetime import date, timedelta
from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.core.api.ids import uuid7_only
from apps.core.api.times import ZonedDateTimeField
from apps.people.models import StaffMember
from apps.staffpay.models import (
    DECIDED,
    AbsenceType,
    AttendanceEvent,
    ClockKind,
    DayChoice,
    DayStatus,
    MealMoney,
    NoPhoto,
    PayRate,
    ReviewReason,
)
from apps.staffpay.services import (
    DEMO_ADD_REASONS,
    DEMO_MEAL_VOID_REASONS,
    DEMO_REASONS,
    DEMO_VOID_REASONS,
    PhotoState,
    meal_line,
    tap_line,
)


# A job's id, as the schema says: a field with no model can't tell the schema its type by itself, as in the sheet that
# adds a tap (AddTapSerializer, ATT-13), so it says so here, as a uuid, which is what a model's field already gives it.
@extend_schema_field({"type": "string", "format": "uuid"})
class WorkerField(serializers.PrimaryKeyRelatedField[StaffMember]):
    """A worker, sent by their job's id: one of the visit's shop. Any other id is "not found" (does_not_exist), another
    shop's worker and an id no shop has alike, so the answer never tells that such a worker exists (03 §5.4). Whether
    the person may set this worker's rate, or fix their taps, is the service's own check, after this one."""

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
    # Its id, the address the sheet sends a decision on it to (attendance-days/{id}/decide/, ATT-6).
    id = serializers.UUIDField()
    date = serializers.DateField()
    status = serializers.ChoiceField(choices=DayStatus.choices)
    reason = serializers.ChoiceField(choices=ReviewReason.choices, allow_null=True)
    fine = serializers.DecimalField(max_digits=14, decimal_places=2)
    meal_share = serializers.DecimalField(
        max_digits=14, decimal_places=2, help_text="The worker's share of the day's meal money, as the book kept it."
    )
    first_in = serializers.TimeField(format="%H:%M", allow_null=True)
    first_out = serializers.TimeField(format="%H:%M", allow_null=True)
    # A person's decision, beside what the book said, which stays (A2), or null; and what the day may be decided as,
    # in the sheet's order: none on an off day, or on the viewer's own month (ATT-6).
    decision = DayDecisionSerializer(allow_null=True)
    choices = DayOptionSerializer(many=True)
    taps_changed = serializers.BooleanField(
        help_text="Whether a tap of the day was added, arrived or was crossed out after the day was decided (ATT-13)."
    )


class TapPhotoSerializer(serializers.Serializer[Any]):
    # A tap's photo: the id the photo route opens (`/api/v1/control/attachments/{id}/file/`, CTRL-3), and whether its
    # file came, hasn't come yet, or was taken away. The page shows a photo only when it is `kept`.
    id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=PhotoState.choices)


class TapStampSerializer(serializers.Serializer[Any]):
    # Who added a tap in the office, or crossed one out (ATT-13), by nickname; when; and why. On the demo the reason is
    # a ready one's code (`forgot_tap`, `wrong_tap`), which the page says in words.
    by = serializers.CharField()
    at = serializers.DateTimeField()
    reason = serializers.CharField()


# Why a tap itself is in doubt (ATT-11): the two of the book's reasons a single tap can carry. The others are a day's.
TAP_DOUBTS = [(reason.value, reason.label) for reason in (ReviewReason.NOT_WORKING, ReviewReason.CLOCK_DISAGREES)]


class AttendanceTapSerializer(serializers.Serializer[Any]):
    # One tap, as the day under the calendar shows it: "Ingia 07:20 asubuhi · Laptop ya Dawa", then its photo or why it
    # has none. Minutes on the shop's clock, "07:20", worked out on the server, so a phone in another zone never moves
    # them; `time` null for a tap whose time the server doesn't trust, which shows its laptop's own (`laptop_time`).
    # `laptop` and `laptop_time` null for a tap a manager entered in the office, which no laptop made (ATT-13).
    id = serializers.UUIDField()
    date = serializers.DateField()
    kind = serializers.ChoiceField(choices=ClockKind.choices)
    time = serializers.TimeField(format="%H:%M", allow_null=True)
    laptop_time = serializers.TimeField(format="%H:%M", allow_null=True)
    laptop = serializers.CharField(allow_null=True)
    photo = TapPhotoSerializer(allow_null=True)
    no_photo = serializers.ChoiceField(choices=NoPhoto.choices, allow_null=True)
    doubt = serializers.ChoiceField(choices=TAP_DOUBTS, allow_null=True)
    # Who entered it in the office, when and why, or null for a laptop's tap; who crossed it out, when and why, or null
    # while it counts (ATT-13). A tap crossed out still comes, for the day to show it struck through (A2).
    entered = TapStampSerializer(allow_null=True)
    voided = TapStampSerializer(allow_null=True)


# One object, not a list, as for the month's answer above.
@extend_schema_serializer(many=False)
class WorkerAttendanceAnswer(serializers.Serializer[Any]):
    # A worker's month, as their calendar shows it (ATT-12): which month; the shop's today, which the calendar marks
    # (•), on the shop's own date; the worker's line, as the month page counts it; their first and last day, for a
    # day outside them to say why; each day the book answers for them, up to yesterday; and each tap of the month,
    # today's too. No amount but the fines and the meals' shares, the same for everyone who came: a manager who fixes
    # attendance sees no one's pay (WAGE-1's review).
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
    ready_add_reasons = serializers.ListField(
        child=serializers.ChoiceField(choices=DEMO_ADD_REASONS),
        help_text="On the demo, the ready reasons a tap added may take, as codes; elsewhere none (ATT-13).",
    )
    ready_void_reasons = serializers.ListField(
        child=serializers.ChoiceField(choices=DEMO_VOID_REASONS),
        help_text="On the demo, the ready reasons a tap crossed out may take, as codes; elsewhere none (ATT-13).",
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


class AddTapSerializer(serializers.Serializer[Any]):
    # A tap added in the office, as the sheet sends it (ATT-13): its id, made on the phone (ADR-0007), required and a
    # UUIDv7, as every create's; whose tap, a job of the visit's shop (WorkerField: another shop's "not found", as an
    # id no shop has); Ingia or Toka; the day; the minute on the shop's clock, "18:45", never with seconds, as the sheet
    # sends a minute; and why. The reason may come empty here: add_tap refuses it with its own code
    # (tap.reason_missing), beside the box, as it refuses the rest.
    id = serializers.UUIDField(validators=[uuid7_only])
    staff = WorkerField()
    kind = serializers.ChoiceField(choices=ClockKind.choices)
    date = serializers.DateField()
    time = serializers.TimeField(input_formats=["%H:%M"])
    reason = serializers.CharField(max_length=200, allow_blank=True)


class VoidTapSerializer(serializers.Serializer[Any]):
    # A tap crossed out, as the sheet sends it (ATT-13): why. Empty here is void_tap's to refuse, beside the box.
    reason = serializers.CharField(max_length=200, allow_blank=True)


class TapAnswer(AttendanceTapSerializer):
    # A tap added or crossed out, answered as the day under the calendar shows it, so the sheet can show it at once:
    # read afresh by tap_line, as a worker's month reads its taps, its laptop, photo, doubt and who added or crossed it
    # out. The fields are AttendanceTapSerializer's own, so the schema describes the answer by itself, and the route
    # needs no `create` of its own to name it (AttendanceTapViewSet, whose key check rests on that). Only answers: what
    # a fix sends is AddTapSerializer's and VoidTapSerializer's.
    def to_representation(self, instance: AttendanceEvent) -> Any:
        return super().to_representation(tap_line(instance))


# The most days one answer of meal money covers: a leap year's whole. The book works every one of them out, so a span is
# kept to what a person would ask for.
MOST_DAYS = timedelta(days=366)


class MealMoneyQuery(serializers.Serializer[Any]):
    # Which days, in the address (?first=2026-11-01&last=2026-11-30), both counted: the page's month, or the days chosen
    # in Chagua siku, where Hadi before Kuanzia, or more than a year of them, is said beside Hadi in its own words. No
    # day before 2000, as for a month (FIRST_MONTH): no shop's attendance is older.
    first = serializers.DateField(help_text="The first day, as 2026-11-01.")
    last = serializers.DateField(help_text="The last day, counted, as 2026-11-30.")

    def validate_first(self, value: date) -> date:
        if value < FIRST_MONTH:
            raise serializers.ValidationError("Days start from 2000-01-01.", code="invalid")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # English for the logs; the screens translate the code (ADR-0032).
        if attrs["last"] < attrs["first"]:
            raise serializers.ValidationError(
                {"last": ["The last day is before the first."]}, code="meal_money.days_backwards"
            )
        if attrs["last"] - attrs["first"] >= MOST_DAYS:
            raise serializers.ValidationError({"last": ["At most a year of days."]}, code="meal_money.too_many_days")
        return attrs


class VoidedMealMoneySerializer(serializers.Serializer[Any]):
    # Who crossed out a row of meal money, by nickname; when; and why. On the demo the reason is a ready one's code
    # (`wrong_amount`), which the page says in words.
    by = serializers.CharField()
    at = serializers.DateTimeField()
    reason = serializers.CharField()


class MealMoneyLineSerializer(serializers.Serializer[Any]):
    # One row of a day's meal money, as the day's page shows it: how much, a string (rule 3), for what, who typed it, by
    # nickname, and when; and who crossed it out, or null while it counts. A row crossed out still comes, for the day to
    # show it struck through (A2).
    id = serializers.UUIDField()
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField()
    by = serializers.CharField()
    at = serializers.DateTimeField()
    voided = VoidedMealMoneySerializer(allow_null=True)


class MealDaySerializer(serializers.Serializer[Any]):
    # One day of Hela ya chakula: its money and each one's share, strings (rule 3), and the two counts. No name: whoever
    # types the meal money sees how many share it, and who came is the attendance pages' to show.
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="The rows that count, added up.")
    over = serializers.BooleanField(help_text="Whether the day is over: today is not, so its money isn't split yet.")
    sharers = serializers.IntegerField(help_text="How many workers share the day's money.")
    share = serializers.DecimalField(
        max_digits=14, decimal_places=2, help_text="What each of them pays, as the book kept it."
    )
    waiting = serializers.IntegerField(help_text="How many workers' days still wait for a decision.")
    rows = MealMoneyLineSerializer(many=True)


# One object, not a list, as for the month's answer above.
@extend_schema_serializer(many=False)
class MealMoneyDaysAnswer(serializers.Serializer[Any]):
    # Hela ya chakula's answer (WAGE-7): the span, its last day no later than the shop's today unless it is all to come;
    # today, on the shop's own date, as a phone's can be wrong; the whole of the money; and its days, newest first.
    first = serializers.DateField()
    last = serializers.DateField()
    today = serializers.DateField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    days = MealDaySerializer(many=True)
    ready_void_reasons = serializers.ListField(
        child=serializers.ChoiceField(choices=DEMO_MEAL_VOID_REASONS),
        help_text="On the demo, the ready reasons a row may be crossed out with, as codes; elsewhere none.",
    )


class RecordMealMoneySerializer(serializers.Serializer[Any]):
    # Meal money as the sheet sends it (WAGE-7): its id, made on the phone (ADR-0007), required and a UUIDv7, as every
    # create's; the day; the amount, a string; and what it bought, which may be left out. The amount's shape is checked
    # here (a number, at most two places); whether it is whole, above 0 and no slip of the zeros, and the day, are
    # record_meal_money's, each beside its box in its own code.
    id = serializers.UUIDField(validators=[uuid7_only])
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField(max_length=200, allow_blank=True, default="")


class VoidMealMoneySerializer(serializers.Serializer[Any]):
    # Meal money crossed out, as the sheet sends it: why. Empty here is void_meal_money's to refuse, beside the box.
    reason = serializers.CharField(max_length=200, allow_blank=True)


class MealMoneyAnswer(MealMoneyLineSerializer):
    # A row typed or crossed out, answered as the day's page shows it (meal_line). The fields are
    # MealMoneyLineSerializer's own, so the schema describes the answer by itself, as a tap's does (TapAnswer).
    def to_representation(self, instance: MealMoney) -> Any:
        return super().to_representation(meal_line(instance))
