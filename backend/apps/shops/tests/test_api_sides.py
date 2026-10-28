"""apps/shops/tests/test_api_sides.py — the sides routes, /api/v1/shops/sides/ (03 §5.10), and through them
the conventions every office route follows (apps/core/api/, CORE-6).

    shop      sides                    who asks
    MFANO     Dawa (D), Vyakula (F)    staff_client_a: a staff member of MFANO
    JINGINE   Dawa (D)                 nobody: another shop, whose rows MFANO must never see

Each visit works for the one shop its login names, and sees that shop's rows only (ADR-0022). The logins
themselves come with AUTH-2, AUTH-3 and AUTH-4: here the client from backend/conftest.py skips them and puts
the staff member straight into `request.auth`, as those logins will. The staff member is typed Any:
`shops` may not name `people`'s StaffMember, not even in its tests (ADR-0035).
"""

import uuid
from typing import Any

import pytest
from django.db import IntegrityError
from django.test import Client
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.test import APIClient

from apps.core.api.base import CreateOnceMixin
from apps.core.api.pagination import CursorPage
from apps.core.tenancy import NoShopSelected, current_shop, shop_context
from apps.shops.api.views import SideViewSet
from apps.shops.models import PaymentAccountSide, Shop, Side, StockLocation

pytestmark = pytest.mark.django_db

SIDES = "/api/v1/shops/sides/"


def new_side() -> dict[str, str]:
    # A third side, as the app sends it: with the id the app made itself (ADR-0007).
    return {"id": str(uuid.uuid7()), "code": "P", "name": "Pembejeo"}


@pytest.fixture
def sides_a(shop_a: Shop) -> dict[str, Side]:
    # Fake data only: the repo is public (03 §10).
    with shop_context(shop_a):
        return {
            "D": Side.objects.create(shop=shop_a, code="D", name="Dawa"),
            "F": Side.objects.create(shop=shop_a, code="F", name="Vyakula"),
        }


@pytest.fixture
def side_b(shop_b: Shop) -> Side:
    with shop_context(shop_b):
        return Side.objects.create(shop=shop_b, code="D", name="Dawa")


def test_side_list_shows_only_the_current_shops_sides(
    staff_client_a: APIClient, sides_a: dict[str, Side], side_b: Side
) -> None:
    response = staff_client_a.get(SIDES)

    assert response.status_code == 200
    # Shop B's Dawa sits in the same table, and never shows: the guard filters every read by the visit's shop.
    assert {row["id"] for row in response.json()["results"]} == {str(side.pk) for side in sides_a.values()}


def test_another_shops_side_is_not_found(staff_client_a: APIClient, side_b: Side) -> None:
    # 404, not 403: "forbidden" would tell shop A that the row exists. To shop A's visit, shop B's rows
    # don't exist at all (03 §5.4).
    response = staff_client_a.get(f"{SIDES}{side_b.pk}/")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_side_routes_need_a_shop_login(superuser_client: Client, sides_a: dict[str, Side]) -> None:
    # Nobody logged in: refused before any table is read.
    anonymous = APIClient().get(SIDES)
    assert anonymous.status_code == 403
    assert anonymous.json()["code"] == "not_authenticated"

    # The superuser's admin login is a real login, but it names no shop: the superuser is nobody's staff.
    # Request code never reads across shops (03 §5.4), so this visit is refused too.
    admin = superuser_client.get(SIDES)
    assert admin.status_code == 403
    assert admin.json()["code"] == "not_authenticated"


def test_shop_closed_after_the_visit(staff_client_a: APIClient, sides_a: dict[str, Side]) -> None:
    # The test client runs each visit in this very thread, as a server worker does. One visit that goes
    # well, one that ends in a refusal (an id that is no side):
    staff_client_a.get(SIDES)
    staff_client_a.get(f"{SIDES}{uuid.uuid7()}/")

    # Both are over, so no shop is open: the next visit on this worker must not inherit this one's shop.
    with pytest.raises(NoShopSelected):
        current_shop()


def test_side_list_is_paged_with_a_cursor(
    staff_client_a: APIClient, shop_a: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 50 rows a page in the app; 2 here, so three sides make two pages.
    monkeypatch.setattr(CursorPage, "page_size", 2)
    with shop_context(shop_a):
        for code in "DFG":
            Side.objects.create(shop=shop_a, code=code, name=f"Upande {code}")

    first = staff_client_a.get(SIDES).json()
    # Newest first, by the server's clock. `next` is the address of the next page, with its cursor.
    assert [row["code"] for row in first["results"]] == ["G", "F"]
    second = staff_client_a.get(first["next"]).json()
    assert [row["code"] for row in second["results"]] == ["D"]
    assert second["next"] is None


def test_side_permission_hook_checks_each_side(
    staff_client_a: APIClient, sides_a: dict[str, Side], monkeypatch: pytest.MonkeyPatch
) -> None:
    # PPL-3 fills the hook in with real permissions. Until then, a stand-in that refuses Vyakula (F)
    # proves that each row the route hands out, to read or to change, passes through the hook, with that
    # row's own side.
    vyakula = sides_a["F"].pk

    def only_dawa(view: SideViewSet, request: Request, side_id: uuid.UUID | None) -> None:
        if side_id == vyakula:
            raise exceptions.PermissionDenied

    monkeypatch.setattr(SideViewSet, "check_side_permission", only_dawa)

    assert staff_client_a.get(f"{SIDES}{sides_a['D'].pk}/").status_code == 200
    refused = staff_client_a.get(f"{SIDES}{vyakula}/")
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
    edit = staff_client_a.patch(f"{SIDES}{vyakula}/", {"name": "Chakula", "version": 1})
    assert edit.status_code == 403
    assert sides_a["F"].name == "Vyakula"


def test_create_twice_with_same_uuid_makes_one_row(staff_client_a: APIClient, shop_a: Shop) -> None:
    # A phone adds a side, and the answer is lost on the way back, so the phone sends the same request
    # again. The id it made makes the second send harmless: it gets the same side back, with the same 201,
    # as if the first answer had arrived.
    side = new_side()

    first = staff_client_a.post(SIDES, side)
    again = staff_client_a.post(SIDES, side)

    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    with shop_context(shop_a):
        assert Side.objects.filter(pk=side["id"]).count() == 1
        # And it came with its default stock location and its cash drawer, once each, as create_shop's
        # sides do (SHOP-2).
        assert StockLocation.objects.filter(side_id=side["id"]).count() == 1
        assert PaymentAccountSide.objects.filter(side_id=side["id"]).count() == 1


def _next_first_look_too_early(monkeypatch: pytest.MonkeyPatch) -> None:
    # Two copies of one request arrive together, and each looks for the id before the other has written.
    # Played here one after the other: the next copy's first look is made to find nothing, as it would have,
    # had it run before the first copy finished. Its later looks see the database as it is.
    real_stored = CreateOnceMixin._stored
    looks: list[object] = []

    def first_look_too_early(view: CreateOnceMixin[Side], row_id: object) -> Side | None:
        looks.append(row_id)
        return None if len(looks) == 1 else real_stored(view, row_id)

    monkeypatch.setattr(CreateOnceMixin, "_stored", first_look_too_early)


def test_two_copies_at_the_same_moment_make_one_row(
    staff_client_a: APIClient, shop_a: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first copy finishes while the second is still checking. The second copy's checks (full_clean) then
    # see the first one's side, and refuse: "letter P is taken". But it is the same side, made by the same
    # request: that copy looks again, finds it, and answers with it, as for any retry.
    side = new_side()
    first = staff_client_a.post(SIDES, side)
    _next_first_look_too_early(monkeypatch)

    again = staff_client_a.post(SIDES, side)

    assert again.status_code == 201
    assert again.json() == first.json()
    with shop_context(shop_a):
        assert Side.objects.filter(pk=side["id"]).count() == 1


def test_two_copies_clashing_at_the_insert_make_one_row(
    staff_client_a: APIClient, shop_a: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first copy finishes a moment later: after the second copy's checks, before its insert. Those
    # checks saw nothing, so the insert fails on the id. That copy looks again and answers with the first
    # one's side.
    side = new_side()
    first = staff_client_a.post(SIDES, side)
    _next_first_look_too_early(monkeypatch)
    # Its checks ran before the first copy had committed, so they found nothing either.
    monkeypatch.setattr(Side, "full_clean", lambda *args, **kwargs: None)

    again = staff_client_a.post(SIDES, side)

    assert again.status_code == 201
    assert again.json() == first.json()
    with shop_context(shop_a):
        assert Side.objects.filter(pk=side["id"]).count() == 1


def test_other_database_refusal_left_as_a_bug(staff_client_a: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only a taken id is the create's own to answer. Any other rule the database refuses is one the service
    # should have checked first: a bug, so it is not dressed up as a refusal, and Django logs it as a 500.
    def broken_service(view: SideViewSet, data: dict[str, object]) -> Side:
        raise IntegrityError("another rule")

    monkeypatch.setattr(SideViewSet, "create_row", broken_service)

    with pytest.raises(IntegrityError, match="another rule"):
        staff_client_a.post(SIDES, new_side())


def test_create_needs_the_client_uuid(staff_client_a: APIClient) -> None:
    # Without an id of its own, a phone's retry would look like a new side, and a lost answer would leave
    # the shop with two.
    response = staff_client_a.post(SIDES, {"code": "P", "name": "Pembejeo"})

    assert response.status_code == 400
    assert response.json()["fields"] == {"id": ["required"]}


def test_uuid_of_another_shop_refused_revealing_nothing(staff_client_a: APIClient, shop_a: Shop, side_b: Side) -> None:
    # Shop B's side already has this id. Shop A's visit can't see it, so the id looks free until the insert
    # fails on the primary key. That becomes a refusal of the id, and says nothing more: not the other
    # row's name, not its shop, not even that it is a side (03 §5.4).
    response = staff_client_a.post(SIDES, {**new_side(), "id": str(side_b.pk)})

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid",
        "message": "id: This id is already in use.",
        "fields": {"id": ["id.taken"]},
        "params": {},
    }
    # And nothing was made in shop A.
    with shop_context(shop_a):
        assert not Side.objects.exists()


def test_create_refused_by_a_rule_answers_its_code(staff_client_a: APIClient, sides_a: dict[str, Side]) -> None:
    # MFANO already has a side D. The service's check (full_clean) refuses a second one, and the app gets
    # the rule's own code, which it translates (ADR-0032).
    response = staff_client_a.post(SIDES, {**new_side(), "code": "D"})

    assert response.status_code == 400
    assert response.json()["code"] == "side.code_taken"


def test_create_passes_the_side_permission_hook(
    staff_client_a: APIClient, shop_a: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A new side belongs to no side yet: adding one is an action on the whole shop, so the hook is asked
    # with no side. A stand-in that refuses whole-shop actions shows the create is checked, and makes
    # nothing.
    def refuse_whole_shop(view: SideViewSet, request: Request, side_id: uuid.UUID | None) -> None:
        if side_id is None:
            raise exceptions.PermissionDenied

    monkeypatch.setattr(SideViewSet, "check_side_permission", refuse_whole_shop)

    response = staff_client_a.post(SIDES, new_side())

    assert response.status_code == 403
    with shop_context(shop_a):
        assert not Side.objects.exists()


def test_stale_version_gets_409(staff_client_a: APIClient, sides_a: dict[str, Side]) -> None:
    # The owner and a manager both open Dawa: each screen holds version 1. The owner saves first, so Dawa
    # moves to version 2. The manager's edit was made on the old copy: it is refused, instead of silently
    # undoing the owner's change, and the manager's app reloads Dawa (02 §1).
    dawa = f"{SIDES}{sides_a['D'].pk}/"

    owner = staff_client_a.patch(dawa, {"name": "Dawa za Mifugo", "version": 1})
    manager = staff_client_a.patch(dawa, {"name": "Dawa za Kuku", "version": 1})

    assert owner.status_code == 200
    assert owner.json()["version"] == 2
    assert manager.status_code == 409
    assert manager.json()["code"] == "version_conflict"
    # The owner's name stays.
    assert staff_client_a.get(dawa).json()["name"] == "Dawa za Mifugo"


def test_edit_bumps_the_version_and_records_who(
    staff_client_a: APIClient, staff_a: Any, shop_a: Shop, sides_a: dict[str, Side]
) -> None:
    # Made at version 1, with no edit yet: `updated_at` and `updated_by` stay empty until the first edit,
    # because the creation is already in `created_at` and `created_by`.
    assert sides_a["D"].version == 1
    assert sides_a["D"].updated_at is None

    staff_client_a.patch(f"{SIDES}{sides_a['D'].pk}/", {"name": "Dawa za Mifugo", "version": 1})

    with shop_context(shop_a):
        dawa = Side.objects.get(pk=sides_a["D"].pk)
    assert dawa.version == 2
    assert dawa.updated_by_id == staff_a.pk
    assert dawa.updated_at is not None


def test_edit_keeps_the_side_letter(staff_client_a: APIClient, sides_a: dict[str, Side]) -> None:
    # Only the name can be changed. The letter starts every number printed on the side's receipts (D7),
    # so a letter sent with an edit is ignored, and Dawa stays D.
    response = staff_client_a.patch(f"{SIDES}{sides_a['D'].pk}/", {"name": "Dawa za Mifugo", "code": "X", "version": 1})

    assert response.status_code == 200
    assert response.json()["code"] == "D"


def test_edit_needs_the_version_read(staff_client_a: APIClient, sides_a: dict[str, Side]) -> None:
    # Without the version it read, an edit can't be told apart from one made on an old copy.
    response = staff_client_a.patch(f"{SIDES}{sides_a['D'].pk}/", {"name": "Dawa za Mifugo"})

    assert response.status_code == 400
    assert response.json()["fields"] == {"version": ["required"]}
