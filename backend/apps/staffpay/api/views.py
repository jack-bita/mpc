"""apps/staffpay/api/views.py — the staffpay routes an office screen calls, under /api/v1/staffpay/ (WAGE-1; 03 §5.10).

Today one: a worker's daily pay rates, read and set on the worker's page (Malipo kwa siku). Thin, as every route is
(ADR-0015): who may set a rate, and what it may be, are set_pay_rate's (apps/staffpay/services.py); which rate is in
force, the selectors'.
"""

from typing import Any, cast

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import CreateOnceMixin
from apps.core.permissions import Permission
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.api.serializers import PayRateCreateSerializer, PayRatesAnswer, PayRateSerializer, PayRatesQuery
from apps.staffpay.models import PayRate
from apps.staffpay.selectors import NEWEST_FIRST, rate_in_force
from apps.staffpay.services import set_pay_rate


class PayRateViewSet(CreateOnceMixin[PayRate]):
    # GET pay-rates/?staff=… lists one worker's rates, newest first; POST pay-rates/ gives a worker a new rate from a
    # day on. No address for one row, nor any edit: a rate is never changed, only added to (rule 2).
    model = PayRate
    # A rate belongs to the whole shop, as its worker does: no side.
    side_field = None
    # A worker's pay is the owner's business: seeing it and setting it both need `settings.manage`, the key to the
    # shop's rules and rates, on the whole shop (WAGE-1). A route of the whole shop's rows may show its rows behind a
    # key of its own, as the workers' list does (PPL-4). Setting one also asks the PIN's rule, staff.manage among it,
    # inside the service.
    action_permissions = {
        "list": Permission.SETTINGS_MANAGE,
        "create": Permission.SETTINGS_MANAGE,
    }
    serializer_class = PayRateSerializer
    create_serializer_class = PayRateCreateSerializer
    # One answer, not pages: a worker has a few rates a year, and the page shows them all.
    pagination_class = None

    def base_rows(self) -> QuerySet[PayRate]:
        # Each rate names who set it (`set_by`): their job comes in the same read, not one read per rate.
        return super().base_rows().select_related("created_by")

    @extend_schema(parameters=[PayRatesQuery], responses=PayRatesAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        asked = PayRatesQuery(data=request.query_params)
        # No worker named, or one that is no id: 400 under `staff`, through the one error handler.
        asked.is_valid(raise_exception=True)
        # The worker's rates, through get_queryset(), inside the visit's shop: another shop's worker, or an id no shop
        # has, has none here, so the answer tells nothing of them (03 §5.4).
        rates = list(self.get_queryset().filter(staff_id=asked.validated_data["staff"]).order_by(*NEWEST_FIRST))
        today = shop_today(Shop.objects.get(pk=self.actor.shop_id))
        in_force = rate_in_force(rates, today)
        answer = {"today": today, "in_force": None if in_force is None else in_force.pk, "rates": rates}
        return Response(PayRatesAnswer(answer).data)

    def create_row(self, data: dict[str, Any]) -> PayRate:
        # The worker is one of the visit's shop (WorkerField); set_pay_rate checks the rest, and refuses with its codes.
        # cast: the login leaves the staff member acting in `request.auth`, which mypy reads as an Actor.
        return set_pay_rate(
            data["staff"],
            rate_id=data["id"],
            daily_rate=data["daily_rate"],
            effective_from=data["effective_from"],
            shares_meals=data["shares_meals"],
            note=data.get("note", ""),
            by=cast(StaffMember, self.actor),
        )
