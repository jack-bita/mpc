"""apps/shops/tests/test_setting_rows.py — the rules of a setting row: one dated value of one rule (02 §4, D13).

A rule that changes over time is kept as rows, never as one value that is overwritten:

    shop    side   key                    value     effective_from
    MFANO   —      attendance.late_fine   1000.00   2026-01-01    ← stays, never changed
    MFANO   —      attendance.late_fine   1500.00   2026-11-01    ← a change is a new row
    MFANO   D      cash.tolerance         500.00    2026-01-01    ← Dawa's own value

These tests check what a row may hold: a key from the list in `core` (apps/core/settings_registry.py), a
value of that key's kind, a side only where the key allows one, and no change or delete once it is
written (ADR-0013, ADR-0021). Which row is in force on a day is test_get_setting.py's subject.

Setting is ShopScoped, so the tests work inside shop_context(shop), as a visit will (CORE-2).
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.models import AppendOnlyError
from apps.core.settings_registry import (
    BLOCK_NEGATIVE_STOCK,
    CASH_TOLERANCE,
    COUNT_TOLERANCE_PCT,
    IDLE_MINUTES,
    LATE_FINE,
    ON_TIME_UNTIL,
)
from apps.core.tenancy import shop_context
from apps.shops.models import Setting, Shop, Side

pytestmark = pytest.mark.django_db

JAN_1 = date(2026, 1, 1)


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    # Shop A's Drugs side, for the rows a side may have of its own.
    with shop_context(shop_a):
        return Side.objects.create(shop=shop_a, code="D", name="Dawa")


def new_row(shop: Shop, key: str, value: str, side: Side | None = None) -> Setting:
    # A row as a form brings it: not yet checked, not yet saved.
    return Setting(shop=shop, side=side, key=key, value=value, effective_from=JAN_1)


def codes(refused: pytest.ExceptionInfo[ValidationError], field: str) -> list[str | None]:
    # The codes one field was refused with: the screens translate codes, not sentences (ADR-0032).
    return [error.code for error in refused.value.error_dict[field]]


def test_setting_value_stored_in_one_form(shop_a: Shop) -> None:
    # "1500", "1500.0" and "1500.00" are the same fine. Each is stored as "1500.00", so the history
    # shows one value one way, and every device reads one form.
    with shop_context(shop_a):
        row = new_row(shop_a, LATE_FINE.key, "1500")
        row.full_clean()
        row.save()
        row.refresh_from_db()

    assert row.value == "1500.00"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        pytest.param(LATE_FINE.key, "abc", id="money_not_a_number"),
        pytest.param(LATE_FINE.key, "1,000", id="money_with_a_comma"),
        pytest.param(ON_TIME_UNTIL.key, "25:00", id="time_past_midnight"),
        pytest.param(IDLE_MINUTES.key, "0", id="whole_below_its_minimum"),
        pytest.param(COUNT_TOLERANCE_PCT.key, "101", id="percent_above_100"),
        pytest.param(BLOCK_NEGATIVE_STOCK.key, "yes", id="yesno_word"),
    ],
)
def test_setting_type_checked(shop_a: Shop, key: str, value: str) -> None:
    # Each key takes one kind of value. The value is checked when the row is checked (full_clean),
    # before anything is saved, and refused with a code instead of a crash on the day a card reads it.
    with shop_context(shop_a):
        row = new_row(shop_a, key, value)
        with pytest.raises(ValidationError) as refused:
            row.full_clean()

    assert codes(refused, "value") == ["setting.value_invalid"]


def test_empty_value_reported_once(shop_a: Shop) -> None:
    # An empty value fails the field's own check, with Django's code `blank`. full_clean runs clean() even
    # so, and clean() leaves an empty value alone: one refusal, not two for the same mistake.
    with shop_context(shop_a):
        row = new_row(shop_a, LATE_FINE.key, "")
        with pytest.raises(ValidationError) as refused:
            row.full_clean()

    assert codes(refused, "value") == ["blank"]


def test_empty_key_reported_once(shop_a: Shop) -> None:
    # The same for an empty key: the field's own check reports it (`blank`), and clean() doesn't add
    # "unknown setting" for the same mistake.
    with shop_context(shop_a):
        row = new_row(shop_a, "", "1000")
        with pytest.raises(ValidationError) as refused:
            row.full_clean()

    assert codes(refused, "key") == ["blank"]


def test_setting_key_checked(shop_a: Shop, dawa: Side) -> None:
    with shop_context(shop_a):
        # A name that is not in the list, such as a typo: no code would ever read its row.
        unknown = new_row(shop_a, "attendance.late_fee", "1000")
        with pytest.raises(ValidationError) as refused:
            unknown.full_clean()
        assert codes(refused, "key") == ["setting.key_unknown"]

        # The late fine is one value for the whole shop: a fine for Dawa alone is refused.
        shop_wide = new_row(shop_a, LATE_FINE.key, "1000", side=dawa)
        with pytest.raises(ValidationError) as refused:
            shop_wide.full_clean()
        assert codes(refused, "side") == ["setting.side_not_allowed"]

        # The cash tolerance may differ per side: Dawa's own value passes.
        new_row(shop_a, CASH_TOLERANCE.key, "500", side=dawa).full_clean()


@pytest.mark.parametrize(
    ("fields", "rule"),
    [
        pytest.param({"key": "Late Fine"}, "shops_setting_key_shape", id="key_with_capitals_and_a_space"),
        pytest.param({"key": "late_fine"}, "shops_setting_key_shape", id="key_without_its_area"),
        pytest.param({"value": ""}, "shops_setting_value_not_blank", id="value_blank"),
    ],
)
def test_database_refuses_a_setting_that_breaks_a_rule(shop_a: Shop, fields: dict[str, str], rule: str) -> None:
    # Code that saves without full_clean skips the checks above, so the database holds what it can
    # (03 §5.6): the key's shape and a value that isn't empty. The list of keys and their kinds live in
    # code, where the database can't see them.
    row = {"key": LATE_FINE.key, "value": "1000.00", "effective_from": JAN_1}
    with shop_context(shop_a), pytest.raises(IntegrityError, match=rule):
        Setting.objects.create(shop=shop_a, **{**row, **fields})


def test_setting_rows_cannot_be_edited(shop_a: Shop) -> None:
    # A rule change is a new row; the old row is history (ADR-0013). So a written row is never changed
    # or deleted: Python refuses first, with a clear message (AppendOnly), and PostgreSQL's trigger
    # refuses whatever goes past Python, such as a bulk update() or delete() (ADR-0021).
    with shop_context(shop_a):
        row = new_row(shop_a, LATE_FINE.key, "1500")
        row.full_clean()
        row.save()

        row.value = "15000.00"
        with pytest.raises(AppendOnlyError):
            row.save()
        with pytest.raises(AppendOnlyError):
            row.delete()
        # Each savepoint (transaction.atomic) takes back only the refused command, so the test can
        # still read the row afterwards (apps/core/tests/test_append_only.py explains why).
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            Setting.objects.filter(pk=row.pk).update(value="15000.00")
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            Setting.objects.filter(pk=row.pk).delete()

        row.refresh_from_db()

    assert row.value == "1500.00"
