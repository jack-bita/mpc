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
- a show action needs only its side to be seen; one that names a key of its own (debts, reports) is refused until
  the card that first needs one builds it (Jack, PPL-5);
- a visit reads the person's permissions once, however many sides the shop has (Jack, PPL-5).

It lives outside `apps` because it needs both the side routes (`shops`) and the roles (`people`), and an app's own
tests may not import a higher layer (ADR-0035). Fake data only: the repo is public (03 §10).

    shop      sides                    who asks
    MFANO     Dawa (D), Vyakula (F)    staff_a and staff_a2, given roles test by test
"""

import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import include, path
from django.utils import timezone
from pytest_django import Settings
from rest_framework import mixins, serializers
from rest_framework.routers import SimpleRouter
from rest_framework.test import APIClient

from apps.core.api import base
from apps.core.api.base import ShopViewSet
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import StaffMember
from apps.people.services import grant_permission, mark_left, suspend
from apps.shops.api.views import SideViewSet
from apps.shops.models import Shop, Side
from apps.shops.services import add_side
from tests.probe.api import NoteSerializer
from tests.probe.models import Note
from tests.test_tenancy_sweep import addresses

SIDES = "/api/v1/shops/sides/"

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


router = SimpleRouter()
router.register("plain-note-makers", PlainNoteMakerViewSet, basename="plain-note-maker")
urlpatterns = [path("api/v1/test/", include(router.urls))]

PLAIN_MAKERS = "/api/v1/test/plain-note-makers/"


def client_for(staff: StaffMember) -> APIClient:
    # The way the office screens will call: logged in as this person, at their shop. The logins come later (AUTH-3,
    # AUTH-4); force_authenticate puts the person straight into `request.auth`, as they will (backend/conftest.py).
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
    # Adding or renaming a side changes the shop itself: `settings.manage`, one of the owner's own four (spec §6).
    # A Manager on every side sees both sides, and still may not.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    manager = client_for(staff_a2)

    rename = manager.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Dawa za Kuku", "version": 1})
    assert rename.status_code == 403
    assert rename.json()["code"] == "permission_denied"
    assert side_name(shop_a, sides["D"]) == "Dawa"

    add = manager.post(SIDES, new_side())
    assert add.status_code == 403
    with shop_context(shop_a):
        assert not Side.objects.filter(code="P").exists()

    # The owner holds it on every side, so both work.
    give_role(staff_a, RoleTemplate.OWNER, None)
    owner = client_for(staff_a)
    assert owner.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Dawa za Kuku", "version": 1}).status_code == 200
    assert owner.post(SIDES, new_side()).status_code == 201


def test_side_routes_name_their_permissions() -> None:
    # Showing a side needs only to see it; adding or renaming one needs `settings.manage` (spec §6). Written out in
    # full, so a change to what a route asks for is a change to this test too.
    assert SideViewSet.action_permissions == {
        "list": base.SEES_THE_SIDE,
        "retrieve": base.SEES_THE_SIDE,
        "create": Permission.SETTINGS_MANAGE,
        "partial_update": Permission.SETTINGS_MANAGE,
    }


# --- A person who may not work


def stop(how: str, staff: StaffMember) -> None:
    # Suspended for a while, or gone for good (02 §5): either way, they hold nothing.
    with shop_context(staff.shop_id):
        if how == "suspended":
            suspend(staff, by=None, reason="Uchunguzi wa upotevu")
        else:
            mark_left(staff, left_on=timezone.localdate(), by=None, reason="Amehama")


@pytest.mark.django_db
@pytest.mark.parametrize("how", ["suspended", "left"])
def test_suspended_member_gets_nothing_from_routes(
    how: str, shop_a: Shop, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # The owner's own login, after they stop working here. The client still holds the person as they were loaded,
    # "active": the check must read the status from the database on each visit, never trust that copy (X2).
    give_role(staff_a, RoleTemplate.OWNER, None)
    client = client_for(staff_a)
    stop(how, staff_a)

    assert client.get(SIDES).json()["results"] == []
    assert client.get(f"{SIDES}{sides['D'].pk}/").status_code == 404
    assert client.patch(f"{SIDES}{sides['D'].pk}/", {"name": "Imeibiwa", "version": 1}).status_code == 404
    assert client.post(SIDES, new_side()).status_code == 403
    assert side_name(shop_a, sides["D"]) == "Dawa"


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


# --- Every action is named


def permission_problems(routes: Iterable[tuple[type[ShopViewSet[Any]], Mapping[str, str]]]) -> list[str]:
    # What breaks the two rules every route's permission list keeps, for each route and the actions its address
    # answers with ({"get": "list", "post": "create"}, as DRF's router notes them):
    # - every action is named, so none is open by forgetting;
    # - a show action (GET) needs only to see its side, for now: one behind a key of its own waits for the card that
    #   first needs one (cost.view, debt.view, report.view), which decides how a list keeps to that key's sides.
    problems = []
    for view, actions in routes:
        named = getattr(view, "action_permissions", {})
        for method, action in sorted(actions.items()):
            if action not in named:
                problems.append(f"{view.__name__}: {action} names no permission")
            elif method in ("get", "head") and named[action] is not base.SEES_THE_SIDE:
                problems.append(f"{view.__name__}: {action} shows rows behind {named[action]}, not built yet")
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


def test_permission_check_finds_what_breaks_its_rules() -> None:
    # The check itself, handed routes built to break each rule once.
    class Named(ShopViewSet[Side]):
        model = Side
        action_permissions = {"list": base.SEES_THE_SIDE, "create": Permission.SETTINGS_MANAGE}

    class ShowsDebts(ShopViewSet[Side]):
        model = Side
        action_permissions = {"list": Permission.DEBT_VIEW}

    class Forgets(ShopViewSet[Side]):
        model = Side

    assert permission_problems(
        [
            (Named, {"get": "list", "post": "create"}),
            (ShowsDebts, {"get": "list"}),
            (Forgets, {"post": "void"}),
        ]
    ) == [
        "ShowsDebts: list shows rows behind debt.view, not built yet",
        "Forgets: void names no permission",
    ]


@pytest.mark.django_db
def test_unnamed_action_refused(
    monkeypatch: pytest.MonkeyPatch, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A route that forgets an action is a bug, not a person's mistake: it answers a server error, which is logged,
    # instead of a 403 that would hide the bug behind a plain "no", or a 200 that would open the action to all.
    # Even the owner, who holds every key, is refused.
    monkeypatch.setattr(SideViewSet, "action_permissions", {"retrieve": base.SEES_THE_SIDE}, raising=False)
    give_role(staff_a, RoleTemplate.OWNER, None)

    with pytest.raises(ImproperlyConfigured, match="list"):
        client_for(staff_a).get(SIDES)


@pytest.mark.django_db
def test_show_action_with_a_key_stopped_for_now(
    monkeypatch: pytest.MonkeyPatch, sides: dict[str, Side], staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A list behind a key of its own, as debts will be (`debt.view`): nothing yet keeps such a list to the sides
    # where the key is held, so it would show every side the person sees. Refused until a card builds that.
    monkeypatch.setattr(
        SideViewSet, "action_permissions", {**SideViewSet.action_permissions, "list": Permission.DEBT_VIEW}
    )
    give_role(staff_a, RoleTemplate.OWNER, None)

    with pytest.raises(ImproperlyConfigured, match="debt.view"):
        client_for(staff_a).get(SIDES)


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
