"""apps/staffpay/api/views.py — the staffpay routes an office screen calls, under /api/v1/staffpay/ (WAGE-1; 03 §5.10).

Thirteen: a worker's daily pay rates, read and set on the worker's page (Malipo kwa siku, WAGE-1); a month of
attendance, read on Mahudhurio ya mwezi (ATT-5); one worker's month, their calendar and its days' taps (ATT-12); a
decision on one of their days, sent from the sheet under the calendar (ATT-6); a manager's fixes to the taps, a tap
added and a tap crossed out, each sent from its sheet under the calendar (ATT-13); the day's meal money, read, typed and
crossed out on Hela ya chakula (WAGE-7); money given before payday, read, typed and crossed out on Advansi (WAGE-8); and
the month's pay, everyone's on Mishahara and one worker's on their page, read alone (WAGE-2); its approval, a month's
and one worker's alone (WAGE-3); handing it out, and crossing out a payment marked by mistake (WAGE-9); and a correction
of a later month, typed and crossed out on a worker's pay page (WAGE-10); and a worker's own days and pay, read by
themselves on Siku na malipo yangu (WAGE-4). Thin, as every route is (ADR-0015): who may set a rate, and what it may be,
are set_pay_rate's (apps/staffpay/services/money.py); which rate is in force, the selectors'; what a month holds,
attendance_month's; what a worker's month holds, worker_attendance's; who may decide a day, and how, decide_day's; who
may fix a tap, and how, add_tap's and void_tap's; the meal money of any days, meal_money_days'; who may type it, and
cross it out, and how, record_meal_money's and void_meal_money's; the advances of a month, advances_month's; who may
type one, and cross it out, and how, record_advance's and void_advance's; what the month pays, pay_month's and
worker_pay's; who may approve it, and when, approve_month's and approve_leaver's; and who may correct it, and how,
record_correction's and void_correction's; and what a worker reads of their own, own_attendance's and own_pay's.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.control.api.uploads import PHOTO_BODY, photo_sent
from apps.control.models import Attachment
from apps.core.api.base import SEES_THE_SIDE, CreateOnceMixin, ShopViewSet
from apps.core.api.ids import id_taken
from apps.core.permissions import Permission
from apps.people.models import StaffMember, StaffStatus
from apps.shops.models import Shop
from apps.shops.selectors import shop_today
from apps.staffpay.api.serializers import (
    AddTapSerializer,
    AdvanceAnswer,
    AdvancePageAnswer,
    AdvancesMonthAnswer,
    ApproveLeaverSerializer,
    ApproveMonthSerializer,
    AttendanceMonthAnswer,
    AttendanceMonthQuery,
    CorrectionAnswer,
    DayDecisionSerializer,
    DecideDaySerializer,
    MealMoneyAnswer,
    MealMoneyDaysAnswer,
    MealMoneyQuery,
    OwnAttendanceAnswer,
    OwnPayAnswer,
    PayCashQuery,
    PaymentLineSerializer,
    PayMonthAnswer,
    PayPayslipSerializer,
    PayRateCreateSerializer,
    PayRatesAnswer,
    PayRateSerializer,
    PayRatesQuery,
    PayRunAnswer,
    PayslipAnswer,
    RecordAdvanceSerializer,
    RecordCorrectionSerializer,
    RecordMealMoneySerializer,
    TapAnswer,
    VoidAdvanceSerializer,
    VoidCorrectionSerializer,
    VoidMealMoneySerializer,
    VoidPaymentSerializer,
    VoidTapSerializer,
    WorkerAttendanceAnswer,
    WorkerPayMonthAnswer,
)
from apps.staffpay.models import (
    Advance,
    AttendanceDay,
    AttendanceEvent,
    ClockKind,
    DayChoice,
    MealMoney,
    PayCorrection,
    PaymentMethod,
    PayRate,
    PayRun,
    Payslip,
    PayslipPayment,
)
from apps.staffpay.selectors import NEWEST_FIRST, is_closed, rate_in_force
from apps.staffpay.services import (
    APPROVES,
    PAYS,
    add_tap,
    advance_line,
    advances_month,
    approve_leaver,
    approve_month,
    attendance_month,
    decide_day,
    decision_of,
    meal_money_days,
    own_attendance,
    own_pay,
    pay_month,
    pay_payslip,
    payment_line,
    ready_advance_void_reasons,
    record_advance,
    record_correction,
    record_meal_money,
    set_pay_rate,
    void_advance,
    void_correction,
    void_meal_money,
    void_payslip_payment,
    void_tap,
    worker_attendance,
    worker_pay,
)


def _ask_the_workers_key_too(view: ShopViewSet[Any]) -> None:
    """The second of the two keys of pay: staff.manage on the whole shop, beside the settings.manage the route names.
    Whoever may see a worker's pay holds the same two keys as whoever may change it (Jack, WAGE-1's review: A), so a
    manager handed settings.manage only to change the late fine reads nobody's pay. Asked in `initial`, before anything
    is read, as the route names one key per action."""
    _ask(view, Permission.STAFF_MANAGE)


def _ask(view: ShopViewSet[Any], *keys: Permission) -> None:
    # Refuse a visit whose person lacks one of the keys on the whole shop.
    for key in keys:
        if key not in view.held.on(None):
            # English for the logs; the screens translate the code (ADR-0032).
            raise exceptions.PermissionDenied(f"This person may not {key} here.")


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
        shop = Shop.objects.get(pk=self.actor.shop_id)
        today = shop_today(shop)
        in_force = rate_in_force(rates, today)
        # The job itself, through the guard too, only if it ended: one that still runs has days to come.
        gone = StaffMember.objects.filter(
            shop=shop, pk=asked.validated_data["staff"], status=StaffStatus.LEFT, left_on__isnull=False
        ).first()
        answer = {
            "today": today,
            "in_force": None if in_force is None else in_force.pk,
            "closed": gone is not None and is_closed(shop, cast(date, gone.left_on), gone.pk),
            "rates": rates,
        }
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


class AdvanceViewSet(CreateOnceMixin[Advance]):
    # GET advances/?month=2026-11: the money given to workers before payday in a month, on Advansi (WAGE-8), and whom
    # one may be typed for. GET advances/{id}/: one, on its own page. POST advances/: whoever holds the key types one.
    # POST advances/{id}/void/: a wrong one crossed out. The row in an address is one of the visit's shop, found through
    # the guard (get_object): another shop's, or an id no shop has, is "not found" alike (03 §5.4).
    model = Advance
    # A worker belongs to the whole shop, as their pay does: no side.
    side_field = None
    # The one key for all four, on the whole shop: the owner's and the managers' (Jack: A). A read too, as what a worker
    # took is nobody's to see by only working there; and the list and the one name it, so a create sent again, which
    # hands back the row it made, asks it as any read does (CreateOnceMixin). Not the two keys of pay: no answer here
    # holds a rate or a day's pay. The services ask it again, inside their transactions, and refuse one's own.
    action_permissions = {
        "list": Permission.MONEY_ADVANCE,
        "retrieve": Permission.MONEY_ADVANCE,
        "create": Permission.MONEY_ADVANCE,
        "void": Permission.MONEY_ADVANCE,
    }
    serializer_class = AdvanceAnswer
    create_serializer_class = RecordAdvanceSerializer
    # One answer, not pages: a shop gives a few dozen a month, and the page adds nothing up.
    pagination_class = None

    def base_rows(self) -> QuerySet[Advance]:
        # Each names whose it is, who typed it and who crossed it out: their jobs come in the same read.
        return super().base_rows().select_related("staff", "created_by", "voided_by")

    @extend_schema(parameters=[AttendanceMonthQuery], responses=AdvancesMonthAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        asked = AttendanceMonthQuery(data=request.query_params)
        # No month named, or one that is no month: 400 under `month`, through the one error handler.
        asked.is_valid(raise_exception=True)
        # The visit's own shop, open already (ShopViewSet): everything below reads inside it, through the guard.
        shop = Shop.objects.get(pk=self.actor.shop_id)
        month = advances_month(shop, asked.validated_data["month"], viewer=cast(StaffMember, self.actor))
        return Response(AdvancesMonthAnswer(month).data)

    @extend_schema(responses=AdvancePageAnswer)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        row = self.get_object()
        # By the person, not the job, as void_advance asks: someone hired again crosses out none of their old job's.
        own = row.staff.user_id == cast(StaffMember, self.actor).user_id
        answer = {
            "advance": advance_line(row),
            "own": own,
            # Its pay approved, the month's or the worker's alone (WAGE-3): the page offers no Batilisha.
            "closed": is_closed(Shop.objects.get(pk=row.shop_id), row.date, row.staff_id),
            "ready_void_reasons": ready_advance_void_reasons(),
        }
        return Response(AdvancePageAnswer(answer).data)

    def create_row(self, data: dict[str, Any]) -> Advance:
        # The worker is one of the visit's shop (WorkerField); record_advance checks the rest, and refuses with its
        # codes. cast: the login leaves the staff member acting in `request.auth`, which mypy reads as an Actor.
        return record_advance(
            data["staff"],
            advance_id=data["id"],
            date=data["date"],
            amount=data["amount"],
            note=data["note"],
            by=cast(StaffMember, self.actor),
        )

    @extend_schema(request=VoidAdvanceSerializer, responses=AdvanceAnswer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The row first, through the guard, whatever was sent. The base found it already, before this ran (initial()),
        # so an empty request for another shop's row is "not found" whatever comes next (03 §5.4); in this order here
        # too, so the two never say otherwise.
        row = self.get_object()
        sent = VoidAdvanceSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        voided = void_advance(row, reason=sent.validated_data["reason"], by=cast(StaffMember, self.actor))
        return Response(AdvanceAnswer(voided).data)


class PayViewSet(ShopViewSet[StaffMember]):
    # GET pay/?month=2026-11: the month's pay of everyone the shop pays by the day, on Mishahara (WAGE-2), each worker's
    # line by line, with the whole of it. GET pay/{id}/?month=2026-11: one worker's, on their own pay page and in the
    # card of their own page. Only reads: the draft is worked out each time and never saved (Jack); approving it is
    # pay-runs/ and payslips/, below, and an approved month is read from its payslips (WAGE-3). Both work an open month
    # out through the book, as the month's route does, so these GETs write too, and are safe to send again (ATT-10).
    # The worker in the address, a job of the visit's shop, found through the guard (get_object): another shop's, or an
    # id no shop has, is "not found" alike (03 §5.4).
    model = StaffMember
    # A worker belongs to the whole shop, as their pay does: no side.
    side_field = None
    # The two keys of pay, on the whole shop, as the rates' route asks them (WAGE-1): "14 × 10,000" shows the rate. So a
    # manager without both sees nobody's pay here either; `pay.run`, which every Manager holds, opens nothing: reading
    # the pay is approving's, and handing it out is WAGE-9's to decide.
    action_permissions = {"list": Permission.SETTINGS_MANAGE, "retrieve": Permission.SETTINGS_MANAGE}
    # One answer, not pages: a shop's workers are a few dozen lines, and the page adds nothing up.
    pagination_class = None

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        _ask_the_workers_key_too(self)

    @extend_schema(parameters=[AttendanceMonthQuery], responses=PayMonthAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        answer = pay_month(self._shop(), self._month(request))
        return Response(PayMonthAnswer(answer, context=self._own()).data)

    @extend_schema(parameters=[AttendanceMonthQuery], responses=WorkerPayMonthAnswer)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The month first, as a worker's attendance reads it: no month is refused before the worker is looked for.
        month = self._month(request)
        answer = worker_pay(self._shop(), self.get_object(), month)
        return Response(WorkerPayMonthAnswer(answer, context=self._own()).data)

    def _own(self) -> dict[str, frozenset[Any]]:
        # Every job of the person looking, at this shop: a line of theirs says `own`, so the page offers no Lipa on it,
        # as pay_payslip refuses one's own by the person (WAGE-9). Their own jobs only, read through the guard.
        person = cast(StaffMember, self.actor).user_id
        return {"own_jobs": frozenset(StaffMember.objects.filter(user_id=person).values_list("pk", flat=True))}

    def _month(self, request: Request) -> date:
        # The month in the address, as its first day. None, or one that is no month: 400 under `month`, through the one
        # error handler.
        asked = AttendanceMonthQuery(data=request.query_params)
        asked.is_valid(raise_exception=True)
        return cast(date, asked.validated_data["month"])

    def _shop(self) -> Shop:
        # The visit's own shop, open already (ShopViewSet): everything below reads inside it, through the guard.
        return Shop.objects.get(pk=self.actor.shop_id)


class _ApprovalViewSet[M: PayRun | Payslip](CreateOnceMixin[M]):
    # What the two approvals share (WAGE-3): who may. Not a route itself.
    # A worker's pay belongs to the whole shop: no side.
    side_field = None
    # The owner's own key to the approval, on the whole shop.
    action_permissions = {"create": Permission.PAY_APPROVE}

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        # The base's checks first: the login, the action named, and its key above (apps/core/api/base.py). Then every
        # key an approval asks, before anything is read: the two of pay, as nobody approves what they may not read; and
        # the approval's own again, as a create sent again hands back the row it made and asks no key for that
        # (CreateOnceMixin), and who approved a month, and one worker's total, are the pay's own (as a tap's, ATT-13).
        # The services ask all three again, inside their transactions.
        super().initial(request, *args, **kwargs)
        _ask(self, *self.keys_asked())

    def keys_asked(self) -> tuple[Permission, ...]:
        # What this visit's action asks, every key on the whole shop: an approval's, unless a route says otherwise.
        return APPROVES

    def base_rows(self) -> QuerySet[M]:
        # Each names who approved it: their job comes in the same read.
        return super().base_rows().select_related("created_by")


class PayRunViewSet(_ApprovalViewSet[PayRun]):
    # POST pay-runs/: a month's pay approved, once, for everyone (WAGE-3), from the sheet on Mishahara. No list and no
    # read of one alone: an approved month is read through pay/, and nothing ever changes or undoes one (A3).
    model = PayRun
    serializer_class = PayRunAnswer
    create_serializer_class = ApproveMonthSerializer

    def create_row(self, data: dict[str, Any]) -> PayRun:
        # approve_month checks the month, its days and the totals, and refuses with its codes. The visit's own shop,
        # open already (ShopViewSet). cast: the login leaves the staff member acting in `request.auth`.
        return approve_month(
            Shop.objects.get(pk=self.actor.shop_id),
            data["month"],
            run_id=data["id"],
            seen={each["staff"]: each["total"] for each in data["seen"]},
            by=cast(StaffMember, self.actor),
        )


class PayslipViewSet(_ApprovalViewSet[Payslip]):
    # POST payslips/: the pay of one worker who left, approved alone (WAGE-3), from the sheet on their pay page. No list
    # and no read of one alone: a payslip is read through pay/{id}/. And Lipa (WAGE-9), a payslip handed out:
    # POST payslips/{id}/pay/ by M-Pesa or a bank, with its number; PUT payslips/{id}/pay-cash/?id=…&signature=…, in
    # cash, the body the worker's signature as the phone drew it. The payslip in the address, found through the guard
    # (get_object) before anything sent is read: another shop's, or an id no shop has, is "not found" alike (03 §5.4).
    model = Payslip
    serializer_class = PayslipAnswer
    create_serializer_class = ApproveLeaverSerializer
    # Lipa asks `pay.run`, every manager's, not the approval's key: handing out is a job of its own (WAGE-9).
    action_permissions = {
        "create": Permission.PAY_APPROVE,
        "pay": Permission.PAY_RUN,
        "pay_cash": Permission.PAY_RUN,
    }

    def keys_asked(self) -> tuple[Permission, ...]:
        # Handing out asks `pay.run` with the two keys of pay, as nobody hands out what they may not read (PAYS);
        # approving, the approval's three. pay_payslip asks its three again, under its locks.
        return PAYS if self.action in ("pay", "pay_cash") else APPROVES

    def create_row(self, data: dict[str, Any]) -> Payslip:
        # The worker is one of the visit's shop (WorkerField); approve_leaver checks the rest, and refuses with its
        # codes.
        return approve_leaver(
            data["staff"],
            data["month"],
            payslip_id=data["id"],
            seen=data["seen"],
            by=cast(StaffMember, self.actor),
        )

    @extend_schema(request=PayPayslipSerializer, responses=PaymentLineSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The payslip first, so another shop's is "not found" before anything sent is read.
        slip = self.get_object()
        sent = PayPayslipSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        with _refusing_a_taken_id(PayslipPayment):
            made = pay_payslip(
                slip,
                payment_id=sent.validated_data["id"],
                method=PaymentMethod(sent.validated_data["method"]),
                reference=sent.validated_data["reference"],
                by=cast(StaffMember, self.actor),
            )
        return Response(PaymentLineSerializer(payment_line(made)).data)

    # PUT, as a payment sent twice is one payment: both ids in the address, after the ?, as a worker's photo's are
    # (PPL-9). The body is the drawing itself, as the phone made it, with no form around it: read only once its length
    # says it is small enough (photo_sent).
    @extend_schema(parameters=[PayCashQuery], request=PHOTO_BODY, responses=PaymentLineSerializer)
    @action(detail=True, methods=["put"], url_path="pay-cash")
    def pay_cash(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The payslip first, then the ids, the body last, its length before a byte of it.
        slip = self.get_object()
        asked = PayCashQuery(data=request.query_params)
        asked.is_valid(raise_exception=True)
        drawing = photo_sent(request)
        with _refusing_a_taken_id(PayslipPayment), _refusing_a_taken_id(Attachment):
            made = pay_payslip(
                slip,
                payment_id=asked.validated_data["id"],
                method=PaymentMethod.CASH,
                signature_id=asked.validated_data["signature"],
                signature=drawing,
                by=cast(StaffMember, self.actor),
            )
        return Response(PaymentLineSerializer(payment_line(made)).data)


class PayslipPaymentViewSet(ShopViewSet[PayslipPayment]):
    # POST payslip-payments/{id}/void/: Batilisha, a payment marked by mistake crossed out (WAGE-9), from the sheet at
    # the foot of the payslip. Nothing else: a payment is made through its payslip, above, and read with it, through
    # pay/. The row through the guard first: another shop's, or an id no shop has, is "not found" alike (03 §5.4).
    model = PayslipPayment
    # A worker's pay belongs to the whole shop: no side.
    side_field = None
    action_permissions = {"void": Permission.PAY_RUN}

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        # The base's checks, then the keys of handing out, all three, before anything is read: who crossed out a
        # payment, and of what amount, are the pay's own. void_payslip_payment asks them again, under its locks.
        super().initial(request, *args, **kwargs)
        _ask(self, *PAYS)

    @extend_schema(request=VoidPaymentSerializer, responses=PaymentLineSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        row = self.get_object()
        sent = VoidPaymentSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        voided = void_payslip_payment(row, reason=sent.validated_data["reason"], by=cast(StaffMember, self.actor))
        return Response(PaymentLineSerializer(payment_line(voided)).data)


class PayCorrectionViewSet(CreateOnceMixin[PayCorrection]):
    # POST pay-corrections/: Marekebisho, a mistake found after an earlier month's approval put right in a month still
    # open (WAGE-10), from the sheet on a worker's pay page. POST pay-corrections/{id}/void/: a wrong one crossed out,
    # from the sheet its line opens. Nothing else: corrections are read with the worker's pay, through pay/{id}/. The
    # row in an address through the guard first (get_object): another shop's, or an id no shop has, is "not found"
    # alike (03 §5.4).
    model = PayCorrection
    # A worker's pay belongs to the whole shop: no side.
    side_field = None
    # The approval's own key, as only whoever approves pay types or crosses out one (Jack: A).
    action_permissions = {"create": Permission.PAY_APPROVE, "void": Permission.PAY_APPROVE}
    serializer_class = CorrectionAnswer
    create_serializer_class = RecordCorrectionSerializer

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        # The base's checks, then all three of the approval's keys, before anything is read: the two of pay, as a
        # correction and its reason are the pay's own; and the approval's again, as a create sent again hands back the
        # row it made and asks no key for that (CreateOnceMixin). The services ask them again, under their locks.
        super().initial(request, *args, **kwargs)
        _ask(self, *APPROVES)

    def base_rows(self) -> QuerySet[PayCorrection]:
        # Each names who typed it and who crossed it out: their jobs come in the same read.
        return super().base_rows().select_related("created_by", "voided_by")

    def create_row(self, data: dict[str, Any]) -> PayCorrection:
        # The worker is one of the visit's shop (WorkerField); record_correction checks the rest, and refuses with its
        # codes. cast: the login leaves the staff member acting in `request.auth`, which mypy reads as an Actor.
        return record_correction(
            data["staff"],
            correction_id=data["id"],
            month=data["month"],
            amount=data["amount"],
            reason=data["reason"],
            by=cast(StaffMember, self.actor),
        )

    @extend_schema(request=VoidCorrectionSerializer, responses=CorrectionAnswer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        row = self.get_object()
        sent = VoidCorrectionSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        voided = void_correction(row, reason=sent.validated_data["reason"], by=cast(StaffMember, self.actor))
        return Response(CorrectionAnswer(voided).data)


# Never kept by a cache, the browser's or a proxy's on the way (Cache-Control: no-store, private), as the sync's answers
# aren't: a shop's laptop is shared, and a worker's pay must never stay on it for the next person to find (03 §6.1).
@method_decorator(never_cache, name="dispatch")
class MineViewSet(ShopViewSet[StaffMember]):
    # GET mine/attendance/?month=2026-11 and GET mine/pay/?month=2026-11: the worker's own month and pay (WAGE-4, A4),
    # on Siku na malipo yangu, after any login, a PIN's on the shop's laptop or a password's on their phone. No id, in
    # the path or the query: each reads only the job the visit's login names, so nobody can ask for anyone else's. A
    # `?staff=` sent along is read by nothing.
    model = StaffMember
    # A worker belongs to the whole shop, as their days and pay do: no side.
    side_field = None
    # No key: everyone may read their own, as everyone may read who they are (`me`, MeViewSet in
    # apps/people/api/views.py), so a worker who holds no role gets in. Only reads, so the base lets them through
    # before any key is asked (ShopViewSet.initial); a change could never come this way.
    action_permissions = {"attendance": SEES_THE_SIDE, "pay": SEES_THE_SIDE}
    # One answer, not pages: a month of one person.
    pagination_class = None

    @extend_schema(parameters=[AttendanceMonthQuery], responses=OwnAttendanceAnswer)
    @action(detail=False, methods=["get"])
    def attendance(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # The month first, as the manager's routes read it: none, or one that is no month, is refused under `month`.
        month = self._month(request)
        return Response(OwnAttendanceAnswer(own_attendance(self._shop(), self._job(), month)).data)

    @extend_schema(parameters=[AttendanceMonthQuery], responses=OwnPayAnswer)
    @action(detail=False, methods=["get"])
    def pay(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        month = self._month(request)
        return Response(OwnPayAnswer(own_pay(self._shop(), self._job(), month)).data)

    def _job(self) -> StaffMember:
        # The job the login names, read afresh through the guard, inside the visit's shop: a PIN's session names its
        # job, a password's the job it chose at this shop. One that isn't working now is refused by the reads themselves
        # (own_attendance, own_pay), which keep that rule (X2). cast: an office visit's actor is always a staff member
        # (perform_authentication refused any other).
        return StaffMember.objects.get(pk=cast(StaffMember, self.actor).pk)

    def _month(self, request: Request) -> date:
        asked = AttendanceMonthQuery(data=request.query_params)
        asked.is_valid(raise_exception=True)
        return cast(date, asked.validated_data["month"])

    def _shop(self) -> Shop:
        # The visit's own shop, open already (ShopViewSet): everything below reads inside it, through the guard.
        return Shop.objects.get(pk=self.actor.shop_id)


@contextmanager
def _refusing_a_taken_id(model: type[PayslipPayment | Attachment]) -> Iterator[None]:
    # A write that makes a row with the app's id: a payment, its signature. An id another shop's row holds is found only
    # by the insert, which PostgreSQL refuses on the table's primary key: answered as the id taken, and nothing more
    # about that row (03 §5.4), as CreateOnceMixin does (and the workers' photos, PPL-9). The service's block rolled
    # back with the refusal, so nothing was written.
    try:
        yield
    except IntegrityError as refusal:
        if id_taken(refusal, model):
            raise ValidationError({"id": ValidationError("This id is already in use.", code="id.taken")}) from None
        raise
