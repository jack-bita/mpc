"""apps/shops/tests/test_api_sides.py — the sides routes, /api/v1/shops/sides/ (03 §5.10), and through them
the conventions every office route follows (apps/core/api/, CORE-6).

    shop      sides                    who asks
    MFANO     Dawa (D), Vyakula (F)    staff_client_a: a staff member of MFANO
    JINGINE   Dawa (D)                 nobody: another shop, whose rows MFANO must never see

Each visit works for the one shop its login names, and sees that shop's rows only (ADR-0022). The logins
themselves come with AUTH-2, AUTH-3 and AUTH-4: here the client from backend/conftest.py skips them and puts
the staff member straight into `request.auth`, as those logins will.
"""

import uuid

import pytest
from django.test import Client
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.test import APIClient

from apps.core.api.pagination import CursorPage
from apps.core.tenancy import NoShopSelected, current_shop, shop_context
from apps.shops.api.views import SideViewSet
from apps.shops.models import Shop, Side

pytestmark = pytest.mark.django_db

SIDES = "/api/v1/shops/sides/"


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
    # proves that each row the route hands out passes through the hook, with that row's own side.
    vyakula = sides_a["F"].pk

    def only_dawa(view: SideViewSet, request: Request, side_id: uuid.UUID | None) -> None:
        if side_id == vyakula:
            raise exceptions.PermissionDenied

    monkeypatch.setattr(SideViewSet, "check_side_permission", only_dawa)

    assert staff_client_a.get(f"{SIDES}{sides_a['D'].pk}/").status_code == 200
    refused = staff_client_a.get(f"{SIDES}{vyakula}/")
    assert refused.status_code == 403
    assert refused.json()["code"] == "permission_denied"
