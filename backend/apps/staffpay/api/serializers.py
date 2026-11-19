"""apps/staffpay/api/serializers.py — how a worker's pay rates look in the API (WAGE-1; 03 §5.10).

Thin: they describe fields and check their shape. A rate is set through set_pay_rate (apps/staffpay/services.py), which
asks who may and checks the amount and the day; the rates in force are read by the selectors (ADR-0015). The route
answers a rate (PayRateSerializer), takes a new one (PayRateCreateSerializer), and lists a worker's, with the one in
force today (PayRatesAnswer), for the worker named in the address (PayRatesQuery). Money travels as strings (rule 3).
"""

from typing import Any

from django.db.models import QuerySet
from rest_framework import serializers

from apps.core.api.ids import uuid7_only
from apps.people.models import StaffMember
from apps.staffpay.models import PayRate


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


class PayRatesAnswer(serializers.Serializer[Any]):
    # A worker's rates, newest first, as the page's history shows them; the shop's today, from which the form's date
    # starts; and the one in force today, which the page shows first ("Sasa"), or none: worked out here, on the shop's
    # own date, as a phone's date can be wrong.
    today = serializers.DateField()
    in_force = serializers.UUIDField(allow_null=True, help_text="The rate in force on the shop's today, or none.")
    rates = PayRateSerializer(many=True)
