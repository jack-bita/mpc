"""apps/staffpay/api/serializers.py — how a worker's pay rates and a month of attendance look in the API (WAGE-1, ATT-5;
03 §5.10).

Thin: they describe fields and check their shape. A rate is set through set_pay_rate (apps/staffpay/services.py), which
asks who may and checks the amount and the day; the rates in force are read by the selectors (ADR-0015). The route
answers a rate (PayRateSerializer), takes a new one (PayRateCreateSerializer), and lists a worker's, with the one in
force today (PayRatesAnswer), for the worker named in the address (PayRatesQuery). Money travels as strings (rule 3).

And the month page's month (AttendanceMonthAnswer, ATT-5), worked out by attendance_month
(apps/staffpay/services.py), for the month named in the address (AttendanceMonthQuery).
"""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.core.api.ids import uuid7_only
from apps.people.models import StaffMember
from apps.staffpay.models import PayRate, ReviewReason


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


class AttendanceMonthQuery(serializers.Serializer[Any]):
    # Which month, in the address (?month=2026-11), as the page keeps it. Anything else, a day or "2026-13", is refused
    # under `month` (400 invalid), and the month page never sends one.
    month = serializers.DateField(input_formats=["%Y-%m"], help_text="The month, as 2026-11.")


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
    month = serializers.DateField(format="%Y-%m")
    today = serializers.DateField()
    workers = WorkerMonthSerializer(many=True)
    to_decide = DayToDecideSerializer(many=True)
