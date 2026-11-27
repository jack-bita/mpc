"""apps/staffpay/api/serializers.py — how a worker's pay rates, a month of attendance and a worker's own month look in
the API (WAGE-1, ATT-5, ATT-12; 03 §5.10).

Thin: they describe fields and check their shape. A rate is set through set_pay_rate
(apps/staffpay/services/money.py), which asks who may and checks the amount and the day; the rates in force are read by
the selectors (ADR-0015). The route answers a rate (PayRateSerializer), takes a new one (PayRateCreateSerializer), and
lists a worker's, with the one in force today (PayRatesAnswer), for the worker named in the address (PayRatesQuery).
Money travels as strings (rule 3).

And the month page's month (AttendanceMonthAnswer, ATT-5), worked out by attendance_month
(apps/staffpay/services/attendance.py), for the month named in the address (AttendanceMonthQuery). And a worker's own
month, their calendar's days and each tap (WorkerAttendanceAnswer, ATT-12), worked out by worker_attendance, for the
same month, each day with its decision and what it may be decided as (ATT-6). And a decision on a day
(DecideDaySerializer, ATT-6), which decide_day checks and keeps, answered as the day shows it (DayDecisionSerializer).
And a manager's fixes to the taps (ATT-13): a tap added (AddTapSerializer) and a tap crossed out (VoidTapSerializer),
which add_tap and void_tap check and keep, each answered as the day shows the tap (TapAnswer).

And the day's meal money (WAGE-7): the days of a span, with their total (MealMoneyDaysAnswer), worked out by
meal_money_days, for the span in the address (MealMoneyQuery); and a row typed (RecordMealMoneySerializer) or crossed
out (VoidMealMoneySerializer), which record_meal_money and void_meal_money check and keep, each answered as the day's
page shows it (MealMoneyAnswer).

And money given before payday (WAGE-8), for the month in the address (AttendanceMonthQuery): the month's, and whom one
may be typed for (AdvancesMonthAnswer), read by advances_month; one, for its own page (AdvancePageAnswer); and one typed
(RecordAdvanceSerializer) or crossed out (VoidAdvanceSerializer), which record_advance and void_advance check and keep,
each answered as the pages show it (AdvanceAnswer).

And the month's pay (WAGE-2), for the month in the address (AttendanceMonthQuery): everyone's (PayMonthAnswer), worked
out by pay_month, and one worker's (WorkerPayMonthAnswer), by worker_pay, each line by line, with who approved it, or
what its approval waits for (WAGE-3). And its approval: a month's (ApproveMonthSerializer), kept by approve_month, and
one worker's alone (ApproveLeaverSerializer), by approve_leaver.

And handing a payslip out (WAGE-9): each payslip's payments on its worker's line (PaymentLineSerializer), and the
month's Bado kulipa; a payment by M-Pesa or a bank (PayPayslipSerializer), or in cash with the signature's drawing as
the request's body, its ids in the address (PayCashQuery), which pay_payslip checks and keeps; and one crossed out
(VoidPaymentSerializer), by void_payslip_payment, each answered as the payslip shows it (PaymentLineSerializer).
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
from apps.staffpay.calculations import PaidAs
from apps.staffpay.models import (
    DECIDED,
    AbsenceType,
    Advance,
    AttendanceEvent,
    ClockKind,
    DayChoice,
    DayStatus,
    MealMoney,
    NoPhoto,
    NoSignature,
    PayCorrection,
    PaymentMethod,
    PayRate,
    PayRun,
    Payslip,
    ReviewReason,
)
from apps.staffpay.models import LONGEST_REFERENCE as _LONGEST_REFERENCE
from apps.staffpay.services import (
    DEMO_ADD_REASONS,
    DEMO_MONEY_VOID_REASONS,
    DEMO_REASONS,
    DEMO_VOID_REASONS,
    PhotoState,
    advance_line,
    correction_line,
    keeps_signatures,
    meal_line,
    ready_correction_reasons,
    ready_correction_void_reasons,
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
    # own date, as a phone's date can be wrong. And whether no rate may be typed any more, of one who left and whose pay
    # up to their last day is approved (WAGE-3's review): the page then offers no button the server would only refuse.
    today = serializers.DateField()
    in_force = serializers.UUIDField(allow_null=True, help_text="The rate in force on the shop's today, or none.")
    closed = serializers.BooleanField(
        help_text="Whether the worker left and the pay of their last day is approved: no rate can be typed any more."
    )
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
    closed = serializers.BooleanField(
        help_text="Whether the month's pay is approved: then its days take no decision and its taps no fix (WAGE-3)."
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
        child=serializers.ChoiceField(choices=DEMO_MONEY_VOID_REASONS),
        help_text="On the demo, the ready reasons a row may be crossed out with, as codes; elsewhere none.",
    )
    closed_to = serializers.DateField(
        allow_null=True,
        help_text="The last day whose pay is approved, or none: no money up to it is typed or crossed out (WAGE-3).",
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


class VoidedAdvanceSerializer(serializers.Serializer[Any]):
    # Who crossed out an advance, by nickname; when; and why. On the demo the reason is a ready one's code
    # (`wrong_amount`), which the page says in words.
    by = serializers.CharField()
    at = serializers.DateTimeField()
    reason = serializers.CharField()


class AdvanceLineSerializer(serializers.Serializer[Any]):
    # One advance, as Advansi's line and its own page show it (WAGE-8): whose, by their job and nickname; the day; how
    # much, a string (rule 3), for what; who typed it, by nickname, and when; and who crossed it out, or null while it
    # counts. One crossed out still comes, to be shown struck through (A2).
    id = serializers.UUIDField()
    staff = serializers.UUIDField(source="staff_id")
    display_name = serializers.CharField()
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField()
    by = serializers.CharField()
    at = serializers.DateTimeField()
    voided = VoidedAdvanceSerializer(allow_null=True)


class AdvanceWorkerSerializer(serializers.Serializer[Any]):
    # A worker one may be typed for: the job, the nickname, and their last day if they left. Nothing of their pay.
    staff = serializers.UUIDField(source="staff_id")
    display_name = serializers.CharField()
    left_on = serializers.DateField(allow_null=True)


# One object, not a list, as for the month's answer above.
@extend_schema_serializer(many=False)
class AdvancesMonthAnswer(serializers.Serializer[Any]):
    # Advansi's answer (WAGE-8): the month; the shop's today, as a phone's date can be wrong; the sum of those that
    # count; every one of it, newest first; and whom one may be typed for, by name.
    month = MonthField()
    today = serializers.DateField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Those not crossed out, added up.")
    rows = AdvanceLineSerializer(many=True)
    workers = AdvanceWorkerSerializer(many=True)
    closed = serializers.BooleanField(
        help_text="Whether the month's pay is approved: then none is typed in it, or crossed out (WAGE-3)."
    )


class AdvancePageAnswer(serializers.Serializer[Any]):
    # One advance, as its own page reads it (WAGE-8): the very line of the list; whether it is the asker's own, whom the
    # page offers no Batilisha (Jack: A); and the reasons its sheet offers on the demo.
    advance = AdvanceLineSerializer()
    own = serializers.BooleanField(help_text="Whether it was given to the person asking, by whichever job of theirs.")
    closed = serializers.BooleanField(
        help_text="Whether the pay it comes off is approved, the month's or the worker's alone (WAGE-3)."
    )
    ready_void_reasons = serializers.ListField(
        child=serializers.ChoiceField(choices=DEMO_MONEY_VOID_REASONS),
        help_text="On the demo, the ready reasons it may be crossed out with, as codes; elsewhere none.",
    )


class RecordAdvanceSerializer(serializers.Serializer[Any]):
    # An advance as the sheet sends it (WAGE-8): its id, made on the phone (ADR-0007), required and a UUIDv7, as every
    # create's; whose, a job of the visit's shop (WorkerField: another shop's "not found", as an id no shop has); the
    # day; the amount, a string; and what it was for, which may be left out. The amount's shape is checked here (a
    # number, at most two places); the rest is record_advance's, each beside its box in its own code.
    id = serializers.UUIDField(validators=[uuid7_only])
    staff = WorkerField()
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    note = serializers.CharField(max_length=200, allow_blank=True, default="")


class VoidAdvanceSerializer(serializers.Serializer[Any]):
    # An advance crossed out, as the sheet sends it: why. Empty here is void_advance's to refuse, beside the box.
    reason = serializers.CharField(max_length=200, allow_blank=True)


class AdvanceAnswer(AdvanceLineSerializer):
    # One typed or crossed out, answered as the pages show it (advance_line). The fields are AdvanceLineSerializer's
    # own, so the schema describes the answer by itself, as a tap's does (TapAnswer).
    def to_representation(self, instance: Advance) -> Any:
        return super().to_representation(advance_line(instance))


class PayLineSerializer(serializers.Serializer[Any]):
    # One line of a worker's pay (WAGE-2): so many full days, or half ones, at so much each, and what they come to. The
    # amounts are strings (rule 3), and the page multiplies nothing itself.
    paid_as = serializers.ChoiceField(
        choices=[(kind.value, kind.value) for kind in (PaidAs.FULL, PaidAs.HALF)], source="paid_as.value"
    )
    days = serializers.IntegerField()
    each = serializers.DecimalField(max_digits=14, decimal_places=2)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class PaySerializer(serializers.Serializer[Any]):
    # A worker's pay over some days (Pay, apps/staffpay/calculations.py): the lines, the full days first; the fines and
    # the meals, each with how many days; the money given before payday (WAGE-8) and a debt carried from an earlier
    # month (WAGE-3), on the days that are over and never on today's part; the corrections of mistakes found after an
    # earlier month's approval, their sum, plus or minus (WAGE-10), on the same part; how many days wait for a decision,
    # and how many paid days have no rate, neither paid; and what is left, which may be below 0.
    lines = PayLineSerializer(many=True)
    fined_days = serializers.IntegerField()
    fines = serializers.DecimalField(max_digits=14, decimal_places=2)
    meal_days = serializers.IntegerField()
    meals = serializers.DecimalField(max_digits=14, decimal_places=2)
    advances = serializers.DecimalField(max_digits=14, decimal_places=2)
    carried = serializers.DecimalField(max_digits=14, decimal_places=2)
    corrections = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Plus or minus (WAGE-10).")
    waiting = serializers.IntegerField()
    no_rate = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)


class ApprovalSerializer(serializers.Serializer[Any]):
    # Who approved a month's pay, or one worker's alone, by nickname, and when (WAGE-3).
    by = serializers.CharField()
    at = serializers.DateTimeField()


class OpenDaySerializer(serializers.Serializer[Any]):
    # A day that stops an approval, as the sheet names it and opens it (WAGE-3).
    staff = serializers.UUIDField(source="staff_id")
    display_name = serializers.CharField()
    date = serializers.DateField()


class QuietLaptopSerializer(serializers.Serializer[Any]):
    # A laptop that has sent nothing since the pay's last day was over, and when it last did, or null for never.
    name = serializers.CharField()
    last_synced_at = serializers.DateTimeField(allow_null=True)


class ToApproveSerializer(serializers.Serializer[Any]):
    # What an approval waits for, and what it warns of (WAGE-3): nothing to wait for when `earlier` is null,
    # `still_clocked_in` false, and both lists of days empty; the server asks it all again as it approves.
    earlier = MonthField(allow_null=True, help_text="An earlier month whose pay is still open, or none.")
    waiting = OpenDaySerializer(many=True, help_text="Days that wait for a decision, the oldest first.")
    no_rate = OpenDaySerializer(many=True, help_text="Days to pay that have no daily rate, the oldest first.")
    still_clocked_in = serializers.BooleanField(
        help_text="Whether the worker, alone, has not tapped Toka on their last evening."
    )
    quiet_laptops = QuietLaptopSerializer(many=True, help_text="A warning: their taps may be missing.")
    came_unpaid = serializers.ListField(
        child=serializers.CharField(), help_text="A warning: who came with no daily pay, by nickname."
    )


class VoidedPaymentSerializer(serializers.Serializer[Any]):
    # Who crossed out a payment, by nickname, when and why (WAGE-9). On the demo the reason is a ready one's code.
    by = serializers.CharField()
    at = serializers.DateTimeField()
    reason = serializers.CharField()


class PaymentLineSerializer(serializers.Serializer[Any]):
    # One handing-out of a payslip, as its foot shows it (WAGE-9): "Amelipwa taslimu na Baba · 2/12/2026 08:10", the
    # number of one by M-Pesa or a bank, the amount, the signature's photo, opened at the attachments' own address with
    # the two keys of pay (CTRL-3), or why there is none (on the demo), and who crossed it out, or null while it counts.
    id = serializers.UUIDField()
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(help_text="The transaction number; empty for cash.")
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    by = serializers.CharField()
    at = serializers.DateTimeField()
    signature = serializers.UUIDField(
        source="signature_id", allow_null=True, help_text="The signature's attachment, for cash; else none."
    )
    no_signature = serializers.ChoiceField(
        choices=[("", "")] + NoSignature.choices,
        help_text="Why cash has no signature: on the demo, none is kept. Empty otherwise.",
    )
    voided = VoidedPaymentSerializer(allow_null=True, help_text="Who crossed it out, or none while it counts.")


class WorkerPaySerializer(serializers.Serializer[Any]):
    # One worker's line of Mishahara, and their own page's: whose, and their last day if they left; the days that are
    # over; today alone, once they tapped Toka, or null (Leo); and what is left to pay, the two together. The month a
    # debt among them is from; and who approved it, once a payslip keeps it (WAGE-3).
    staff = serializers.UUIDField(source="staff_id")
    display_name = serializers.CharField()
    left_on = serializers.DateField(allow_null=True)
    pay = PaySerializer()
    today = PaySerializer(allow_null=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    carried_from = MonthField(allow_null=True, help_text="The month a debt among them is from, or none (WAGE-3).")
    approval = ApprovalSerializer(allow_null=True, help_text="Who approved it, once a payslip keeps it, or none.")
    # Once a payslip keeps it (WAGE-9): the payslip, which Lipa pays; its payments, crossed out ones too, in the order
    # made; what is still to hand out, 0 once it is paid or when it pays nothing; and whether it is the person's own
    # pay, by the person, so the page offers no Lipa on it, as the server would refuse it.
    payslip = serializers.UUIDField(source="payslip_id", allow_null=True, help_text="The payslip, once approved.")
    payments = PaymentLineSerializer(many=True)
    to_hand_out = serializers.DecimalField(max_digits=14, decimal_places=2)
    own = serializers.SerializerMethodField(help_text="Whether it is the pay of the person looking, any job of theirs.")

    def get_own(self, line: Any) -> bool:
        # The jobs of the person looking, which the route reads (own_jobs); none when nobody says, as in a test.
        return bool(line.staff_id in self.context.get("own_jobs", frozenset()))


# One object, not a list, as for the pay rates' answer above.
@extend_schema_serializer(many=False)
class PayMonthAnswer(serializers.Serializer[Any]):
    # Mishahara's answer (WAGE-2): the month; the shop's today, as a phone's date can be wrong; the last day counted, or
    # null when none is over; whether no working day of it has come yet; the whole of what it pays; and a line per
    # worker paid by the day, or given money before payday in it (WAGE-8), by name.
    month = MonthField()
    today = serializers.DateField()
    counted_to = serializers.DateField(allow_null=True)
    no_day_yet = serializers.BooleanField(
        help_text="Whether no working day of this month has come yet: listed then is only who was given money in it."
    )
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    workers = WorkerPaySerializer(many=True)
    approval = ApprovalSerializer(allow_null=True, help_text="Who approved the month, or none while it is open.")
    to_approve = ToApproveSerializer(
        allow_null=True, help_text="What its approval waits for, once it is over and open; else none (WAGE-3)."
    )
    still_to_pay = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        allow_null=True,
        help_text="Once approved: the cash still to hand out, 0 once each is paid; none while open (WAGE-9).",
    )
    keeps_signatures = serializers.SerializerMethodField(
        help_text="Whether cash is sent with the worker's signature: false on the demo, which keeps none (WAGE-9)."
    )

    def get_keeps_signatures(self, _answer: Any) -> bool:
        return keeps_signatures()


class VoidedCorrectionSerializer(serializers.Serializer[Any]):
    # Who crossed out a correction, by nickname, when and why (WAGE-10). On the demo the reason is a ready one's code.
    by = serializers.CharField()
    at = serializers.DateTimeField()
    reason = serializers.CharField()


class CorrectionLineSerializer(serializers.Serializer[Any]):
    # One correction of a worker's pay, as their page lists it (WAGE-10): what it adds or takes off, a string (rule 3),
    # why, who typed it and when, and who crossed it out, or null while it counts. On the demo the reason is a ready
    # one's code, which the page says in words.
    id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Plus or minus.")
    reason = serializers.CharField()
    by = serializers.CharField()
    at = serializers.DateTimeField()
    voided = VoidedCorrectionSerializer(allow_null=True, help_text="Who crossed it out, or none while it counts.")


# Why a month takes no correction for a worker (why_no_correction, apps/staffpay/selectors.py), as its code.
NO_CORRECTION_CODES = [
    "correction.left_paid",
    "correction.month_to_come",
    "correction.outside_job",
    "correction.not_paid_by_day",
    "pay.day_approved",
]


class WorkerPayMonthAnswer(serializers.Serializer[Any]):
    # One worker's pay of a month: their line of Mishahara, with its month and its days; and, for the page to say why
    # there is nothing, whether there is a line at all, and whether their first working day is to come. The line's field
    # is named for what it first said (WAGE-2), before money given made a line too (WAGE-8): renamed, a page still open
    # in an older copy of the app would read nothing, and say that nobody is paid.
    month = MonthField()
    today = serializers.DateField()
    counted_to = serializers.DateField(allow_null=True)
    paid_by_day = serializers.BooleanField(
        help_text="Whether the month has a line of theirs: a daily rate on a working day, or money given before payday."
    )
    no_day_yet = serializers.BooleanField(
        help_text="Whether the worker's first working day of this month is still to come."
    )
    worker = WorkerPaySerializer()
    to_approve = ToApproveSerializer(
        allow_null=True,
        help_text="For one who left, with pay still open: what approving it alone waits for; else none (WAGE-3).",
    )
    void_reasons = serializers.ListField(
        child=serializers.CharField(),
        help_text="The ready reasons a payment is crossed out with, on the demo alone; empty where it is typed.",
    )
    keeps_signatures = serializers.SerializerMethodField(
        help_text="Whether cash is sent with the worker's signature: false on the demo, which keeps none (WAGE-9)."
    )
    # The month's corrections of the worker's pay, crossed out ones too, in the order typed (WAGE-10); why the month
    # takes none, as its code, or null when it takes one, so the page offers Ongeza marekebisho only when the server
    # would take it; and, on the demo alone, the ready reasons a correction is typed and crossed out with.
    corrections = CorrectionLineSerializer(many=True)
    no_correction = serializers.ChoiceField(
        choices=[(code, code) for code in NO_CORRECTION_CODES],
        allow_null=True,
        help_text="Why this month takes no correction for the worker, or none when it takes one (WAGE-10).",
    )
    correction_reasons = serializers.SerializerMethodField(
        help_text="The ready reasons a correction is typed with, on the demo alone; empty where it is typed."
    )
    correction_void_reasons = serializers.SerializerMethodField(
        help_text="The ready reasons a correction is crossed out with, on the demo alone; empty where it is typed."
    )

    def get_keeps_signatures(self, _answer: Any) -> bool:
        return keeps_signatures()

    def get_correction_reasons(self, _answer: Any) -> list[str]:
        return ready_correction_reasons()

    def get_correction_void_reasons(self, _answer: Any) -> list[str]:
        return ready_correction_void_reasons()


class RecordCorrectionSerializer(serializers.Serializer[Any]):
    # A correction as the sheet sends it (WAGE-10): its id, made on the phone (ADR-0007), required and a UUIDv7, as
    # every create's; whose, a job of the visit's shop (WorkerField: another shop's "not found", as an id no shop has);
    # the month whose pay takes it, the page's own; what it adds or takes off, a string, below 0 for Punguza malipo; and
    # why. The amount's shape is checked here (a number, at most two places); the rest is record_correction's, each in
    # its own code.
    id = serializers.UUIDField(validators=[uuid7_only])
    staff = WorkerField()
    month = MonthField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField(max_length=200, allow_blank=True)


class VoidCorrectionSerializer(serializers.Serializer[Any]):
    # A correction crossed out, as the sheet sends it: why. Empty here is void_correction's to refuse, beside the box.
    reason = serializers.CharField(max_length=200, allow_blank=True)


class CorrectionAnswer(CorrectionLineSerializer):
    # One typed or crossed out, answered as the page lists it (correction_line). The fields are
    # CorrectionLineSerializer's own, so the schema describes the answer by itself, as an advance's does
    # (AdvanceAnswer).
    def to_representation(self, instance: PayCorrection) -> Any:
        return super().to_representation(correction_line(instance))


class SeenTotalSerializer(serializers.Serializer[Any]):
    # One worker's total, as the person read it: whoever approves approves only what they read.
    staff = serializers.UUIDField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)


class ApproveMonthSerializer(serializers.Serializer[Any]):
    # What the page sends to approve a month (WAGE-3), with the id it made itself (ADR-0007): the month, and each
    # worker's total as it was read. A worker named twice is the last one said; whether they are every worker, and the
    # very totals, is approve_month's to check.
    id = serializers.UUIDField(validators=[uuid7_only])
    month = MonthField()
    seen = SeenTotalSerializer(many=True)


class PayRunAnswer(serializers.ModelSerializer[PayRun]):
    # An approval, as it was kept: the page then reads the month again. Who and when are always there, as the table
    # holds.
    month = MonthField(read_only=True)
    approved_by = serializers.CharField(source="created_by.display_name", read_only=True)
    approved_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = PayRun
        fields = ["id", "month", "approved_by", "approved_at"]
        read_only_fields = fields


class ApproveLeaverSerializer(serializers.Serializer[Any]):
    # What the page sends to approve one who left, alone (WAGE-3), with the id it made itself: whose, the month, and the
    # total as it was read.
    id = serializers.UUIDField(validators=[uuid7_only])
    staff = WorkerField()
    month = MonthField()
    seen = serializers.DecimalField(max_digits=14, decimal_places=2)


class PayslipAnswer(serializers.ModelSerializer[Payslip]):
    # A payslip approved alone, as it was kept: the page then reads the worker's pay again.
    month = MonthField(read_only=True)
    approved_by = serializers.CharField(source="created_by.display_name", read_only=True)
    approved_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Payslip
        fields = ["id", "staff", "month", "total", "approved_by", "approved_at"]
        read_only_fields = fields


class PayPayslipSerializer(serializers.Serializer[Any]):
    # What the Lipa sheet sends for a payment by M-Pesa or a bank, with the id it made itself (ADR-0007): how, and the
    # transaction number. Cash comes this way only on the demo, where no signature is kept; elsewhere it comes with its
    # drawing (pay-cash). Whether the number is there, its shape and whether it is used already are pay_payslip's to
    # check, beside its box.
    id = serializers.UUIDField(validators=[uuid7_only])
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField(max_length=_LONGEST_REFERENCE, allow_blank=True, default="")

    def validate(self, sent: dict[str, Any]) -> dict[str, Any]:
        # Cash is proven by the signature, never a number: the sheet never sends one with it.
        if sent["method"] == PaymentMethod.CASH and sent["reference"].strip():
            raise serializers.ValidationError({"reference": serializers.ErrorDetail("Cash has no number.", "invalid")})
        return sent


class PayCashQuery(serializers.Serializer[Any]):
    # What a payment in cash carries in its address, beside the payslip's id (WAGE-9): its own id and the signature's,
    # both made on the phone as Nimemlipa is tapped (ADR-0007), so a request sent again is one payment and one
    # signature. After the ?, as a path names one row at most, as the tenancy sweep calls it (PPL-9).
    id = serializers.UUIDField(validators=[uuid7_only], help_text="The payment's id, a UUIDv7 made on the phone.")
    signature = serializers.UUIDField(
        validators=[uuid7_only], help_text="The signature's id, a UUIDv7 made on the phone."
    )


class VoidPaymentSerializer(serializers.Serializer[Any]):
    # A payment crossed out, as the sheet sends it: why. Empty here is void_payslip_payment's to refuse, beside the box.
    reason = serializers.CharField(max_length=200, allow_blank=True)
