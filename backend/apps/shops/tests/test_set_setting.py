"""apps/shops/tests/test_set_setting.py — set_setting, the one way a rule's new value is written (SHOP-3, ADR-0013).

A new value is a new row, never an edit: the late fine is 1,000 today, and the owner sets 2,000 from 1 December. The
service checks what Setting.clean() holds (a known key, a value of its kind, no side for a shop's rule), which
`objects.create` would skip, and two rules of its own, both Jack's (15 Nov 2026):
- a value starts on the shop's today or later, never before: an earlier day would change what past days answer, and a
  draft pay run with them;
- a side's rule (the two tolerances, the expiry alert, blocking stock below zero) is set one side at a time, with no
  row for the whole shop, so a side's old row can never hide a newer shop value (CORE-4: a side's row beats it).
Each saved row lands its line in the shop's change log, so the laptops get it at their next pull (SYNC-2). The staff
members come from backend/conftest.py and are typed Any: `shops` may not name `people`'s StaffMember (ADR-0043).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import ChangeOp
from apps.core.settings_registry import CASH_TOLERANCE, LATE_FINE
from apps.core.tenancy import ShopMismatch, shop_context
from apps.shops.models import Setting, Shop, Side
from apps.shops.selectors import get_setting, shop_today
from apps.shops.services import set_setting
from tests.change_log import lines_written

pytestmark = pytest.mark.django_db


def refusal_codes(refused: pytest.ExceptionInfo[ValidationError]) -> dict[str, list[str | None]]:
    # Each field's codes, as the API's error handler reads them (apps/core/api/errors.py).
    return {field: [error.code for error in errors] for field, errors in refused.value.error_dict.items()}


def no_rows(shop: Shop) -> bool:
    with shop_context(shop):
        return not Setting.objects.filter(shop=shop).exists()


def test_set_setting_saves_a_new_row(shop_a: Shop, staff_a: Any) -> None:
    # The owner sets the late fine to 2,000 from tomorrow, then to 2,500 from next week. Each is a row of its own: today
    # still answers the default 1,000, tomorrow 2,000, next week 2,500. The value is stored in its kind's one form
    # ("2000" as "2000.00"), and who set it is the row's created_by (02 v1.7).
    today = shop_today(shop_a)
    with shop_context(shop_a):
        tomorrow = today + timedelta(days=1)
        first = set_setting(
            shop_a, key=LATE_FINE.key, value="2000", effective_from=tomorrow, note="Mwezi mpya", by=staff_a
        )
        set_setting(shop_a, key=LATE_FINE.key, value="2500", effective_from=today + timedelta(days=7), by=staff_a)

        assert get_setting(LATE_FINE, shop_a, on=today) == Decimal("1000.00")
        assert get_setting(LATE_FINE, shop_a, on=today + timedelta(days=1)) == Decimal("2000.00")
        assert get_setting(LATE_FINE, shop_a, on=today + timedelta(days=7)) == Decimal("2500.00")
        saved = Setting.objects.get(pk=first.pk)
    assert (saved.value, saved.note, saved.side_id, saved.created_by_id) == ("2000.00", "Mwezi mpya", None, staff_a.pk)


def test_past_day_refused(shop_a: Shop) -> None:
    # Yesterday is refused, and nothing is written: a value from yesterday would change what yesterday's clock-ins
    # answer (Jack, 15 Nov 2026).
    yesterday = shop_today(shop_a) - timedelta(days=1)
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        set_setting(shop_a, key=LATE_FINE.key, value="2000", effective_from=yesterday, by=None)
    assert refusal_codes(refused) == {"effective_from": ["setting.date_past"]}
    assert no_rows(shop_a)


def test_past_day_is_the_shops_day(shop_a: Shop) -> None:
    # "Today" is the shop's, not the server's: at 23:30 UTC on 14 Nov, it is already 02:30 on 15 Nov in Arusha. So
    # 14 Nov is a past day there, although the server's own clock is still on it.
    late_in_utc = datetime(2026, 11, 14, 23, 30, tzinfo=UTC)
    with shop_context(shop_a), patch("django.utils.timezone.now", return_value=late_in_utc):
        with pytest.raises(ValidationError) as refused:
            set_setting(shop_a, key=LATE_FINE.key, value="2000", effective_from=date(2026, 11, 14), by=None)
        assert refusal_codes(refused) == {"effective_from": ["setting.date_past"]}
        set_setting(shop_a, key=LATE_FINE.key, value="2000", effective_from=date(2026, 11, 15), by=None)


def test_today_allowed_and_same_day_fix_wins(shop_a: Shop) -> None:
    # Today may still take a new value, and a mistake made today is fixed with one more row for the same day: the row
    # written last wins (T2). The first row stays, as rows are never edited.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        set_setting(shop_a, key=LATE_FINE.key, value="15000", effective_from=today, by=None)
        set_setting(shop_a, key=LATE_FINE.key, value="1500", effective_from=today, note="Sifuri moja zaidi", by=None)
        assert get_setting(LATE_FINE, shop_a, on=today) == Decimal("1500.00")
        assert Setting.objects.filter(shop=shop_a, key=LATE_FINE.key).count() == 2


def test_side_rule_needs_a_side(shop_a: Shop) -> None:
    # The cash tolerance is set for Dawa or for Vyakula, never for the whole shop (Jack, 15 Nov 2026): a whole-shop row
    # would be hidden by any side's own row, even an older one, and nobody would see why.
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        set_setting(shop_a, key=CASH_TOLERANCE.key, value="500", effective_from=shop_today(shop_a), by=None)
    assert refusal_codes(refused) == {"side": ["setting.side_required"]}
    assert no_rows(shop_a)


def test_side_rule_set_for_one_side(shop_a: Shop, side_a: Side) -> None:
    # With its side named, the cash tolerance is Dawa's alone.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        set_setting(shop_a, key=CASH_TOLERANCE.key, value="500", effective_from=today, side=side_a, by=None)
        assert get_setting(CASH_TOLERANCE, shop_a, side_a, on=today) == Decimal("500.00")


def test_shop_rule_refuses_a_side(shop_a: Shop, side_a: Side) -> None:
    # The late fine is the whole shop's: staff work for the shop, not a side (02 §5). Setting.clean() holds this rule,
    # which only a save through full_clean asks.
    with shop_context(shop_a), pytest.raises(ValidationError) as refused:
        set_setting(shop_a, key=LATE_FINE.key, value="2000", effective_from=shop_today(shop_a), side=side_a, by=None)
    assert refusal_codes(refused) == {"side": ["setting.side_not_allowed"]}
    assert no_rows(shop_a)


def test_side_of_another_shop_refused(shop_a: Shop, side_b: Side, staff_b: Any) -> None:
    # T1: shop A's rule can't name shop B's side, nor be set by shop B's staff. Both are bugs in the calling code, not a
    # person's mistake, so they raise ShopMismatch, a server error, and write nothing.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        with pytest.raises(ShopMismatch):
            set_setting(shop_a, key=CASH_TOLERANCE.key, value="500", effective_from=today, side=side_b, by=None)
        with pytest.raises(ShopMismatch):
            set_setting(shop_a, key=LATE_FINE.key, value="2000", effective_from=today, by=staff_b)
    assert no_rows(shop_a)


def test_wrong_value_refused(shop_a: Shop) -> None:
    # A value its kind can't read, and a key the registry doesn't list, are refused with their codes, and nothing is
    # written. Several mistakes at once come back together, so a screen shows each beside its box.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as wrong_value:
            set_setting(shop_a, key=LATE_FINE.key, value="elfu mbili", effective_from=today, by=None)
        with pytest.raises(ValidationError) as unknown_key:
            set_setting(shop_a, key="attendance.lunch_fine", value="500", effective_from=today, by=None)
        with pytest.raises(ValidationError) as both:
            set_setting(shop_a, key=LATE_FINE.key, value="-5", effective_from=today - timedelta(days=1), by=None)
    assert refusal_codes(wrong_value) == {"value": ["setting.value_invalid"]}
    assert refusal_codes(unknown_key) == {"key": ["setting.key_unknown"]}
    assert refusal_codes(both) == {"effective_from": ["setting.date_past"], "value": ["setting.value_invalid"]}
    assert no_rows(shop_a)


def test_new_value_lands_a_change_line(shop_a: Shop, side_a: Side) -> None:
    # Each new row names itself in the change log, so a laptop learns it at its next pull, and switches to it on its
    # day, even offline (03 §5.8). A refused value names nothing.
    today = shop_today(shop_a)
    with shop_context(shop_a):
        with lines_written(shop_a) as saved:
            row = set_setting(shop_a, key=CASH_TOLERANCE.key, value="500", effective_from=today, side=side_a, by=None)
        with lines_written(shop_a) as refused, pytest.raises(ValidationError):
            set_setting(shop_a, key=CASH_TOLERANCE.key, value="500", effective_from=today, by=None)
    assert saved == [("setting", row.pk, ChangeOp.UPSERT)]
    assert refused == []
