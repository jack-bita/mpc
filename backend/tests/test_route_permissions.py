"""backend/tests/test_route_permissions.py — office routes check what each person may do, side by side (PPL-5,
02 §5, rule X1).

PPL-3 gave every person their keys: roles and extra permissions, each on one side or on every side. This module
checks that the office routes ask for them, through the two hooks of their base (apps/core/api/base.py):

- a person sees only the sides they hold some permission on; another side's rows are "not found", as another
  shop's are (visible_sides()), whichever way a route reads them, its own @actions included;
- an action needs the permission its route names for it, on the row's side, or on the whole shop for a row of no
  side, or for a change sent to a whole list (check_side_permission()); without it, 403 permission_denied, and
  nothing is written;
- a person who is suspended, or has left, gets nothing at all;
- every route names a permission for each of its actions, and an action it forgets is refused: no route is ever
  open by forgetting (Jack, PPL-5);
- a show action needs only its side to be seen, or a key of its own: a side's rows, as flags are, then keep to the
  sides where that key is held, and to the whole shop's rows only for the key on every side (CTRL-4); the whole shop's
  rows, which have no side to keep to, ask the key on the whole shop, as the shop's workers do (PPL-4);
- a visit reads the person's permissions once, however many sides the shop has (Jack, PPL-5).

It lives outside `apps` because it needs both the side routes (`shops`) and the roles (`people`), and an app's own
tests may not import a higher layer (ADR-0035). Fake data only: the repo is public (03 §10).

    shop      sides                    who asks
    MFANO     Dawa (D), Vyakula (F)    staff_a and staff_a2, given roles test by test
"""

import hashlib
import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, models
from django.test.utils import CaptureQueriesContext
from django.urls import include, path
from pytest_django import Settings
from rest_framework import exceptions, mixins, serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.test import APIClient

from apps.control.api.views import AttachmentViewSet, FlagViewSet
from apps.control.models import AttachmentKind, AttachmentType
from apps.control.services import expect_attachment, receive_attachment_file
from apps.core.api import base
from apps.core.api.base import CreateOnceMixin, ShopViewSet
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, end_permission, grant_permission, mark_left, suspend
from apps.shops.api.views import ClosureViewSet, SettingViewSet, SideViewSet
from apps.shops.models import Closure, ClosureStatus, Setting, Shop, Side
from apps.shops.selectors import shop_today
from apps.shops.services import add_closure, add_side, set_setting
from apps.staffpay.api.views import (
    AdvanceViewSet,
    AttendanceDayViewSet,
    AttendanceMonthViewSet,
    AttendanceTapViewSet,
    AttendanceWorkerViewSet,
    MealMoneyViewSet,
    PayCorrectionViewSet,
    PayRateViewSet,
    PayRunViewSet,
    PayslipPaymentViewSet,
    PayslipViewSet,
    PayViewSet,
)
from apps.staffpay.models import Advance, AttendanceEvent, MealMoney, PayCorrection, PayRate, PayRun, Payslip
from apps.staffpay.tests.days import job, kept_day, switch_on
from tests.probe.api import NoteCreateSerializer, NoteSerializer
from tests.probe.models import Note
from tests.test_tenancy_sweep import addresses

SIDES = "/api/v1/shops/sides/"
SETTINGS = "/api/v1/shops/settings/"
CLOSURES = "/api/v1/shops/closures/"
ATTACHMENTS = "/api/v1/control/attachments/"
WORKERS = "/api/v1/people/staff/"
PAY_RATES = "/api/v1/staffpay/pay-rates/"
ATTENDANCE_MONTH = "/api/v1/staffpay/attendance-month/"
ATTENDANCE_WORKER = "/api/v1/staffpay/attendance-worker/{}/"
ATTENDANCE_DAY_DECIDE = "/api/v1/staffpay/attendance-days/{}/decide/"
ATTENDANCE_TAPS = "/api/v1/staffpay/attendance-taps/"
ATTENDANCE_TAP_VOID = "/api/v1/staffpay/attendance-taps/{}/void/"
MEAL_MONEY = "/api/v1/staffpay/meal-money/"
MEAL_MONEY_VOID = "/api/v1/staffpay/meal-money/{}/void/"
ADVANCES = "/api/v1/staffpay/advances/"
ADVANCE = "/api/v1/staffpay/advances/{}/"
ADVANCE_VOID = "/api/v1/staffpay/advances/{}/void/"
PAY = "/api/v1/staffpay/pay/"
PAY_WORKER = "/api/v1/staffpay/pay/{}/"
PAY_RUNS = "/api/v1/staffpay/pay-runs/"
PAYSLIPS = "/api/v1/staffpay/payslips/"
PAY_CORRECTIONS = "/api/v1/staffpay/pay-corrections/"

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


# --- Test-only routes, for the cases no real route has yet. A test that calls them runs with this module's address
# list (`@pytest.mark.urls(__name__)`); config/urls.py never mounts them, so the route walk below never sees them.


class PlainNoteMakerViewSet(mixins.CreateModelMixin, ShopViewSet[Note]):
    # Makes notes through DRF's own create, which asks for no key, unlike CreateOnceMixin's.
    model = Note
    side_field = None
    serializer_class = NoteSerializer
    action_permissions = {"create": Permission.SETTINGS_MANAGE}

    def perform_create(self, serializer: serializers.BaseSerializer[Note]) -> None:
        serializer.save(shop_id=self.actor.shop_id)


class RetextNoteViewSet(ShopViewSet[Note]):
    # A change to one note through an @action of its own that finds the note without get_object(), so never asks for
    # its key itself, as a careless route could.
    model = Note
    side_field = None
    action_permissions = {"retext": Permission.SETTINGS_MANAGE}

    @action(detail=True, methods=["post"])
    def retext(self, request: Request, pk: str) -> Response:
        text = request.data["text"] if isinstance(request.data, dict) else ""
        self.get_queryset().filter(pk=pk).update(text=text)
        return Response({"done": True})


class KNoteViewSet(mixins.ListModelMixin, ShopViewSet[Note]):
    # Adds to its rows, as a route that loads linked rows will: here, only the notes whose text starts with K. Through
    # base_rows(), so the person's sides are still kept to.
    model = Note
    side_field = None
    serializer_class = NoteSerializer
    action_permissions = {"list": base.SEES_THE_SIDE}

    def base_rows(self) -> models.QuerySet[Note]:
        return super().base_rows().filter(text__startswith="K")


class GuardedNoteViewSet(CreateOnceMixin[Note]):
    # Makes notes once, and has a row check of its own on top of the base's: a note marked "siri" is never handed back.
    model = Note
    side_field = None
    serializer_class = NoteSerializer
    create_serializer_class = NoteCreateSerializer
    action_permissions = {"create": Permission.SETTINGS_MANAGE}

    def create_row(self, data: dict[str, Any]) -> Note:
        note = Note(id=data["id"], shop_id=self.actor.shop_id, text=data["text"])
        note.save()
        return note

    def check_object_permissions(self, request: Request, obj: Any) -> None:
        super().check_object_permissions(request, obj)
        if obj.text == "siri":
            raise exceptions.PermissionDenied("A secret note is never handed back.")


class ManagedNoteViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ShopViewSet[Note]):
    # The whole shop's rows, shown only behind a key of their own, as the shop's workers are: for whoever manages
    # them (`staff.manage`), not for everyone who works there (PPL-4).
    model = Note
    side_field = None
    serializer_class = NoteSerializer
    action_permissions = {"list": Permission.STAFF_MANAGE, "retrieve": Permission.STAFF_MANAGE}


class ManagedNoteMakerViewSet(mixins.RetrieveModelMixin, CreateOnceMixin[Note]):
    # Makes the whole shop's notes once, and shows one behind a key of its own, as the shop's workers are: a create
    # sent again shows its row, so it must ask that key too, or it is a way round it (PPL-4's review).
    model = Note
    side_field = None
    serializer_class = NoteSerializer
    create_serializer_class = NoteCreateSerializer
    action_permissions = {"create": Permission.STAFF_MANAGE, "retrieve": Permission.STAFF_MANAGE}

    def create_row(self, data: dict[str, Any]) -> Note:
        note = Note(id=data["id"], shop_id=self.actor.shop_id, text=data["text"])
        note.save()
        return note


class RuleSerializer(serializers.ModelSerializer[Setting]):
    class Meta:
        model = Setting
        fields = ["id", "value"]


class RuleBehindAKeyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ShopViewSet[Setting]):
    # A side's rows shown behind a key of their own, as the flags are (`flag.review`, CTRL-4) and debts will be, and a
    # change to one behind another key. A rule's row stands for them: it belongs to a side, or to the whole shop.
    model = Setting
    serializer_class = RuleSerializer
    action_permissions = {
        "list": Permission.DEBT_VIEW,
        "retrieve": Permission.DEBT_VIEW,
        "touch": Permission.SETTINGS_MANAGE,
    }

    @action(detail=True, methods=["post"])
    def touch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(self.get_serializer(self.get_object()).data)


router = SimpleRouter()
router.register("rules-behind-a-key", RuleBehindAKeyViewSet, basename="rule-behind-a-key")
router.register("managed-notes", ManagedNoteViewSet, basename="managed-note")
router.register("managed-note-makers", ManagedNoteMakerViewSet, basename="managed-note-maker")
router.register("plain-note-makers", PlainNoteMakerViewSet, basename="plain-note-maker")
router.register("guarded-notes", GuardedNoteViewSet, basename="guarded-note")
router.register("retext-notes", RetextNoteViewSet, basename="retext-note")
router.register("k-notes", KNoteViewSet, basename="k-note")
urlpatterns = [path("api/v1/test/", include(router.urls))]

PLAIN_MAKERS = "/api/v1/test/plain-note-makers/"
MANAGED_NOTES = "/api/v1/test/managed-notes/"
RULES_BEHIND_A_KEY = "/api/v1/test/rules-behind-a-key/"


def client_for(staff: StaffMember) -> APIClient:
    # The way the office screens call: logged in as this person, at their shop. force_authenticate puts the person
    # straight into `request.auth`, as the real logins do (AUTH-3, AUTH-4; backend/conftest.py).
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def new_side() -> dict[str, str]:
    # A third side, as the app sends it: with the id the app made itself (ADR-0007).
    return {"id": str(uuid.uuid7()), "code": "P", "name": "Pembejeo"}


@pytest.fixture
def sides(shop_a: Shop) -> dict[str, Side]:
    # Shop A's two sides, made the way the app makes them, with their stock locations and drawers (SHOP-2).
    with shop_context(shop_a):
        return {
            "D": add_side(shop=shop_a, code="D", name="Dawa", by=None),
            "F": add_side(shop=shop_a, code="F", name="Vyakula", by=None),
        }


def side_name(shop: Shop, side: Side) -> str:
    # The side's name as stored, read again from the database: a refusal must have written nothing.
    with shop_context(shop):
        return Side.objects.get(pk=side.pk).name


# --- What a person sees


@pytest.mark.django_db
def test_list_shows_only_sides_with_a_permission(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # Asha sells on Dawa only (spec §6). Vyakula is not hers to see: it is left out of her list, and its own address
    # is "not found", as another shop's side is. "Forbidden" would tell her it exists (03 §5.4).
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    asha = client_for(staff_a)

    assert [row["code"] for row in asha.get(SIDES).json()["results"]] == ["D"]
    assert asha.get(f"{SIDES}{sides['D'].pk}/").status_code == 200
    hidden = asha.get(f"{SIDES}{sides['F'].pk}/")
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "not_found"

    # One extra key on Vyakula, a grant rather than a role, is enough to see it too (02 §5).
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.STOCK_COUNT, side=sides["F"], by=None)
    assert {row["code"] for row in asha.get(SIDES).json()["results"]} == {"D", "F"}


# --- What a person may do


@pytest.mark.django_db
def test_action_needs_its_permission(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Adding or renaming a side changes the shop itself: `settings.manage`, one of the owner's own (spec §6).
    # A Manager on every side sees both sides, and still may not.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    manager = client_for(staff_a2)

    rename = manager.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Dawa za Kuku", "version": 1})
    assert rename.status_code == 403
    assert rename.json()["code"] == "permission_denied"
    assert side_name(shop_a, sides["D"]) == "Dawa"

    add = manager.post(SIDES, new_side())
    assert add.status_code == 403
    assert add.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert not Side.objects.filter(code="P").exists()

    # The owner holds it on every side, so both work.
    give_role(staff_a, RoleTemplate.OWNER, None)
    owner = client_for(staff_a)
    assert owner.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Dawa za Kuku", "version": 1}).status_code == 200
    assert owner.post(SIDES, new_side()).status_code == 201


@pytest.mark.django_db
def test_side_switch_needs_settings_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Switching a side on or off changes what the shop sells from (ADR-0033): `settings.manage`, the owner's, as adding
    # or renaming one does. A Manager on every side is refused, and Vyakula stays off; the owner may (SHOP-3).
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    switch = {"is_live": True, "version": 1}
    refused = client_for(staff_a2).patch(f"{SIDES}{sides['F'].pk}/", switch, format="json")
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert Side.objects.get(pk=sides["F"].pk).is_live is False

    give_role(staff_a, RoleTemplate.OWNER, None)
    assert client_for(staff_a).patch(f"{SIDES}{sides['F'].pk}/", switch, format="json").status_code == 200


@pytest.mark.django_db
def test_side_band_needs_settings_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # A side's band is how every laptop of the shop tells its sides apart (SHOP-4): `settings.manage`, the owner's, as
    # renaming or switching one is. A Manager on every side is refused, and Vyakula stays blue; the owner may.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    band = {"band": "striped", "version": 1}
    refused = client_for(staff_a2).patch(f"{SIDES}{sides['F'].pk}/", band, format="json")
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert Side.objects.get(pk=sides["F"].pk).band == "blue"

    give_role(staff_a, RoleTemplate.OWNER, None)
    assert client_for(staff_a).patch(f"{SIDES}{sides['F'].pk}/", band, format="json").status_code == 200


@pytest.mark.django_db
def test_setting_needs_settings_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # A rule's new value changes the shop's rules: `settings.manage`, the owner's (spec §6). A Manager on every side
    # sees the rules and may not change one: refused, and nothing written. The owner may (SHOP-3).
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    today = shop_today(shop_a).isoformat()

    def sent() -> dict[str, str]:
        return {"id": str(uuid.uuid7()), "key": "attendance.late_fine", "value": "2000", "effective_from": today}

    manager = client_for(staff_a2)
    assert manager.get(SETTINGS).status_code == 200
    refused = manager.post(SETTINGS, sent(), format="json")
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert not Setting.objects.filter(shop=shop_a).exists()

    give_role(staff_a, RoleTemplate.OWNER, None)
    assert client_for(staff_a).post(SETTINGS, sent(), format="json").status_code == 201


@pytest.mark.django_db
def test_settings_list_keeps_to_the_persons_sides(shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember) -> None:
    # Asha holds one key, on Dawa only: she sees the whole shop's rules, and Dawa's own, never Vyakula's, as every read
    # keeps to the sides a person sees (PPL-5). Seeing them hides nothing a counter doesn't hold: every rule travels to
    # every laptop of the shop (SYNC-2). The owner has set the late fine, a row of no side, and a tolerance on each
    # side: the late fine's row is the whole shop's, so she sees it beside its value, and Vyakula's row stays hidden.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.STOCK_COUNT, side=sides["D"], by=None)
        fine = set_setting(shop_a, key="attendance.late_fine", value="2000", effective_from=today, by=None)
        dawa = set_setting(shop_a, key="cash.tolerance", value="500", effective_from=today, side=sides["D"], by=None)
        set_setting(shop_a, key="cash.tolerance", value="700", effective_from=today, side=sides["F"], by=None)
    rules = client_for(staff_a).get(SETTINGS).json()["rules"]

    assert {rule["side"] for rule in rules} == {None, str(sides["D"].pk)}
    rows = {(rule["key"], row["id"], row["value"]) for rule in rules for row in rule["rows"]}
    assert rows == {("attendance.late_fine", str(fine.pk), "2000.00"), ("cash.tolerance", str(dawa.pk), "500.00")}


@pytest.mark.django_db
def test_who_sees_no_side_sees_no_rule(sides: dict[str, Side], staff_a: StaffMember) -> None:
    # A person who holds no key sees no side, and so no row of the whole shop either (PPL-5): not even the shop's rules'
    # values, which come from the registry and the rows. The answer still says the shop's today.
    answer = client_for(staff_a).get(SETTINGS).json()

    assert answer["rules"] == []


@pytest.mark.django_db
def test_a_key_on_one_side_opens_only_that_side(shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember) -> None:
    # Rule X1 itself: a key works on the side it was given on, and nowhere else. Juma may change the shop's rules on
    # Dawa only, and counts stock on Vyakula, so he sees both. He may rename Dawa, not Vyakula; and adding a side, an
    # action on the whole shop, needs the key on every side, which he doesn't hold (02 §5).
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.SETTINGS_MANAGE, side=sides["D"], by=None)
        grant_permission(staff_a, Permission.STOCK_COUNT, side=sides["F"], by=None)
    juma = client_for(staff_a)

    assert juma.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Dawa za Kuku", "version": 1}).status_code == 200
    vyakula = juma.patch(f"{SIDES}{sides['F'].pk}/", {"name": "Chakula", "version": 1})
    assert vyakula.status_code == 403
    assert vyakula.json()["code"] == "permission_denied"
    assert side_name(shop_a, sides["F"]) == "Vyakula"
    assert juma.post(SIDES, new_side()).status_code == 403


@pytest.mark.django_db
def test_a_create_sent_twice_is_answered_as_a_read(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # The owner adds a side; the manager's phone sends the same create again, with the same id. Nothing is made, so
    # the create's key is not asked: the manager, who may see every side but not add one, gets the stored side back,
    # as any read of it, and there is still one side P (ADR-0007, CORE-6).
    give_role(staff_a, RoleTemplate.OWNER, None)
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    side = new_side()
    first = client_for(staff_a).post(SIDES, side)

    again = client_for(staff_a2).post(SIDES, side)

    assert again.status_code == 201
    assert again.json() == first.json()
    with shop_context(shop_a):
        assert Side.objects.filter(code="P").count() == 1


def test_side_routes_name_their_permissions() -> None:
    # Showing a side needs only to see it; adding or renaming one needs `settings.manage` (spec §6). Written out in
    # full, so a change to what a route asks for is a change to this test too.
    assert SideViewSet.action_permissions == {
        "list": base.SEES_THE_SIDE,
        "retrieve": base.SEES_THE_SIDE,
        "create": Permission.SETTINGS_MANAGE,
        "partial_update": Permission.SETTINGS_MANAGE,
    }


@pytest.mark.django_db
def test_closures_need_settings_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # A closed day changes everyone's pay: `settings.manage`, the owner's (spec §6), on the whole shop, as a closure
    # closes both sides (ATT-8). A Manager on every side sees the closures and may change none: each change refused, and
    # nothing written. The owner may make all three.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    today = shop_today(shop_a)
    with shop_context(shop_a):
        krismasi = add_closure(
            shop_a, first_day=today + timedelta(days=5), last_day=today + timedelta(days=6), name="Krismasi", by=None
        )

    def new() -> dict[str, str]:
        first = (today + timedelta(days=1)).isoformat()
        return {"id": str(uuid.uuid7()), "first_day": first, "last_day": first, "name": "Msiba wa bibi"}

    later = {"last_day": (today + timedelta(days=7)).isoformat(), "reason": "Zaidi"}
    changes: list[tuple[str, Callable[[], dict[str, str]]]] = [
        (CLOSURES, new),
        (f"{CLOSURES}{krismasi.pk}/last-day/", lambda: later),
        (f"{CLOSURES}{krismasi.pk}/cancel/", lambda: {"reason": "Imeahirishwa"}),
    ]
    manager = client_for(staff_a2)
    assert manager.get(CLOSURES).status_code == 200
    for url, sent in changes:
        refused = manager.post(url, sent(), format="json")
        assert refused.status_code == 403, url
        assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert list(Closure.objects.values_list("name", "last_day", "status")) == [
            ("Krismasi", today + timedelta(days=6), ClosureStatus.ACTIVE)
        ]

    give_role(staff_a, RoleTemplate.OWNER, None)
    owner = client_for(staff_a)
    assert [owner.post(url, sent(), format="json").status_code for url, sent in changes] == [201, 200, 200]


@pytest.mark.django_db
def test_a_key_on_one_side_changes_no_closure(shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember) -> None:
    # Juma may change the shop's rules on Dawa only (X1). A closure closes both sides, so changing one is an action on
    # the whole shop, which needs the key on every side: he sees the closures, as he sees a side, and may add, move or
    # cancel none of them. Nothing changes.
    today = shop_today(shop_a)
    in_a_week = today + timedelta(days=7)
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.SETTINGS_MANAGE, side=sides["D"], by=None)
        krismasi = add_closure(shop_a, first_day=in_a_week, last_day=in_a_week, name="Krismasi", by=None)
    juma = client_for(staff_a)

    assert [row["name"] for row in juma.get(CLOSURES).json()["closures"]] == ["Krismasi"]
    first = (today + timedelta(days=1)).isoformat()
    new_one = {"id": str(uuid.uuid7()), "first_day": first, "last_day": first, "name": "Msiba wa bibi"}
    later = {"last_day": (in_a_week + timedelta(days=1)).isoformat(), "reason": "Zaidi"}
    for url, sent in (
        (CLOSURES, new_one),
        (f"{CLOSURES}{krismasi.pk}/last-day/", later),
        (f"{CLOSURES}{krismasi.pk}/cancel/", {"reason": "Imeahirishwa"}),
    ):
        refused = juma.post(url, sent, format="json")
        assert refused.status_code == 403, url
        assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert list(Closure.objects.values_list("name", "last_day", "status")) == [
            ("Krismasi", in_a_week, ClosureStatus.ACTIVE)
        ]


def test_closures_routes_name_their_permissions() -> None:
    # Seeing the closures needs only to see a side; adding one, moving its last day and cancelling it each need
    # `settings.manage` (ATT-8). Written out in full, as above.
    assert ClosureViewSet.action_permissions == {
        "list": base.SEES_THE_SIDE,
        "create": Permission.SETTINGS_MANAGE,
        "cancel": Permission.SETTINGS_MANAGE,
        "last_day": Permission.SETTINGS_MANAGE,
    }


def test_attachment_routes_name_their_permissions() -> None:
    # Opening a photo's file only shows it, so the route asks only to see the shop's rows; each kind's own key is asked
    # inside the action, on the whole shop (CTRL-3, ATTACHMENT_KINDS), as the key depends on the photo. Written out in
    # full, as above.
    assert AttachmentViewSet.action_permissions == {"file": base.SEES_THE_SIDE}


def test_flag_routes_name_their_permissions() -> None:
    # A flag shows only to whoever may close it, so even its list and its page are behind `flag.review`, as its three
    # actions are (CTRL-4). Written out in full, as above.
    assert FlagViewSet.action_permissions == {
        "list": Permission.FLAG_REVIEW,
        "retrieve": Permission.FLAG_REVIEW,
        "explain": Permission.FLAG_REVIEW,
        "resolve": Permission.FLAG_REVIEW,
        "dismiss": Permission.FLAG_REVIEW,
    }


def test_settings_routes_name_their_permissions() -> None:
    # Seeing the rules needs only to see a side; a new value needs `settings.manage` (SHOP-3), on the row's side, or on
    # the whole shop for a shop's rule. Written out in full, as above.
    assert SettingViewSet.action_permissions == {
        "list": base.SEES_THE_SIDE,
        "create": Permission.SETTINGS_MANAGE,
    }


# --- A person who may not work


def stop(how: str, staff: StaffMember) -> None:
    # Suspended for a while, or gone for good (02 §5): either way, they hold nothing.
    with shop_context(staff.shop_id):
        if how == "suspended":
            suspend(staff, by=None, reason="Uchunguzi wa upotevu")
        else:
            mark_left(staff, left_on=staff.started_on, by=None, reason="Amehama")


@pytest.mark.django_db
@pytest.mark.parametrize("how", ["suspended", "left"])
def test_suspended_member_gets_nothing_from_routes(
    how: str, shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # The owner's own login, after they stop working here. The client still holds the person as they were loaded,
    # "active": the check must read the status from the database on each visit, never trust that copy (X2).
    give_role(staff_a, RoleTemplate.OWNER, None)
    client = client_for(staff_a)
    in_a_week = shop_today(shop_a) + timedelta(days=7)
    with shop_context(shop_a):
        krismasi = add_closure(shop_a, first_day=in_a_week, last_day=in_a_week, name="Krismasi", by=None)
        # Their own photo, its file kept (CTRL-3).
        face = b"\xff\xd8\xff a made-up face"
        own_photo = expect_attachment(
            id=uuid.uuid7(),
            kind=AttachmentKind.STAFF_PHOTO,
            subject=staff_a,
            content_type=AttachmentType.JPEG,
            size=len(face),
            sha256=hashlib.sha256(face).hexdigest(),
            by=staff_a,
        )
        receive_attachment_file(own_photo.pk, content=face)
        # A worker of theirs (PPL-4).
        juma = add_staff(
            shop=shop_a, user=User.objects.create_user(full_name="Juma Mfano"), display_name="Juma", by=None
        )
    stop(how, staff_a)

    assert client.get(SIDES).json()["results"] == []
    assert client.get(f"{SIDES}{sides['D'].pk}/").status_code == 404
    assert client.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Imeibiwa", "version": 1}).status_code == 404
    assert client.post(SIDES, new_side()).status_code == 403
    assert side_name(shop_a, sides["D"]) == "Dawa"
    with shop_context(shop_a):
        assert not Side.objects.filter(code="P").exists()
    # The shop's rules too (SHOP-3): none shown, not even the whole shop's, whose values come from the registry; no side
    # switched, and no new value written.
    assert client.get(SETTINGS).json()["rules"] == []
    switch = {"is_live": True, "version": 1}
    assert client.patch(f"{SIDES}{sides['F'].pk}/", switch, format="json").status_code == 404
    # Nor a side's band (SHOP-4).
    band = {"band": "striped", "version": 1}
    assert client.patch(f"{SIDES}{sides['F'].pk}/", band, format="json").status_code == 404
    today = shop_today(shop_a).isoformat()
    fine = {"id": str(uuid.uuid7()), "key": "attendance.late_fine", "value": "9000", "effective_from": today}
    assert client.post(SETTINGS, fine, format="json").status_code == 403
    # Nor the days the shop is closed (ATT-8): none shown; none added, cancelled or moved.
    assert client.get(CLOSURES).json()["closures"] == []
    new_one = {"id": str(uuid.uuid7()), "first_day": today, "last_day": today, "name": "Siku yangu"}
    assert client.post(CLOSURES, new_one, format="json").status_code == 403
    assert client.post(f"{CLOSURES}{krismasi.pk}/cancel/", {"reason": "Hapana"}, format="json").status_code == 404
    later = {"last_day": (in_a_week + timedelta(days=3)).isoformat(), "reason": "Hapana"}
    assert client.post(f"{CLOSURES}{krismasi.pk}/last-day/", later, format="json").status_code == 404
    # Nor a photo, not even their own face (CTRL-3): not found, as they see no side.
    assert client.get(f"{ATTACHMENTS}{own_photo.pk}/file/").status_code == 404
    # Nor the shop's workers (PPL-4): the list and one worker refused, as the key is asked first; nobody added; and
    # nobody fixed (PPL-10), suspended, brought back or marked left: not found, as they see no side.
    assert client.get(WORKERS).status_code == 403
    assert client.get(f"{WORKERS}{juma.pk}/").status_code == 403
    worker = {"id": str(uuid.uuid7()), "full_name": "Asha Mfano", "display_name": "Asha"}
    assert client.post(WORKERS, worker, format="json").status_code == 403
    for change, sent in (
        ("suspend", {"reason": "Hapana"}),
        ("unsuspend", {"reason": "Hapana"}),
        ("leave", {"reason": "Hapana", "left_on": today}),
    ):
        assert client.post(f"{WORKERS}{juma.pk}/{change}/", sent, format="json").status_code == 404, change
    fix = {"version": 1, "reason": "Hapana", "job_title": "Fundi"}
    assert client.patch(f"{WORKERS}{juma.pk}/", fix, format="json").status_code == 404
    # Nor is a worker's photo set or taken off (PPL-9).
    photo = f"{WORKERS}{juma.pk}/photo/?photo={uuid.uuid7()}"
    assert client.put(photo, data=face, content_type="image/jpeg").status_code == 404
    off = {"photo": str(uuid.uuid7()), "reason": "Hapana"}
    assert client.post(f"{WORKERS}{juma.pk}/remove-photo/", off, format="json").status_code == 404
    # Nor the month's attendance (ATT-5), nor a worker's month (ATT-12), Juma's or their own: refused, as the key is
    # asked first, before any month is worked out.
    assert client.get(ATTENDANCE_MONTH, {"month": "2026-10"}).status_code == 403
    for whose in (juma, staff_a):
        assert client.get(ATTENDANCE_WORKER.format(whose.pk), {"month": "2026-10"}).status_code == 403
    with shop_context(shop_a):
        assert Side.objects.get(pk=sides["F"].pk).is_live is False
        assert Side.objects.get(pk=sides["F"].pk).band == "blue"
        assert not Setting.objects.filter(shop=shop_a).exists()
        assert list(Closure.objects.values_list("name", "last_day", "status")) == [
            ("Krismasi", in_a_week, ClosureStatus.ACTIVE)
        ]
        assert StaffMember.objects.get(pk=juma.pk).status == "active"
        assert (StaffMember.objects.get(pk=juma.pk).job_title, StaffMember.objects.get(pk=juma.pk).version) == ("", 1)
        assert not StaffMember.objects.filter(display_name="Asha").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("how", ["suspended", "left"])
def test_who_sees_no_side_sees_no_whole_shop_rows(
    how: str, settings: Settings, shop_a: Shop, staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A row of the whole shop, like a product, has no side to hide it behind (`side_field` None). So a person who
    # sees no side at all sees none of those rows either. The probe's notes stand in for such rows
    # (tests/probe/api.py).
    settings.ROOT_URLCONF = "tests.probe.urls"
    with shop_context(shop_a):
        Note(shop=shop_a, text="Kumbukumbu ya duka").save()
    give_role(staff_a, RoleTemplate.OWNER, None)
    client = client_for(staff_a)
    assert len(client.get("/api/v1/probe/notes/").json()["results"]) == 1

    stop(how, staff_a)

    assert client.get("/api/v1/probe/notes/").json()["results"] == []


@pytest.mark.django_db
def test_every_read_of_a_route_keeps_to_the_persons_sides(
    settings: Settings, shop_a: Shop, staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A route's own @action may read its rows without DRF's list, as an export does (tests/probe/api.py). The sides a
    # person sees are kept to where every read of a route starts (get_queryset), so such an action shows a person
    # who sees no side nothing, as a list does.
    settings.ROOT_URLCONF = "tests.probe.urls"
    with shop_context(shop_a):
        Note(shop=shop_a, text="Kumbukumbu ya duka").save()
    give_role(staff_a, RoleTemplate.OWNER, None)
    client = client_for(staff_a)
    assert client.get("/api/v1/probe/notes/export/").content == b"Kumbukumbu ya duka"

    stop("suspended", staff_a)

    assert client.get("/api/v1/probe/notes/export/").content == b""


@pytest.mark.django_db
def test_change_to_a_whole_list_needs_its_key_on_every_side(
    settings: Settings, shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # A change sent to a whole list names no row, so no row's side to ask about: it could touch every side's rows,
    # so it needs its key on every side. The probe's `clear` stands in for one; it needs `settings.manage`.
    settings.ROOT_URLCONF = "tests.probe.urls"
    clear = "/api/v1/probe/notes-in-bulk/clear/"
    with shop_context(shop_a):
        # Juma holds it on Dawa only; Asha on every side.
        grant_permission(staff_a, Permission.SETTINGS_MANAGE, side=sides["D"], by=None)
        grant_permission(staff_a2, Permission.SETTINGS_MANAGE, side=None, by=None)

    refused = client_for(staff_a).delete(clear)
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    assert client_for(staff_a2).delete(clear).status_code == 204


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_create_that_does_not_ask_needs_its_key_on_every_side(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # A route built on DRF's own create, not on CreateOnceMixin's, which asks with the new row's side: nothing in it
    # asks for a key, so the base asks on the whole shop before it runs. Juma, a Seller on Dawa, doesn't hold
    # `settings.manage`: refused, and no note is made. Asha, the owner, may.
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a2, RoleTemplate.OWNER, None)

    refused = client_for(staff_a).post(PLAIN_MAKERS, {"text": "Haikupaswa"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert not Note.objects.exists()
    assert client_for(staff_a2).post(PLAIN_MAKERS, {"text": "Kumbukumbu"}).status_code == 201


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_change_to_one_row_is_checked_before_it_runs(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # The route's own action finds its note without get_object(), so nothing in it asks for `settings.manage`. The
    # base finds and checks the row before the action runs: Juma, a Worker on every side, sees the note but may not
    # change it, so it stays as it was. Asha, the owner, may.
    with shop_context(shop_a):
        note = Note(shop=shop_a, text="Kumbukumbu")
        note.save()
    give_role(staff_a, RoleTemplate.WORKER, None)
    give_role(staff_a2, RoleTemplate.OWNER, None)
    retext = f"/api/v1/test/retext-notes/{note.pk}/retext/"

    refused = client_for(staff_a).post(retext, {"text": "Imebadilishwa"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert Note.objects.get(pk=note.pk).text == "Kumbukumbu"
    assert client_for(staff_a2).post(retext, {"text": "Imebadilishwa"}).status_code == 200


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_route_adds_to_its_rows_without_losing_the_side_check(
    shop_a: Shop, staff_a: StaffMember, give_role: GiveRole
) -> None:
    # The route keeps only the notes starting with K, in base_rows(): the owner sees that one and not the other, so
    # the route's own rows are used. Suspended, they see none: the side check still runs after them.
    with shop_context(shop_a):
        Note(shop=shop_a, text="Kumbukumbu").save()
        Note(shop=shop_a, text="Zamani").save()
    give_role(staff_a, RoleTemplate.OWNER, None)
    client = client_for(staff_a)
    assert [row["text"] for row in client.get("/api/v1/test/k-notes/").json()["results"]] == ["Kumbukumbu"]

    stop("suspended", staff_a)

    assert client.get("/api/v1/test/k-notes/").json()["results"] == []


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_create_sent_twice_keeps_the_routes_own_checks(staff_a: StaffMember, give_role: GiveRole) -> None:
    # The route refuses to hand back a note marked "siri", in a row check of its own. The repeat of the create that
    # made one is handed back as a read, through the same checks as any row: the route's own refuses it too.
    give_role(staff_a, RoleTemplate.OWNER, None)
    client = client_for(staff_a)
    note = {"id": str(uuid.uuid7()), "text": "siri"}
    assert client.post("/api/v1/test/guarded-notes/", note).status_code == 201

    again = client.post("/api/v1/test/guarded-notes/", note)

    assert again.status_code == 403
    assert again.json()["code"] == "permission_denied"


# --- Every action is named


def permission_problems(routes: Iterable[tuple[type[ShopViewSet[Any]], Mapping[str, str]]]) -> list[str]:
    # What breaks the two rules every route's permission list keeps, for each route and the actions its address
    # answers with ({"get": "list", "post": "create"}, as DRF's router notes them):
    # - every action is named, so none is open by forgetting;
    # - a change (any method but a read) always names a key of its own: seeing a side is not leave to change it.
    # A show action names either: to see its side, or a key of its own, which the base keeps its rows to (CTRL-4).
    problems = []
    for view, actions in routes:
        named = getattr(view, "action_permissions", {})
        for method, name in sorted(actions.items()):
            if name not in named:
                problems.append(f"{view.__name__}: {name} names no permission")
            elif method not in ("get", "head") and named[name] is base.SEES_THE_SIDE:
                problems.append(f"{view.__name__}: {name} changes rows with no key of its own")
    return problems


def office_routes() -> list[tuple[type[ShopViewSet[Any]], Mapping[str, str]]]:
    # Every route of the office API, found by walking the address list as the tenancy sweep does, so a new route is
    # checked with no change here.
    routes = []
    for address in addresses():
        view = getattr(address.view, "cls", None)
        actions = getattr(address.view, "actions", None) or {}
        if isinstance(view, type) and issubclass(view, ShopViewSet) and actions:
            routes.append((view, actions))
    return routes


def test_every_route_names_a_permission_for_each_action() -> None:
    routes = office_routes()
    # Not passed by looking at nothing: the side routes are there.
    assert SideViewSet in {view for view, _ in routes}
    assert permission_problems(routes) == []


def rows_problems(views: Iterable[type[ShopViewSet[Any]]]) -> list[str]:
    # A route that writes over get_queryset() can lose the person's sides, which are kept to there: such a route
    # writes over base_rows() instead (apps/core/api/base.py).
    return sorted(
        {
            f"{view.__name__} writes over get_queryset()"
            for view in views
            if view.get_queryset is not ShopViewSet.get_queryset
        }
    )


def test_no_route_writes_over_get_queryset() -> None:
    assert rows_problems(view for view, _ in office_routes()) == []


def test_rows_check_finds_a_route_that_writes_over_get_queryset() -> None:
    class Narrowed(ShopViewSet[Side]):
        model = Side

        def base_rows(self) -> models.QuerySet[Side]:
            return super().base_rows().filter(code="D")

    class Overridden(ShopViewSet[Side]):
        model = Side

        def get_queryset(self) -> models.QuerySet[Side]:
            return Side.objects.all()

    assert rows_problems([Narrowed, Overridden]) == ["Overridden writes over get_queryset()"]


def test_permission_check_finds_what_breaks_its_rules() -> None:
    # The check itself, handed routes built to break each rule once.
    class Named(ShopViewSet[Side]):
        model = Side
        action_permissions = {"list": base.SEES_THE_SIDE, "create": Permission.SETTINGS_MANAGE}

    class ShowsDebts(ShopViewSet[Side]):
        # A side's rows behind a key: allowed, kept to the sides where it is held (CTRL-4).
        model = Side
        action_permissions = {"list": Permission.DEBT_VIEW}

    class ShowsWorkers(ShopViewSet[StaffMember]):
        # Rows of the whole shop behind a key: allowed, asked on the whole shop (PPL-4).
        model = StaffMember
        side_field = None
        action_permissions = {"list": Permission.STAFF_MANAGE}

    class Forgets(ShopViewSet[Side]):
        model = Side

    class ChangesBySight(ShopViewSet[Side]):
        model = Side
        action_permissions = {"partial_update": base.SEES_THE_SIDE}

    assert permission_problems(
        [
            (Named, {"get": "list", "post": "create"}),
            (ShowsDebts, {"get": "list"}),
            (ShowsWorkers, {"get": "list"}),
            (Forgets, {"post": "void"}),
            (ChangesBySight, {"patch": "partial_update"}),
        ]
    ) == [
        "Forgets: void names no permission",
        "ChangesBySight: partial_update changes rows with no key of its own",
    ]


@pytest.mark.django_db
def test_unnamed_action_refused(
    monkeypatch: pytest.MonkeyPatch, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A route that forgets an action is a bug, not a person's mistake: it answers a server error, which is logged,
    # instead of a 403 that would hide the bug behind a plain "no", or a 200 that would open the action to all.
    # Even the owner, who holds every key, is refused.
    monkeypatch.setattr(SideViewSet, "action_permissions", {"retrieve": base.SEES_THE_SIDE})
    give_role(staff_a, RoleTemplate.OWNER, None)

    with pytest.raises(ImproperlyConfigured, match="list"):
        client_for(staff_a).get(SIDES)


@pytest.fixture
def rules(shop_a: Shop, sides: dict[str, Side]) -> dict[str, Setting]:
    # Three rows: one of Dawa's, one of Vyakula's and one of the whole shop's.
    with shop_context(shop_a):
        return {
            name: Setting.objects.create(
                shop=shop_a, key=f"test.{name}", value=f'"{name}"', effective_from=shop_today(shop_a), side=side
            )
            for name, side in (("dawa", sides["D"]), ("vyakula", sides["F"]), ("duka", None))
        }


def values_shown(client: APIClient) -> set[str]:
    return {row["value"].strip('"') for row in client.get(RULES_BEHIND_A_KEY).json()["results"]}


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_side_list_behind_a_key_keeps_to_the_sides_that_hold_it(
    shop_a: Shop, sides: dict[str, Side], rules: dict[str, Setting], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # Asha sells on Dawa, where her role holds debt.view, and loads on Vyakula, where it doesn't. Behind that key she
    # sees Dawa's rows only: Vyakula's, a side she works on, and the whole shop's are "not found", alike, as another
    # shop's are (03 §5.4).
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a, RoleTemplate.WORKER, sides["F"])
    asha = client_for(staff_a)

    assert values_shown(asha) == {"dawa"}
    assert asha.get(f"{RULES_BEHIND_A_KEY}{rules['dawa'].pk}/").status_code == 200
    for hidden in ("vyakula", "duka"):
        answer = asha.get(f"{RULES_BEHIND_A_KEY}{rules[hidden].pk}/")
        assert (answer.status_code, answer.json()["code"]) == (404, "not_found"), hidden

    # The key on both of today's sides is still not the whole shop's: a third side may come, whose rows it opens not.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.DEBT_VIEW, side=sides["F"], by=None)
    assert values_shown(client_for(staff_a)) == {"dawa", "vyakula"}

    # On every side: the whole shop's rows too.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.DEBT_VIEW, side=None, by=None)
    assert values_shown(client_for(staff_a)) == {"dawa", "vyakula", "duka"}


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_who_holds_the_key_nowhere_is_refused(
    sides: dict[str, Side], rules: dict[str, Setting], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # Juma loads on Dawa: he sees the side, and holds no key to these rows on any. Refused, as a whole shop's list
    # refuses him (PPL-4), so the page says why, where an empty list would say that nothing waits.
    give_role(staff_a, RoleTemplate.WORKER, sides["D"])
    juma = client_for(staff_a)

    for address in (RULES_BEHIND_A_KEY, f"{RULES_BEHIND_A_KEY}{rules['dawa'].pk}/"):
        refused = juma.get(address)
        assert (refused.status_code, refused.json()["code"]) == (403, "permission_denied"), address


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_change_to_a_row_shown_behind_a_key_keeps_to_the_key(
    shop_a: Shop, sides: dict[str, Side], rules: dict[str, Setting], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A row a person may not be shown is "not found" for a change too, even one whose own key they hold everywhere: a
    # 403, or a change that went through, would tell them it is there.
    def touch(name: str) -> int:
        return client_for(staff_a).post(f"{RULES_BEHIND_A_KEY}{rules[name].pk}/touch/").status_code

    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    assert {name: touch(name) for name in rules} == {"dawa": 403, "vyakula": 404, "duka": 404}

    with shop_context(shop_a):
        grant_permission(staff_a, Permission.SETTINGS_MANAGE, side=None, by=None)
    assert {name: touch(name) for name in rules} == {"dawa": 200, "vyakula": 404, "duka": 404}


@pytest.mark.django_db
def test_the_sides_themselves_keep_to_a_key(
    monkeypatch: pytest.MonkeyPatch, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A route whose rows are sides, kept to the key as a side's rows are. The read of one side keeps its own rule, as
    # its action names it: to see the side.
    monkeypatch.setattr(
        SideViewSet, "action_permissions", {**SideViewSet.action_permissions, "list": Permission.DEBT_VIEW}
    )
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a, RoleTemplate.WORKER, sides["F"])
    asha = client_for(staff_a)

    assert [row["code"] for row in asha.get(SIDES).json()["results"]] == ["D"]
    assert asha.get(f"{SIDES}{sides['F'].pk}/").status_code == 200


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_whole_shop_list_behind_a_key_needs_it_on_the_whole_shop(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # The shop's workers are for whoever manages them, not for everyone who works there (PPL-4). Their rows belong to
    # no side, so there is no side to keep the list to: the key is asked on the whole shop, as for adding a side.
    with shop_context(shop_a):
        note = Note.objects.create(shop=shop_a, text="Juma")
    one = f"{MANAGED_NOTES}{note.pk}/"
    juma = client_for(staff_a)

    # Juma sells on Dawa: he sees the side, but holds no key to these rows. Refused, the list and the one row alike.
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    for address in (MANAGED_NOTES, one):
        refused = juma.get(address)
        assert refused.status_code == 403, address
        assert refused.json()["code"] == "permission_denied"

    # The key on Dawa alone is not the whole shop's: still refused.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.STAFF_MANAGE, side=sides["D"], by=None)
    assert juma.get(MANAGED_NOTES).status_code == 403
    assert juma.get(one).status_code == 403

    # The key on every side: shown.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.STAFF_MANAGE, side=None, by=None)
    shown = juma.get(MANAGED_NOTES)
    assert shown.status_code == 200
    assert [row["text"] for row in shown.json()["results"]] == ["Juma"]
    assert juma.get(one).json()["text"] == "Juma"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "address"),
    [
        pytest.param("put", "list", id="PUT on the list"),
        pytest.param("delete", "list", id="DELETE on the list"),
        pytest.param("put", "row", id="PUT on a side"),
        pytest.param("delete", "row", id="DELETE on a side"),
        # OPTIONS would describe the route, its forms included, even to a person who may do none of its actions.
        pytest.param("options", "list", id="OPTIONS"),
    ],
)
def test_methods_a_route_does_not_answer_get_405(
    method: str, address: str, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # The side routes answer GET, POST and PATCH. Any other method is "not allowed", as DRF answers it, never a server
    # error: a method no route answers is a visitor's mistake, not a bug, and must not fill the error logs. The owner
    # holds every key, so only the method is refused, and the side stays as it was.
    give_role(staff_a, RoleTemplate.OWNER, None)
    url = SIDES if address == "list" else f"{SIDES}{sides['D'].pk}/"

    response = getattr(client_for(staff_a), method)(url)

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
    assert "OPTIONS" not in response["Allow"]
    assert side_name(sides["D"].shop, sides["D"]) == "Dawa"


@pytest.mark.django_db
def test_change_with_no_key_of_its_own_refused(
    monkeypatch: pytest.MonkeyPatch, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # Renaming a side named as needing only to see it: a Worker who sees Dawa could rename it. A route written that
    # way is a bug, refused before anything changes, even for the owner.
    monkeypatch.setattr(
        SideViewSet, "action_permissions", {**SideViewSet.action_permissions, "partial_update": base.SEES_THE_SIDE}
    )
    give_role(staff_a, RoleTemplate.OWNER, None)

    with pytest.raises(ImproperlyConfigured, match="partial_update changes rows"):
        client_for(staff_a).patch(f"{SIDES}{sides['D'].pk}/", {"name": "Dawa za Kuku", "version": 1})
    assert side_name(sides["D"].shop, sides["D"]) == "Dawa"


# --- Read once per visit


def permission_reads(visit: Callable[[], Any]) -> tuple[int, int]:
    # How many queries a visit sends to the two tables a person's keys live in, and how many it sends in all.
    with CaptureQueriesContext(connection) as seen:
        visit()
    sql = [query["sql"] for query in seen.captured_queries]
    keys = sum('"people_roleassignment"' in text or '"people_permissiongrant"' in text for text in sql)
    return keys, len(sql)


@pytest.mark.django_db
def test_permissions_read_once_per_visit(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A seller given a role on each side one at a time, the most rows a person's keys can take. Her list reads her
    # keys once, roles and grants one query each, and costs the same with five sides as with two: a busier shop is no
    # slower (Jack, PPL-5).
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a, RoleTemplate.SELLER, sides["F"])
    asha = client_for(staff_a)
    keys, two_sides = permission_reads(lambda: asha.get(SIDES))
    assert keys == 2

    with shop_context(shop_a):
        more = [add_side(shop=shop_a, code=code, name=f"Upande {code}", by=None) for code in "GHJ"]
    for side in more:
        give_role(staff_a, RoleTemplate.SELLER, side)
    keys, five_sides = permission_reads(lambda: asha.get(SIDES))
    assert keys == 2
    assert five_sides == two_sides

    # An edit asks twice, once to find the row and once to change it: still one read of the keys.
    give_role(staff_a, RoleTemplate.OWNER, None)
    owner = client_for(staff_a)
    keys, _ = permission_reads(lambda: owner.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Dawa za Kuku", "version": 1}))
    assert keys == 2


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_a_create_sent_again_asks_the_key_to_read_its_row(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # PPL-4's review: a create that finds its id already stored answers with the stored row. On a route whose rows are
    # read behind a key of their own, that answer is a read too: a seller who sends a worker's id must not get the
    # worker back, when the list and the one row both refuse her. The create's own key is still not asked again.
    with shop_context(shop_a):
        note = Note.objects.create(shop=shop_a, text="Mshahara wa Juma")
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])

    refused = client_for(staff_a).post("/api/v1/test/managed-note-makers/", {"id": str(note.pk), "text": "x"})

    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    assert "Mshahara" not in refused.content.decode()

    # Whoever may read it gets it back, as any lost answer is.
    give_role(staff_a2, RoleTemplate.OWNER, None)
    again = client_for(staff_a2).post("/api/v1/test/managed-note-makers/", {"id": str(note.pk), "text": "x"})
    assert (again.status_code, again.json()["text"]) == (201, "Mshahara wa Juma")


@pytest.mark.django_db
def test_pay_rates_need_settings_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # A worker's pay is the owner's business (WAGE-1): `settings.manage`, the key to the shop's rules and rates, on the
    # whole shop. A Manager on every side, who fixes attendance and prepares the pay, neither reads Juma's rates nor
    # sets one, and nothing is written. The owner does both.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        juma = add_staff(
            shop=shop_a, user=User.objects.create_user(full_name="Juma Demo"), display_name="Juma", by=None
        )

    def new() -> dict[str, object]:
        return {
            "id": str(uuid.uuid7()),
            "staff": str(juma.pk),
            "daily_rate": "10000",
            "shares_meals": True,
            "effective_from": juma.started_on.isoformat(),
        }

    manager = client_for(staff_a2)
    for refused in (manager.get(PAY_RATES, {"staff": str(juma.pk)}), manager.post(PAY_RATES, new(), format="json")):
        assert refused.status_code == 403
        assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert not PayRate.objects.exists()

    give_role(staff_a, RoleTemplate.OWNER, None)
    owner = client_for(staff_a)
    assert owner.post(PAY_RATES, new(), format="json").status_code == 201
    assert len(owner.get(PAY_RATES, {"staff": str(juma.pk)}).json()["rates"]) == 1


@pytest.mark.django_db
def test_a_key_on_one_side_sees_and_sets_no_rate(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # Hamisi may change the shop's rules on Dawa only (X1), and manage its workers: a worker's pay is the whole shop's,
    # so he reads and sets no rate. Nothing is written.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.SETTINGS_MANAGE, side=sides["D"], by=None)
        grant_permission(staff_a, Permission.STAFF_MANAGE, side=None, by=None)
        juma = add_staff(
            shop=shop_a, user=User.objects.create_user(full_name="Juma Demo"), display_name="Juma", by=None
        )
    hamisi = client_for(staff_a)
    sent = {
        "id": str(uuid.uuid7()),
        "staff": str(juma.pk),
        "daily_rate": "10000",
        "shares_meals": True,
        "effective_from": juma.started_on.isoformat(),
    }
    for refused in (hamisi.get(PAY_RATES, {"staff": str(juma.pk)}), hamisi.post(PAY_RATES, sent, format="json")):
        assert refused.status_code == 403
        assert refused.json()["code"] == "permission_denied"
    with shop_context(shop_a):
        assert not PayRate.objects.exists()


@pytest.mark.django_db
def test_seeing_pay_needs_the_workers_key_too(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Baba hands Meneja settings.manage to change the late fine, and nothing else (Jack, WAGE-1's review: A): Meneja
    # reads nobody's pay, sets none, and a rate's id sent again as a new one hands nothing back. Whoever may see a
    # worker's pay holds the same two keys as whoever may change it.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    give_role(staff_a, RoleTemplate.OWNER, None)
    with shop_context(shop_a):
        grant_permission(staff_a2, Permission.SETTINGS_MANAGE, side=None, by=None)
        juma = add_staff(
            shop=shop_a, user=User.objects.create_user(full_name="Juma Demo"), display_name="Juma", by=None
        )
    sent = {
        "id": str(uuid.uuid7()),
        "staff": str(juma.pk),
        "daily_rate": "13579",
        "shares_meals": True,
        "effective_from": juma.started_on.isoformat(),
    }
    assert client_for(staff_a).post(PAY_RATES, sent, format="json").status_code == 201

    meneja = client_for(staff_a2)
    new_one = {**sent, "id": str(uuid.uuid7())}
    for refused in (
        meneja.get(PAY_RATES, {"staff": str(juma.pk)}),
        meneja.post(PAY_RATES, new_one, format="json"),
        meneja.post(PAY_RATES, sent, format="json"),
    ):
        assert refused.status_code == 403
        assert refused.json()["code"] == "permission_denied"
        assert "13579" not in refused.content.decode()
    with shop_context(shop_a):
        assert PayRate.objects.count() == 1


def test_pay_rate_routes_name_their_permissions() -> None:
    # Reading a worker's rates and setting one both need `settings.manage` (WAGE-1). Written out in full, as above.
    assert PayRateViewSet.action_permissions == {
        "list": Permission.SETTINGS_MANAGE,
        "create": Permission.SETTINGS_MANAGE,
    }


@pytest.mark.django_db
def test_the_months_pay_needs_both_keys_of_pay(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # What the month pays shows each worker's daily rate ("14 × 10,000"), so it asks the rates' own two keys (Jack,
    # WAGE-1's review: A): a Manager on every side, who holds `pay.run` and fixes attendance, sees nobody's pay, not
    # their own either; nor handed one of the two keys, the rules' or the workers'. With both, as the owner holds them,
    # everyone's and one worker's.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    manager = client_for(staff_a2)
    addresses = (PAY, PAY_WORKER.format(staff_a.pk), PAY_WORKER.format(staff_a2.pk))

    def refused() -> None:
        for address in addresses:
            reply = manager.get(address, {"month": "2026-10"})
            assert reply.status_code == 403
            assert reply.json()["code"] == "permission_denied"

    refused()
    with shop_context(shop_a):
        rules = grant_permission(staff_a2, Permission.SETTINGS_MANAGE, side=None, by=None)
    refused()
    with shop_context(shop_a):
        grant_permission(staff_a2, Permission.STAFF_MANAGE, side=None, by=None)
    for address in addresses:
        assert manager.get(address, {"month": "2026-10"}).status_code == 200
    with shop_context(shop_a):
        end_permission(rules, by=None, reason="Hapaswi")
    refused()


@pytest.mark.django_db
def test_a_key_on_one_side_sees_no_pay(shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember) -> None:
    # Hamisi holds the two keys on Dawa only (X1): a worker's pay is the whole shop's, so he sees none, whichever of the
    # two is the side's.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.SETTINGS_MANAGE, side=sides["D"], by=None)
        grant_permission(staff_a, Permission.STAFF_MANAGE, side=sides["D"], by=None)
    hamisi = client_for(staff_a)
    for address in (PAY, PAY_WORKER.format(staff_a.pk)):
        assert hamisi.get(address, {"month": "2026-10"}).status_code == 403
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.SETTINGS_MANAGE, side=None, by=None)
    for address in (PAY, PAY_WORKER.format(staff_a.pk)):
        assert hamisi.get(address, {"month": "2026-10"}).status_code == 403


# The keys an approval asks, all three on the whole shop (WAGE-3): its own, and the two of pay.
APPROVING = (Permission.PAY_APPROVE, Permission.SETTINGS_MANAGE, Permission.STAFF_MANAGE)


@pytest.mark.django_db
@pytest.mark.parametrize("missing", APPROVING)
def test_approving_needs_all_three_keys(
    shop_a: Shop,
    sides: dict[str, Side],
    staff_a: StaffMember,
    staff_a2: StaffMember,
    give_role: GiveRole,
    missing: Permission,
) -> None:
    # A Manager holds none of the three; handed two, he still approves nothing, a month or one worker alone, whichever
    # is missing: nor is he handed back an approval somebody else made, by sending its id as a new one's
    # (CreateOnceMixin).
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    month = date(2026, 10, 1)
    with shop_context(shop_a):
        run = PayRun(shop=shop_a, month=month, created_by=staff_a)
        run.save()
        slip = Payslip(shop=shop_a, staff=staff_a, month=month, total=Decimal("12345.00"), created_by=staff_a)
        slip.save()
        for key in APPROVING:
            if key != missing:
                grant_permission(staff_a2, key, side=None, by=None)
    sent = {"month": "2026-10", "seen": []}
    alone = {"staff": str(staff_a.pk), "month": "2026-10", "seen": "12345.00"}

    def asked() -> list[Any]:
        client = client_for(staff_a2)
        return [
            client.post(PAY_RUNS, sent | {"id": str(uuid.uuid7())}, format="json"),
            client.post(PAY_RUNS, sent | {"id": str(run.pk)}, format="json"),
            client.post(PAYSLIPS, alone | {"id": str(uuid.uuid7())}, format="json"),
            client.post(PAYSLIPS, alone | {"id": str(slip.pk)}, format="json"),
        ]

    for refused in asked():
        assert (refused.status_code, refused.json()["code"]) == (403, "permission_denied")
        assert "12345" not in refused.content.decode()
    # On one side, the missing key is no key: a worker's pay is the whole shop's.
    with shop_context(shop_a):
        grant_permission(staff_a2, missing, side=sides["D"], by=None)
    assert {refused.status_code for refused in asked()} == {403}
    # With all three, what was approved is handed back, and a new one is refused by the service, not by the key.
    with shop_context(shop_a):
        grant_permission(staff_a2, missing, side=None, by=None)
    assert [answer.status_code for answer in asked()] == [400, 201, 400, 201]


def test_approval_routes_name_their_permissions() -> None:
    # Only a create, behind the approval's own key; the two of pay are asked for every action (the test above). And a
    # payslip's Lipa (WAGE-9), by number and in cash, behind `pay.run`, the key of handing out, never the approval's;
    # crossing a payment out too. Written out in full, as above.
    assert PayRunViewSet.action_permissions == {"create": Permission.PAY_APPROVE}
    assert PayslipViewSet.action_permissions == {
        "create": Permission.PAY_APPROVE,
        "pay": Permission.PAY_RUN,
        "pay_cash": Permission.PAY_RUN,
    }
    assert PayslipPaymentViewSet.action_permissions == {"void": Permission.PAY_RUN}


@pytest.mark.django_db
@pytest.mark.parametrize("missing", APPROVING)
def test_correcting_needs_all_three_keys(
    shop_a: Shop,
    sides: dict[str, Side],
    staff_a: StaffMember,
    staff_a2: StaffMember,
    give_role: GiveRole,
    missing: Permission,
) -> None:
    # Only whoever approves pay types or crosses out a correction (WAGE-10, Jack: A): a Manager, who types advances,
    # handed two of the three keys, types none and crosses out none, whichever is missing; nor is he handed back one
    # somebody else typed, by sending its id as a new one's (CreateOnceMixin).
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    with shop_context(shop_a):
        month = shop_today(shop_a).replace(day=1)
        juma = job(shop_a, "Juma")
        PayRate(shop=shop_a, staff=juma, daily_rate=Decimal("10000.00"), effective_from=juma.started_on).save()
        row = PayCorrection(
            shop=shop_a, staff=juma, month=month, amount=Decimal("12345.00"), reason="Kosa", created_by=staff_a
        )
        row.save()
        for key in APPROVING:
            if key != missing:
                grant_permission(staff_a2, key, side=None, by=None)
    sheet = {"staff": str(juma.pk), "month": f"{month:%Y-%m}", "amount": "9000.00", "reason": "Kosa"}

    def asked() -> list[Any]:
        client = client_for(staff_a2)
        return [
            client.post(PAY_CORRECTIONS, sheet | {"id": str(uuid.uuid7())}, format="json"),
            client.post(PAY_CORRECTIONS, sheet | {"id": str(row.pk)}, format="json"),
            client.post(f"{PAY_CORRECTIONS}{row.pk}/void/", {"reason": "Kosa"}, format="json"),
        ]

    for refused in asked():
        assert (refused.status_code, refused.json()["code"]) == (403, "permission_denied")
        assert "12345" not in refused.content.decode()
    # On one side, the missing key is no key: a worker's pay is the whole shop's.
    with shop_context(shop_a):
        grant_permission(staff_a2, missing, side=sides["D"], by=None)
    assert {refused.status_code for refused in asked()} == {403}
    # With all three: a new one typed, the one somebody typed handed back, and crossed out.
    with shop_context(shop_a):
        grant_permission(staff_a2, missing, side=None, by=None)
    assert [answer.status_code for answer in asked()] == [201, 201, 200]


def test_correction_route_names_its_permissions() -> None:
    # Typing one and crossing one out, both behind the approval's own key; the two of pay are asked for every action
    # (the test above). Written out in full, as above.
    assert PayCorrectionViewSet.action_permissions == {
        "create": Permission.PAY_APPROVE,
        "void": Permission.PAY_APPROVE,
    }


def test_pay_route_names_its_permissions() -> None:
    # Everyone's pay and one worker's, both reads, both behind `settings.manage`, the first of the two keys of pay; the
    # second, staff.manage, is asked for every action (the two tests above). Written out in full, as above.
    assert PayViewSet.action_permissions == {
        "list": Permission.SETTINGS_MANAGE,
        "retrieve": Permission.SETTINGS_MANAGE,
    }


@pytest.mark.django_db
def test_the_attendance_month_needs_attendance_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # The month page is for whoever fixes attendance (ATT-5): `attendance.manage`, which the Owner and the Manager
    # hold. Asha, a seller on Dawa, sees nobody's month, her own included; a Manager on every side opens it.
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    refused = client_for(staff_a).get(ATTENDANCE_MONTH, {"month": "2026-10"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    assert client_for(staff_a2).get(ATTENDANCE_MONTH, {"month": "2026-10"}).status_code == 200


@pytest.mark.django_db
def test_a_key_on_one_side_opens_no_month(shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember) -> None:
    # Hamisi may fix attendance on Dawa only (X1): attendance is the whole shop's, as Asha of Dawa and Baraka of
    # Vyakula are on one list, so a key on one side opens no month.
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.ATTENDANCE_MANAGE, side=sides["D"], by=None)
    refused = client_for(staff_a).get(ATTENDANCE_MONTH, {"month": "2026-10"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"


def test_attendance_month_route_names_its_permission() -> None:
    # The month page's one action, a read, behind the key to fix attendance (ATT-5). Written out in full, as above.
    assert AttendanceMonthViewSet.action_permissions == {"list": Permission.ATTENDANCE_MANAGE}


@pytest.mark.django_db
def test_a_workers_month_needs_attendance_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # A worker's month (ATT-12) is behind the month page's key: Asha, a seller on Dawa, may not open anyone's, her own
    # included, even with the address typed in; a Manager on every side opens hers.
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    address = ATTENDANCE_WORKER.format(staff_a.pk)
    refused = client_for(staff_a).get(address, {"month": "2026-10"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    assert client_for(staff_a2).get(address, {"month": "2026-10"}).status_code == 200


@pytest.mark.django_db
def test_a_key_on_one_side_opens_no_workers_month(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Hamisi may fix attendance on Dawa only (X1): attendance is the whole shop's, so a key on one side opens no
    # worker's month, as it opens no month (ATT-5).
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.ATTENDANCE_MANAGE, side=sides["D"], by=None)
    refused = client_for(staff_a).get(ATTENDANCE_WORKER.format(staff_a2.pk), {"month": "2026-10"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"


def test_attendance_worker_route_names_its_permission() -> None:
    # A worker's month's one action, a read, behind the key to fix attendance, as the month's (ATT-12). Written out in
    # full, as above.
    assert AttendanceWorkerViewSet.action_permissions == {"retrieve": Permission.ATTENDANCE_MANAGE}


@pytest.mark.django_db
def test_deciding_a_day_needs_attendance_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Deciding a day (ATT-6) is for whoever fixes attendance: Asha, a seller on Dawa, may not decide anyone's, even
    # with the address typed in; a Manager on every side decides Juma's. His Monday, in at 07:50 with no Toka, waits,
    # made the way the shop makes one: a tap on the shop's laptop, then the book (apps/staffpay/tests/days.py). The
    # laptop is made here, on this file's Dawa, as device_a would make a Dawa of its own beside it.
    with shop_context(shop_a):
        Device.objects.create(shop=shop_a, home_side=sides["D"], name="Laptop ya Dawa", code=1, key_hash="a" * 64)
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    switch_on(shop_a)
    day = kept_day(job(shop_a, "Juma"))
    sent = {"choice": "on_time", "reason": "Alisahau kubonyeza Toka", "replaces": None}
    refused = client_for(staff_a).post(ATTENDANCE_DAY_DECIDE.format(day.pk), sent, format="json")
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    decided = client_for(staff_a2).post(ATTENDANCE_DAY_DECIDE.format(day.pk), sent, format="json")
    assert decided.status_code == 200


def test_attendance_day_route_names_its_permission() -> None:
    # Deciding a day's one action, a change, behind the key to fix attendance (ATT-6), as the month's read is. Written
    # out in full, as above.
    assert AttendanceDayViewSet.action_permissions == {"decide": Permission.ATTENDANCE_MANAGE}


@pytest.mark.django_db
def test_fixing_taps_needs_attendance_manage(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Fixing a tap (ATT-13) is for whoever fixes attendance: Asha, a seller on Dawa, may neither add a tap nor cross one
    # out, even with the address typed in; a Manager on every side does both, on Juma's Monday: in at 07:50 on the
    # shop's laptop, made the way the shop makes one (apps/staffpay/tests/days.py), on this file's Dawa.
    with shop_context(shop_a):
        Device.objects.create(shop=shop_a, home_side=sides["D"], name="Laptop ya Dawa", code=1, key_hash="a" * 64)
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    switch_on(shop_a)
    juma = job(shop_a, "Juma")
    kept_day(juma)
    with shop_context(shop_a):
        ingia = AttendanceEvent.objects.get(staff=juma)
    added = {
        "id": str(uuid.uuid7()),
        "staff": str(juma.pk),
        "kind": "out",
        "date": "2026-11-16",
        "time": "18:45",
        "reason": "Alisahau kubonyeza Toka",
    }
    crossed = {"reason": "Alibonyeza kwa makosa"}
    for refused in (
        client_for(staff_a).post(ATTENDANCE_TAPS, added, format="json"),
        client_for(staff_a).post(ATTENDANCE_TAP_VOID.format(ingia.pk), crossed, format="json"),
    ):
        assert refused.status_code == 403
        assert refused.json()["code"] == "permission_denied"
    assert client_for(staff_a2).post(ATTENDANCE_TAPS, added, format="json").status_code == 201
    assert client_for(staff_a2).post(ATTENDANCE_TAP_VOID.format(ingia.pk), crossed, format="json").status_code == 200


def test_attendance_tap_route_names_its_permission() -> None:
    # Fixing a tap's two actions, both changes, behind the key to fix attendance (ATT-13), as deciding a day is. Written
    # out in full, as above.
    assert AttendanceTapViewSet.action_permissions == {
        "create": Permission.ATTENDANCE_MANAGE,
        "void": Permission.ATTENDANCE_MANAGE,
    }


@pytest.mark.django_db
def test_meal_money_needs_meals_record(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # The day's meal money (WAGE-7) is for whoever the owner gave the key to (Jack, 15 Nov 2026): a Manager on every
    # side may neither see it, type it nor cross it out, even with the address typed in, until he is given it; nor may
    # Asha, a seller, with the key on Dawa alone, as the meals are the whole shop's.
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    switch_on(shop_a)
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.MEALS_RECORD, side=sides["D"], by=None)
        row = MealMoney(shop=shop_a, date=date(2026, 11, 16), amount=Decimal("9000.00"), created_by=staff_a)
        row.save()
    typed = {"id": str(uuid.uuid7()), "date": "2026-11-16", "amount": "5000.00", "note": ""}
    crossed = {"reason": "Sifuri moja zaidi"}
    november = {"first": "2026-11-01", "last": "2026-11-30"}
    for person in (staff_a, staff_a2):
        for refused in (
            client_for(person).get(MEAL_MONEY, november),
            client_for(person).post(MEAL_MONEY, typed, format="json"),
            # A create sent again hands back the row it made: with the id of one, nothing comes back (CreateOnceMixin).
            client_for(person).post(MEAL_MONEY, {**typed, "id": str(row.pk)}, format="json"),
            client_for(person).post(MEAL_MONEY_VOID.format(row.pk), crossed, format="json"),
        ):
            assert refused.status_code == 403
            assert refused.json()["code"] == "permission_denied"
            assert "9000" not in refused.content.decode()
    with shop_context(shop_a):
        grant_permission(staff_a2, Permission.MEALS_RECORD, side=None, by=None)
    assert client_for(staff_a2).get(MEAL_MONEY, november).status_code == 200
    assert client_for(staff_a2).post(MEAL_MONEY, typed, format="json").status_code == 201
    assert client_for(staff_a2).post(MEAL_MONEY_VOID.format(row.pk), crossed, format="json").status_code == 200


def test_meal_money_route_names_its_permission() -> None:
    # Its three actions, the list too, behind the one key (WAGE-7): what the shop spends on meals, and who eats them, is
    # nobody's to see by only working there. Written out in full, as above.
    assert MealMoneyViewSet.action_permissions == {
        "list": Permission.MEALS_RECORD,
        "create": Permission.MEALS_RECORD,
        "void": Permission.MEALS_RECORD,
    }


@pytest.mark.django_db
def test_advances_need_money_advance(
    shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, staff_a2: StaffMember, give_role: GiveRole
) -> None:
    # Money given before payday (WAGE-8) is for the owner and the managers of the whole shop (Jack: A): Asha, a seller,
    # may neither see, type nor cross out one, even with the address typed in; nor may she with the key on Dawa alone,
    # as a worker's pay is the whole shop's. A manager may, with none of the two keys of pay.
    give_role(staff_a, RoleTemplate.SELLER, sides["D"])
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    juma = job(shop_a, "Juma")
    with shop_context(shop_a):
        PayRate(shop=shop_a, staff=juma, daily_rate=Decimal("10000.00"), effective_from=date(2026, 1, 1)).save()
        row = Advance(shop=shop_a, staff=juma, date=date(2026, 11, 16), amount=Decimal("9000.00"), created_by=staff_a2)
        row.save()
    typed = {"id": str(uuid.uuid7()), "staff": str(juma.pk), "date": "2026-11-16", "amount": "5000.00", "note": ""}
    crossed = {"reason": "Sifuri moja zaidi"}
    november = {"month": "2026-11"}

    def asked(person: StaffMember) -> list[Any]:
        return [
            client_for(person).get(ADVANCES, november),
            client_for(person).get(ADVANCE.format(row.pk)),
            client_for(person).post(ADVANCES, typed, format="json"),
            # A create sent again hands back the row it made: with the id of one, nothing comes back (CreateOnceMixin).
            client_for(person).post(ADVANCES, {**typed, "id": str(row.pk)}, format="json"),
            client_for(person).post(ADVANCE_VOID.format(row.pk), crossed, format="json"),
        ]

    for give_the_key in (False, True):
        if give_the_key:
            with shop_context(shop_a):
                grant_permission(staff_a, Permission.MONEY_ADVANCE, side=sides["D"], by=None)
        for refused in asked(staff_a):
            assert (refused.status_code, refused.json()["code"]) == (403, "permission_denied")
            assert "9000" not in refused.content.decode()
    assert [answer.status_code for answer in asked(staff_a2)] == [200, 200, 201, 201, 200]
    assert client_for(staff_a2).get(PAY, november).status_code == 403


def test_advances_route_names_its_permission() -> None:
    # Its four actions, the reads too, behind the one key (WAGE-8): what a worker took is nobody's to see by only
    # working there. Written out in full, as above.
    assert AdvanceViewSet.action_permissions == {
        "list": Permission.MONEY_ADVANCE,
        "retrieve": Permission.MONEY_ADVANCE,
        "create": Permission.MONEY_ADVANCE,
        "void": Permission.MONEY_ADVANCE,
    }
