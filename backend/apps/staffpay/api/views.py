"""apps/staffpay/api/views.py — the staffpay routes an office screen calls, under /api/v1/staffpay/ (WAGE-1; 03 §5.10).

Four: a worker's daily pay rates, read and set on the worker's page (Malipo kwa siku, WAGE-1); a month of attendance,
read on Mahudhurio ya mwezi (ATT-5); one worker's month, their calendar and its days' taps (ATT-12); and a decision on
one of their days, sent from the sheet under the calendar (ATT-6). Thin, as every route is (ADR-0015): who may set a
rate, and what it may be, are set_pay_rate's (apps/staffpay/services.py); which rate is in force, the selectors'; what a
month holds, attendance_month's; what a worker's month holds, worker_attendance's; who may decide a day, and how,
decide_day's.
"""

from typing import Any, cast

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import CreateOnceMixin, ShopViewSet
from apps.core.permissions import Permission
from apps.people.models import StaffMember
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.api.serializers import (
    AttendanceMonthAnswer,
    AttendanceMonthQuery,
    DayDecisionSerializer,
    DecideDaySerializer,
    PayRateCreateSerializer,
    PayRatesAnswer,
    PayRateSerializer,
    PayRatesQuery,
    WorkerAttendanceAnswer,
)
from apps.staffpay.models import AttendanceDay, DayChoice, PayRate
from apps.staffpay.selectors import NEWEST_FIRST, rate_in_force
from apps.staffpay.services import attendance_month, decide_day, decision_of, set_pay_rate, worker_attendance


class PayRateViewSet(CreateOnceMixin[PayRate]):
    # GET pay-rates/?staff=… lists one worker's rates, newest first; POST pay-rates/ gives a worker a new rate from a
    # day on. No address for one row, nor any edit: a rate is never changed, only added to (rule 2).
    model = PayRate
    # A rate belongs to the whole shop, as its worker does: no side.
    side_field = None
    # A worker's pay is the owner's business: seeing it and setting it both need `settings.manage`, the key to the
    # shop's rules and rates, on the whole shop (WAGE-1). A route of the whole shop's rows may show its rows behind a
    # key of its own, as the workers' list does (PPL-4). Both need `staff.manage` on the whole shop too (initial()
    # below); setting one also asks the PIN's rule, inside the service.
    action_permissions = {
        "list": Permission.SETTINGS_MANAGE,
        "create": Permission.SETTINGS_MANAGE,
    }
    serializer_class = PayRateSerializer
    create_serializer_class = PayRateCreateSerializer
    # One answer, not pages: a worker has a few rates a year, and the page shows them all.
    pagination_class = None

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        # The base's checks first: the login, the action named, and its key above (apps/core/api/base.py). Then the
        # workers' key, staff.manage on the whole shop, for every action, a read too: whoever may see a worker's pay
        # holds the same two keys as whoever may change it (Jack, WAGE-1's review: A), so a manager handed
        # settings.manage only to change the late fine reads nobody's pay. Here, before anything is read, as the route
        # names one key per action: so a create sent again, which hands back the rate it made, is refused alike.
        super().initial(request, *args, **kwargs)
        if Permission.STAFF_MANAGE not in self.held.on(None):
            # English for the logs; the screens translate the code (ADR-0032).
            raise exceptions.PermissionDenied(f"This person may not {Permission.STAFF_MANAGE} here.")

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


class AttendanceMonthViewSet(ShopViewSet[AttendanceDay]):
    # GET attendance-month/?month=2026-11: the month page's month (ATT-5), a line per worker the shop pays by the day,
    # with the month's counts, and the days a person must decide, each with why. Only a read: a day is decided through
    # attendance-days/{id}/decide/ (AttendanceDayViewSet, below, ATT-6).
    # It works the month out through the book, which keeps the days it works out (work_out_days), so this GET writes;
    # it is safe to send again, as a month asked for twice writes nothing the second time (ATT-10).
    model = AttendanceDay
    # Attendance belongs to the whole shop, as its rules do (02 §12): no side.
    side_field = None
    # The key to fix attendance, held by the owner and the managers (03 §5.8), on the whole shop, as a route of the
    # whole shop's rows asks its key there (PPL-4): a seller, or a manager of one side alone, sees nobody's month. No
    # amount is in the answer, so the pay's two keys aren't asked (WAGE-1's review).
    action_permissions = {"list": Permission.ATTENDANCE_MANAGE}
    # One answer, not pages: a month of a shop's workers is a few dozen lines.
    pagination_class = None

    @extend_schema(parameters=[AttendanceMonthQuery], responses=AttendanceMonthAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        asked = AttendanceMonthQuery(data=request.query_params)
        # No month named, or one that is no month: 400 under `month`, through the one error handler.
        asked.is_valid(raise_exception=True)
        # The visit's own shop, open already (ShopViewSet): the book and the rates read inside it, through the guard.
        shop = Shop.objects.get(pk=self.actor.shop_id)
        return Response(AttendanceMonthAnswer(attendance_month(shop, asked.validated_data["month"])).data)


class AttendanceWorkerViewSet(ShopViewSet[StaffMember]):
    # GET attendance-worker/{id}/?month=2026-11: one worker's month (ATT-12), as their calendar shows it, opened from
    # their name on Mahudhurio ya mwezi: their days, their counts, and every tap of the month, today's too. Only a
    # read: a day is decided through attendance-days/{id}/decide/ (ATT-6), with the choices and the decision this
    # answers for each day. It works the month out through the book, as the month's route does, so this GET
    # writes too, and is safe to send again (ATT-10).
    # The worker in the address, a job of the visit's shop, found through the guard (get_object): another shop's, or
    # an id no shop has, is "not found" alike, so the answer never tells that such a worker exists (03 §5.4).
    model = StaffMember
    # A worker belongs to the whole shop, as their attendance does (02 §12): no side.
    side_field = None
    # The same key as the month's, on the whole shop (ATT-5): whoever may see the month may open its workers. The
    # photos inside are opened by their own route, which asks it again (CTRL-3). No pay in the answer, so the pay's two
    # keys aren't asked (WAGE-1's review).
    action_permissions = {"retrieve": Permission.ATTENDANCE_MANAGE}

    @extend_schema(parameters=[AttendanceMonthQuery], responses=WorkerAttendanceAnswer)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        asked = AttendanceMonthQuery(data=request.query_params)
        # No month named, or one that is no month: 400 under `month`, before the worker is looked for, as the month's
        # route refuses it.
        asked.is_valid(raise_exception=True)
        job = self.get_object()
        shop = Shop.objects.get(pk=self.actor.shop_id)
        # The person looking, so their own month offers no day to decide (Jack, ATT-6): cast, as the pay rate's route
        # does, since an office visit's actor is always a staff member.
        answer = worker_attendance(shop, job, asked.validated_data["month"], viewer=cast(StaffMember, self.actor))
        return Response(WorkerAttendanceAnswer(answer).data)


class AttendanceDayViewSet(ShopViewSet[AttendanceDay]):
    # POST attendance-days/{id}/decide/: a person decides one day of a worker's (ATT-6), from the sheet under the
    # worker's calendar: Juma's Thursday with no Toka is a full day, "Alisahau kubonyeza Toka". The day in the address,
    # a day of the visit's shop, found through the guard (get_object): another shop's, or an id no shop has, is "not
    # found" alike (03 §5.4). No list and no read of a day alone: the days are read through the worker's month.
    model = AttendanceDay
    # Attendance belongs to the whole shop, as its rules do (02 §12): no side.
    side_field = None
    # The key to fix attendance, on the whole shop, as the month's and a worker's month's routes ask it (ATT-5,
    # ATT-12). decide_day asks it again, inside its transaction, and refuses one's own day (Jack, ATT-6).
    action_permissions = {"decide": Permission.ATTENDANCE_MANAGE}

    @extend_schema(request=DecideDaySerializer, responses=DayDecisionSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The day first, through the guard: another shop's, or an id no shop has, is "not found" alike, whatever was
        # sent (03 §5.4). Before the body is read, so the tenancy sweep's empty request reaches the guard, never stops
        # at a 400 that would answer every day the same and prove nothing (ATT-6's review).
        day = self.get_object()
        sent = DecideDaySerializer(data=request.data)
        # A choice that is none of the six, a reason too long, or a time with no zone: 400, each beside its box.
        sent.is_valid(raise_exception=True)
        # An office visit's actor is always a staff member, as for the pay rate's route.
        by = cast(StaffMember, self.actor)
        data = sent.validated_data
        decided = decide_day(
            day, choice=DayChoice(data["choice"]), reason=data["reason"], replaces=data["replaces"], by=by
        )
        # The decision as the day will show it, the decider named by their nickname: the page asks the month again
        # after it, and this answer lets it show the decision at once.
        return Response(DayDecisionSerializer(decision_of(decided, {by.pk: by.display_name})).data)
