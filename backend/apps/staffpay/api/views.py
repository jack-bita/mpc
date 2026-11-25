"""apps/staffpay/api/views.py — the staffpay routes an office screen calls, under /api/v1/staffpay/ (WAGE-1; 03 §5.10).

Seven: a worker's daily pay rates, read and set on the worker's page (Malipo kwa siku, WAGE-1); a month of attendance,
read on Mahudhurio ya mwezi (ATT-5); one worker's month, their calendar and its days' taps (ATT-12); a decision on one
of their days, sent from the sheet under the calendar (ATT-6); a manager's fixes to the taps, a tap added and a tap
crossed out, each sent from its sheet under the calendar (ATT-13); the day's meal money, read, typed and crossed out
on Hela ya chakula (WAGE-7); and the month's pay, everyone's on Mishahara and one worker's on their page, read alone
(WAGE-2). Thin, as every route is (ADR-0015): who may set a rate, and what it may be, are
set_pay_rate's (apps/staffpay/services.py); which rate is in force, the selectors'; what a month holds,
attendance_month's; what a worker's month holds, worker_attendance's; who may decide a day, and how, decide_day's; who
may fix a tap, and how, add_tap's and void_tap's; the meal money of any days, meal_money_days'; who may type it, and
cross it out, and how, record_meal_money's and void_meal_money's; what the month pays, pay_month's and worker_pay's.
"""

from datetime import date
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
    AddTapSerializer,
    AttendanceMonthAnswer,
    AttendanceMonthQuery,
    DayDecisionSerializer,
    DecideDaySerializer,
    MealMoneyAnswer,
    MealMoneyDaysAnswer,
    MealMoneyQuery,
    PayMonthAnswer,
    PayRateCreateSerializer,
    PayRatesAnswer,
    PayRateSerializer,
    PayRatesQuery,
    RecordMealMoneySerializer,
    TapAnswer,
    VoidMealMoneySerializer,
    VoidTapSerializer,
    WorkerAttendanceAnswer,
    WorkerPayMonthAnswer,
)
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind, DayChoice, MealMoney, PayRate
from apps.staffpay.selectors import NEWEST_FIRST, rate_in_force
from apps.staffpay.services import (
    add_tap,
    attendance_month,
    decide_day,
    decision_of,
    meal_money_days,
    pay_month,
    record_meal_money,
    set_pay_rate,
    void_meal_money,
    void_tap,
    worker_attendance,
    worker_pay,
)


def _ask_the_workers_key_too(view: ShopViewSet[Any]) -> None:
    """The second of the two keys of pay: staff.manage on the whole shop, beside the settings.manage the route names.
    Whoever may see a worker's pay holds the same two keys as whoever may change it (Jack, WAGE-1's review: A), so a
    manager handed settings.manage only to change the late fine reads nobody's pay. Asked in `initial`, before anything
    is read, as the route names one key per action."""
    if Permission.STAFF_MANAGE not in view.held.on(None):
        # English for the logs; the screens translate the code (ADR-0032).
        raise exceptions.PermissionDenied(f"This person may not {Permission.STAFF_MANAGE} here.")


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
        # workers' key, for every action, a read too: so a create sent again, which hands back the rate it made, is
        # refused alike.
        super().initial(request, *args, **kwargs)
        _ask_the_workers_key_too(self)

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


class AttendanceTapViewSet(CreateOnceMixin[AttendanceEvent]):
    # POST attendance-taps/: a manager adds a tap a worker forgot (ATT-13), from the sheet under the worker's calendar:
    # Juma's Toka of 18:45, "Alisahau kubonyeza Toka". POST attendance-taps/{id}/void/: a manager crosses out a tap
    # made by mistake, Juma's Toka of 10:00, "Alibonyeza kwa makosa"; the tap in the address, one of the visit's shop,
    # found through the guard (get_object): another shop's, or an id no shop has, is "not found" alike (03 §5.4). No
    # list and no read of a tap alone: the taps are read through the worker's month (ATT-12). Each answers the tap as
    # the day shows it (TapAnswer).
    model = AttendanceEvent
    # Attendance belongs to the whole shop, as its rules do (02 §12): no side.
    side_field = None
    # The key to fix attendance, on the whole shop, as the month's routes ask it (ATT-5, ATT-12, ATT-6). The services
    # ask it again, inside their transactions, and refuse one's own taps (as ATT-6's own day).
    action_permissions = {
        "create": Permission.ATTENDANCE_MANAGE,
        "void": Permission.ATTENDANCE_MANAGE,
    }
    serializer_class = TapAnswer
    create_serializer_class = AddTapSerializer

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        # The base's checks first: the login, the action named, and its key above (apps/core/api/base.py). Then the same
        # key again, for every action, before anything is read: a create sent again hands back the tap it made before
        # (CreateOnceMixin), and asks no key for that, so a seller sending the id of a tap their laptop made, as a new
        # tap's, would be handed it, its time and its photo's id. Refused here instead, as the pay rates' route does
        # (WAGE-1's review). This is the check that refuses her: the route keeps CreateOnceMixin's own `create`, which
        # asks the create's key only after it looks for a tap sent before, so the base leaves that key to it
        # (ShopViewSet.initial). A `create` written here, even to describe it, would make the base ask instead, and
        # leave this line unreached (ATT-13's review): the answer describes itself (TapAnswer).
        super().initial(request, *args, **kwargs)
        if Permission.ATTENDANCE_MANAGE not in self.held.on(None):
            # English for the logs; the screens translate the code (ADR-0032).
            raise exceptions.PermissionDenied(f"This person may not {Permission.ATTENDANCE_MANAGE} here.")

    def create_row(self, data: dict[str, Any]) -> AttendanceEvent:
        # The worker is one of the visit's shop (WorkerField); add_tap checks the rest, and refuses with its codes.
        # cast: the login leaves the staff member acting in `request.auth`, which mypy reads as an Actor.
        return add_tap(
            data["staff"],
            tap_id=data["id"],
            kind=ClockKind(data["kind"]),
            date=data["date"],
            minute=data["time"],
            reason=data["reason"],
            by=cast(StaffMember, self.actor),
        )

    @extend_schema(request=VoidTapSerializer, responses=TapAnswer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The tap first, through the guard: another shop's, or an id no shop has, is "not found" alike, whatever was
        # sent (03 §5.4). Before the body is read, so the tenancy sweep's empty request reaches the guard, never stops
        # at a 400 that would answer every tap the same and prove nothing (as ATT-6's review asked of deciding a day).
        tap = self.get_object()
        sent = VoidTapSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        voided = void_tap(tap, reason=sent.validated_data["reason"], by=cast(StaffMember, self.actor))
        return Response(TapAnswer(voided).data)


class MealMoneyViewSet(CreateOnceMixin[MealMoney]):
    # GET meal-money/?first=…&last=…: the days of a span on Hela ya chakula (WAGE-7), each with its money, how it is
    # split and its rows, and the whole of it. POST meal-money/: whoever the owner gave the key to types what the shop
    # spent on one day's meals. POST meal-money/{id}/void/: a wrong row crossed out; the row in the address, one of the
    # visit's shop, found through the guard (get_object): another shop's, or an id no shop has, is "not found" alike
    # (03 §5.4). No read of a row alone: the rows come with their day.
    # It works the days out through the book, as the month's route does, so this GET writes too, and is safe to send
    # again (ATT-10).
    model = MealMoney
    # The whole shop's, not a side's: the workers of both sides eat together (02 §12).
    side_field = None
    # The one key for all three, on the whole shop: the owner's own, which he gives to whoever he chooses (Jack, 15 Nov
    # 2026), so a manager without it sees none of it. The list names it too, so a create sent again, which hands back
    # the row it made, asks it as any read of a row does (CreateOnceMixin). The services ask it again, inside their
    # transactions.
    action_permissions = {
        "list": Permission.MEALS_RECORD,
        "create": Permission.MEALS_RECORD,
        "void": Permission.MEALS_RECORD,
    }
    serializer_class = MealMoneyAnswer
    create_serializer_class = RecordMealMoneySerializer
    # One answer, not pages: a span is at most a year of days, and the page adds nothing up.
    pagination_class = None

    @extend_schema(parameters=[MealMoneyQuery], responses=MealMoneyDaysAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        asked = MealMoneyQuery(data=request.query_params)
        # A day missing, or one that is none, Hadi before Kuanzia, or more than a year: 400, each under its own name.
        asked.is_valid(raise_exception=True)
        span = asked.validated_data
        return Response(MealMoneyDaysAnswer(meal_money_days(self._shop(), span["first"], span["last"])).data)

    def create_row(self, data: dict[str, Any]) -> MealMoney:
        # record_meal_money checks the day and the amount, and refuses with its codes. cast: the login leaves the staff
        # member acting in `request.auth`, which mypy reads as an Actor.
        return record_meal_money(
            self._shop(),
            money_id=data["id"],
            date=data["date"],
            amount=data["amount"],
            note=data["note"],
            by=cast(StaffMember, self.actor),
        )

    @extend_schema(request=VoidMealMoneySerializer, responses=MealMoneyAnswer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The row first, through the guard, whatever was sent: before the body is read, so the tenancy sweep's empty
        # request reaches the guard, never stops at a 400 (as a tap's void, ATT-13).
        row = self.get_object()
        sent = VoidMealMoneySerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        voided = void_meal_money(row, reason=sent.validated_data["reason"], by=cast(StaffMember, self.actor))
        return Response(MealMoneyAnswer(voided).data)

    def _shop(self) -> Shop:
        # The visit's own shop, open already (ShopViewSet): everything below reads inside it, through the guard.
        return Shop.objects.get(pk=self.actor.shop_id)


class PayViewSet(ShopViewSet[StaffMember]):
    # GET pay/?month=2026-11: the month's pay of everyone the shop pays by the day, on Mishahara (WAGE-2), each worker's
    # line by line, with the whole of it. GET pay/{id}/?month=2026-11: one worker's, on their own pay page and in the
    # card of their own page. Only reads: the draft is worked out each time and never saved (Jack); approving it is
    # WAGE-3's. Both work the days out through the book, as the month's route does, so these GETs write too, and are
    # safe to send again (ATT-10).
    # The worker in the address, a job of the visit's shop, found through the guard (get_object): another shop's, or an
    # id no shop has, is "not found" alike (03 §5.4).
    model = StaffMember
    # A worker belongs to the whole shop, as their pay does: no side.
    side_field = None
    # The two keys of pay, on the whole shop, as the rates' route asks them (WAGE-1): "14 × 10,000" shows the rate. So a
    # manager without both sees nobody's pay here either; `pay.run`, which every Manager holds, opens nothing until
    # WAGE-3 decides what preparing the pay may show.
    action_permissions = {"list": Permission.SETTINGS_MANAGE, "retrieve": Permission.SETTINGS_MANAGE}
    # One answer, not pages: a shop's workers are a few dozen lines, and the page adds nothing up.
    pagination_class = None

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        _ask_the_workers_key_too(self)

    @extend_schema(parameters=[AttendanceMonthQuery], responses=PayMonthAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(PayMonthAnswer(pay_month(self._shop(), self._month(request))).data)

    @extend_schema(parameters=[AttendanceMonthQuery], responses=WorkerPayMonthAnswer)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The month first, as a worker's attendance reads it: no month is refused before the worker is looked for.
        month = self._month(request)
        return Response(WorkerPayMonthAnswer(worker_pay(self._shop(), self.get_object(), month)).data)

    def _month(self, request: Request) -> date:
        # The month in the address, as its first day. None, or one that is no month: 400 under `month`, through the one
        # error handler.
        asked = AttendanceMonthQuery(data=request.query_params)
        asked.is_valid(raise_exception=True)
        return cast(date, asked.validated_data["month"])

    def _shop(self) -> Shop:
        # The visit's own shop, open already (ShopViewSet): everything below reads inside it, through the guard.
        return Shop.objects.get(pk=self.actor.shop_id)
