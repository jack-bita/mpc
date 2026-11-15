"""apps/shops/tests/test_api_settings.py — the settings routes, /api/v1/shops/settings/ (SHOP-3, 03 §5.10).

    GET  settings/   the shop's today, and every rule in the registry, once per side for a side's rule, each with its
                     default, its value today and its rows, newest first (the settings page, SHOP-5)
    POST settings/   a rule's new value from a day on, through set_setting, with the id the client made (ADR-0007)

Who may do which is pinned in backend/tests/test_route_permissions.py, beside every other route's. Here the client from
backend/conftest.py holds every key. Fake data only: the repo is public.
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.core.settings_registry import KEYS, Scope
from apps.core.tenancy import shop_context
from apps.shops.models import Setting, Shop, Side
from apps.shops.selectors import shop_today
from apps.shops.services import add_side, set_setting

pytestmark = pytest.mark.django_db

SETTINGS = "/api/v1/shops/settings/"


@pytest.fixture
def sides(shop_a: Shop) -> dict[str, Side]:
    # MPC's two sides, made the way the app makes them (SHOP-2).
    with shop_context(shop_a):
        return {
            "D": add_side(shop=shop_a, code="D", name="Dawa", by=None),
            "F": add_side(shop=shop_a, code="F", name="Vyakula", by=None),
        }


def rule_of(answer: dict[str, Any], key: str, side: Side | None = None) -> dict[str, Any]:
    # The one item for this rule, and this side for a side's rule.
    side_id = None if side is None else str(side.pk)
    (rule,) = [rule for rule in answer["rules"] if rule["key"] == key and rule["side"] == side_id]
    return dict(rule)


def new_value(**sent: Any) -> dict[str, Any]:
    # A new value as the settings page sends it, with the id it made itself (ADR-0007).
    return {"id": str(uuid.uuid7()), "note": "", **sent}


def test_settings_list_shows_every_rule(
    staff_client_a: APIClient, staff_a: Any, shop_a: Shop, sides: dict[str, Side]
) -> None:
    # Every rule in the registry, in its order: a shop's rule once, a side's rule once for Dawa and once for Vyakula.
    # The owner set the late fine to 2,000 from tomorrow, so today it is still 1,000, and its rows show the 2,000
    # coming, with who set it, by the nickname the screens show.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        tomorrow = today + timedelta(days=1)
        set_setting(shop_a, key="attendance.late_fine", value="2000", effective_from=tomorrow, by=staff_a)

    answer = staff_client_a.get(SETTINGS).json()

    assert answer["today"] == today.isoformat()
    expected = [
        (key.key, side)
        for key in KEYS
        for side in ([None] if key.scope is Scope.SHOP else [str(sides["D"].pk), str(sides["F"].pk)])
    ]
    assert [(rule["key"], rule["side"]) for rule in answer["rules"]] == expected
    fine = rule_of(answer, "attendance.late_fine")
    assert (fine["kind"], fine["scope"], fine["default"], fine["value"]) == ("money", "shop", "1000.00", "1000.00")
    ((row,),) = [fine["rows"]]
    assert (row["value"], row["effective_from"], row["set_by"], row["side"]) == (
        "2000.00",
        (today + timedelta(days=1)).isoformat(),
        "Staff A",
        None,
    )


def test_settings_list_shows_a_sides_rule_per_side(
    staff_client_a: APIClient, shop_a: Shop, sides: dict[str, Side]
) -> None:
    # Dawa's cash tolerance is 500 from today; Vyakula keeps the default 0, and Dawa's row is not in its history. Two
    # rows for the same day, newest first: the second fixed a typo, and it is the one in force (T2).
    today = shop_today(shop_a)
    with shop_context(shop_a):
        set_setting(shop_a, key="cash.tolerance", value="5000", effective_from=today, side=sides["D"], by=None)
        set_setting(shop_a, key="cash.tolerance", value="500", effective_from=today, side=sides["D"], by=None)

    answer = staff_client_a.get(SETTINGS).json()

    dawa = rule_of(answer, "cash.tolerance", sides["D"])
    vyakula = rule_of(answer, "cash.tolerance", sides["F"])
    assert (dawa["value"], [row["value"] for row in dawa["rows"]]) == ("500.00", ["500.00", "5000.00"])
    assert (vyakula["value"], vyakula["rows"]) == ("0.00", [])
    # Nobody set it, so the row names no one: the system's, as a seed's would be.
    assert dawa["rows"][0]["set_by"] is None


def test_a_shop_row_of_a_sides_rule_shows_on_each_side(
    staff_client_a: APIClient, shop_a: Shop, sides: dict[str, Side]
) -> None:
    # set_setting never writes a whole-shop row for a side's rule (SHOP-3), but code that skips it could, as a seed
    # might: checked, then saved. get_setting still reads such a row behind a side's own (02 §4), so the page shows it
    # in each side's rows, marked as the shop's by its empty side, and never a value that no row explains. Dawa has its
    # own row too, which beats it; Vyakula has none, so the shop's row is Vyakula's value.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        shop_row = Setting(shop=shop_a, key="cash.tolerance", value="300", effective_from=today)
        shop_row.full_clean()
        shop_row.save()
        own = set_setting(shop_a, key="cash.tolerance", value="500", effective_from=today, side=sides["D"], by=None)

    answer = staff_client_a.get(SETTINGS).json()

    dawa = rule_of(answer, "cash.tolerance", sides["D"])
    vyakula = rule_of(answer, "cash.tolerance", sides["F"])
    assert (dawa["value"], [(row["id"], row["side"]) for row in dawa["rows"]]) == (
        "500.00",
        [(str(own.pk), str(sides["D"].pk)), (str(shop_row.pk), None)],
    )
    assert (vyakula["value"], [(row["id"], row["side"]) for row in vyakula["rows"]]) == (
        "300.00",
        [(str(shop_row.pk), None)],
    )


def test_settings_list_is_one_answer_not_pages(staff_client_a: APIClient, sides: dict[str, Side]) -> None:
    # The registry is a short list, so the answer is whole: no cursor to follow, as the side list has (CORE-6).
    answer = staff_client_a.get(SETTINGS).json()
    assert set(answer) == {"today", "rules"}


def test_create_setting_saves_and_answers_the_row(
    staff_client_a: APIClient, staff_a: Any, shop_a: Shop, sides: dict[str, Side]
) -> None:
    # The page sends Vyakula's cash tolerance from tomorrow. The answer is the row as saved, in its kind's one form;
    # sent again with the same id, as a phone does when the answer was lost, it gets the same row back, and no second
    # row.
    tomorrow = shop_today(shop_a) + timedelta(days=1)
    sent = new_value(key="cash.tolerance", side=str(sides["F"].pk), value="1000", effective_from=tomorrow.isoformat())

    first = staff_client_a.post(SETTINGS, sent, format="json")
    again = staff_client_a.post(SETTINGS, sent, format="json")

    assert (first.status_code, again.status_code) == (201, 201)
    assert first.json() == again.json()
    assert (first.json()["id"], first.json()["value"], first.json()["set_by"]) == (sent["id"], "1000.00", "Staff A")
    with shop_context(shop_a):
        assert Setting.objects.filter(shop=shop_a).count() == 1
        assert Setting.objects.get().created_by_id == staff_a.pk


def test_create_setting_refused_answers_its_codes(
    staff_client_a: APIClient, shop_a: Shop, sides: dict[str, Side]
) -> None:
    # Each mistake beside its box (ADR-0040): a day before today and a wrong value, together; a side's rule with no
    # side; and nothing written.
    yesterday = shop_today(shop_a) - timedelta(days=1)
    both = staff_client_a.post(
        SETTINGS,
        new_value(key="attendance.late_fine", value="elfu", effective_from=yesterday.isoformat()),
        format="json",
    )
    no_side = staff_client_a.post(
        SETTINGS,
        new_value(key="cash.tolerance", value="500", effective_from=shop_today(shop_a).isoformat()),
        format="json",
    )

    assert both.status_code == 400
    assert both.json()["fields"] == {"effective_from": ["setting.date_past"], "value": ["setting.value_invalid"]}
    assert no_side.status_code == 400
    assert no_side.json()["fields"] == {"side": ["setting.side_required"]}
    with shop_context(shop_a):
        assert not Setting.objects.filter(shop=shop_a).exists()


def test_create_setting_with_another_shops_side_is_not_found(
    staff_client_a: APIClient, shop_a: Shop, side_b: Side
) -> None:
    # T1: shop B's side is "not found", as if it didn't exist, so the answer says nothing about it (03 §5.4).
    sent = new_value(
        key="cash.tolerance", side=str(side_b.pk), value="500", effective_from=shop_today(shop_a).isoformat()
    )
    response = staff_client_a.post(SETTINGS, sent, format="json")

    assert response.status_code == 400
    assert response.json()["fields"] == {"side": ["does_not_exist"]}
