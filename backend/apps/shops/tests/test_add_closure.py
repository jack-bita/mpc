"""apps/shops/tests/test_add_closure.py — add_closure, how a person closes the shop for some days (ATT-8, 02 §12).

Baba adds "Msiba wa bibi" on the morning of the funeral, from today to four days on: saved. The service refuses, each
with its code beside its box, and all at once:

    first day yesterday             → closure.date_past             (a day ATT-4 may have worked out already)
    last day before the first       → closure.ends_before_it_starts
    a name of spaces                → closure.name_blank
    a day another closure has       → closure.overlaps               (the database's own rule, asked first)
    on the demo, a person's today   → demo.closures_from_tomorrow    (the system, as the seed acts, still may)

Two managers adding at the same moment take turns on the shop's row, so the second meets the first and gets its code,
never a database error.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from pytest_django import Settings

from apps.core.tenancy import ShopMismatch, shop_context
from apps.shops.models import Closure, ClosureStatus, Shop
from apps.shops.selectors import shop_today
from apps.shops.services import add_closure
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db


def refusal_codes(refused: ValidationError) -> dict[str, list[str | None]]:
    # Each field's codes, as the API's error handler reads them (apps/core/api/errors.py).
    return {field: [error.code for error in errors] for field, errors in refused.error_dict.items()}


def closures_of(shop: Shop) -> list[tuple[date, date, str]]:
    with shop_context(shop):
        return list(
            Closure.objects.filter(shop=shop).order_by("first_day").values_list("first_day", "last_day", "name")
        )


def test_closure_from_today_saved(shop_a: Shop, staff_a: Any) -> None:
    # The funeral: the shop closes this morning, for five days. Who added it, and when, is on the row itself.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        row = add_closure(shop_a, first_day=today, last_day=today + timedelta(days=4), name="Msiba wa bibi", by=staff_a)
    assert row.status == ClosureStatus.ACTIVE
    assert row.created_by_id == staff_a.pk
    assert closures_of(shop_a) == [(today, today + timedelta(days=4), "Msiba wa bibi")]


def test_closure_keeps_the_id_it_was_given(shop_a: Shop) -> None:
    # The page makes the closure's id (ADR-0007), so a request sent twice finds the row it made (the route, step 4).
    today = shop_today(shop_a)
    chosen = Closure().id
    with shop_context(shop_a):
        row = add_closure(shop_a, closure_id=chosen, first_day=today, last_day=today, name="Siku ya Uhuru", by=None)
    assert row.pk == chosen


def test_closure_before_today_refused(shop_a: Shop) -> None:
    # Yesterday is a day the attendance may already have worked out and paid: closing it now would change that. Beside
    # the first day's box, and nothing written.
    yesterday = shop_today(shop_a) - timedelta(days=1)
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        add_closure(shop_a, first_day=yesterday, last_day=yesterday + timedelta(days=2), name="Msiba wa bibi", by=None)
    assert refusal_codes(refused.value) == {"first_day": ["closure.date_past"]}
    assert closures_of(shop_a) == []


def test_every_mistake_at_once(shop_a: Shop) -> None:
    # Three mistakes in one form: the owner sees them all at once, each beside its box, not one after another.
    yesterday = shop_today(shop_a) - timedelta(days=1)
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        add_closure(shop_a, first_day=yesterday, last_day=yesterday - timedelta(days=3), name="  ", by=None)
    assert refusal_codes(refused.value) == {
        "first_day": ["closure.date_past"],
        "last_day": ["closure.ends_before_it_starts"],
        "name": ["closure.name_blank"],
    }


def test_two_closures_sharing_a_day_refused(shop_a: Shop) -> None:
    # Krismasi closes the 25th and 26th; a second closure that takes the 26th is refused with its code, not a database
    # error, and nothing more is written.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        add_closure(
            shop_a, first_day=today + timedelta(days=5), last_day=today + timedelta(days=6), name="Krismasi", by=None
        )
        with pytest.raises(ValidationError) as refused:
            add_closure(
                shop_a,
                first_day=today + timedelta(days=6),
                last_day=today + timedelta(days=7),
                name="Mapumziko",
                by=None,
            )
    assert refusal_codes(refused.value) == {"__all__": ["closure.overlaps"]}
    assert [name for _first, _last, name in closures_of(shop_a)] == ["Krismasi"]


@pytest.mark.django_db(transaction=True)
def test_two_adds_at_once_take_turns(shop_a: Shop) -> None:
    # Two managers at the same moment close days that share tomorrow. Each alone is fine; together they clash. The
    # second waits for the shop's row, which the first holds until it commits, then sees the first closure and is
    # refused with its code. Without the lock both would pass the check, and the database would refuse the second with
    # an error no screen can explain. transaction=True, as in test_day_in_order.py: the shop is really committed, so
    # the second manager's own connection can see it at all.
    today = shop_today(shop_a)

    def second_manager_adds() -> object:
        with shop_context(shop_a.pk):
            return add_closure(
                shop_a,
                first_day=today + timedelta(days=1),
                last_day=today + timedelta(days=2),
                name="Mapumziko",
                by=None,
            )

    with shop_context(shop_a), transaction.atomic():
        add_closure(shop_a, first_day=today, last_day=today + timedelta(days=1), name="Msiba wa bibi", by=None)
        second, ended = in_another_transaction(second_manager_adds)
        # The second waits for this transaction, which hasn't committed yet.
        wait_until_someone_waits_for_me()
    # The first commits here; the second goes on, and meets it.
    second.join(timeout=5)
    assert not second.is_alive(), "The second add still waits after the first committed."
    (refused,) = ended
    assert isinstance(refused, ValidationError)
    assert refusal_codes(refused) == {"__all__": ["closure.overlaps"]}
    assert [name for _first, _last, name in closures_of(shop_a)] == ["Msiba wa bibi"]


def test_demo_closures_from_tomorrow(shop_a: Shop, staff_a: Any, settings: Settings) -> None:
    # On the demo every visitor shares the manager's login (OPS-3): a visitor's closure from today would close today's
    # demo for everyone after them, until the night's seed. So a person's starts tomorrow or later; the system, as the
    # seed acts, still may close today.
    settings.DEMO_SEED = True
    today = shop_today(shop_a)
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            add_closure(shop_a, first_day=today, last_day=today, name="Siku ya mfano", by=staff_a)
        assert refusal_codes(refused.value) == {"first_day": ["demo.closures_from_tomorrow"]}
        add_closure(
            shop_a, first_day=today + timedelta(days=1), last_day=today + timedelta(days=1), name="Kesho", by=staff_a
        )
        add_closure(shop_a, first_day=today, last_day=today, name="Ya mfumo", by=None)
    assert [name for _first, _last, name in closures_of(shop_a)] == ["Ya mfumo", "Kesho"]


def test_add_closure_checks_the_shop(shop_a: Shop, shop_b: Shop, staff_b: Any) -> None:
    # A bug in the calling code, not a person's mistake: shop B's manager can't close shop A, and a closure is written
    # into the shop the visit opened, or not at all.
    today = shop_today(shop_a)
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        add_closure(shop_a, first_day=today, last_day=today, name="Msiba", by=staff_b)
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        add_closure(shop_a, first_day=today, last_day=today, name="Msiba", by=None)
    assert closures_of(shop_a) == []
