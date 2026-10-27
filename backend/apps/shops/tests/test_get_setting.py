"""apps/shops/tests/test_get_setting.py — get_setting: which value of a rule is in force on a day (02 §4, D13).

Every later card reads its rules through get_setting(key, shop, side, on=day). Given a shop's rows like
these, it answers:

    side   key                    value      effective_from
    —      attendance.late_fine   800.00     2026-01-01
    —      attendance.late_fine   1500.00    2026-11-01

    on 2025-12-31  →  1000.00   no row yet: the default from the list in core
    on 2026-10-31  →   800.00   the newest row on or before the day
    on 2026-11-01  →  1500.00   a row counts from its own day

A side's own row beats the shop's row, and on one day the row written last wins, so a typo is fixed
with one more row (T2). The value comes back as its kind: a Decimal for money, never text or a float.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

import pytest

from apps.core.settings_registry import CASH_TOLERANCE, LATE_FINE, ON_TIME_UNTIL, SettingKey
from apps.core.tenancy import NoShopSelected, shop_context, system_context
from apps.shops.models import Setting, Shop, Side
from apps.shops.selectors import get_setting

pytestmark = pytest.mark.django_db

DEC_31_2025 = date(2025, 12, 31)
JAN_1 = date(2026, 1, 1)
OCT_31 = date(2026, 10, 31)
NOV_1 = date(2026, 11, 1)
NOV_3 = date(2026, 11, 3)


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return Side.objects.create(shop=shop_a, code="D", name="Dawa")


@pytest.fixture
def vyakula(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return Side.objects.create(shop=shop_a, code="F", name="Vyakula")


def add_row(shop: Shop, key: SettingKey[Any], value: str, effective_from: date, side: Side | None = None) -> None:
    # A row written the way the settings screen will write one (SHOP-3): checked, then saved.
    with shop_context(shop):
        row = Setting(shop=shop, side=side, key=key.key, value=value, effective_from=effective_from)
        row.full_clean()
        row.save()


def test_default_when_no_rows(shop_a: Shop, dawa: Side) -> None:
    # A new shop has no rows: every rule is its default until the owner sets a value.
    with shop_context(shop_a):
        fine = get_setting(LATE_FINE, shop_a, on=NOV_3)
        assert get_setting(ON_TIME_UNTIL, shop_a, on=NOV_3) == time(7, 35)
        assert get_setting(CASH_TOLERANCE, shop_a, dawa, on=NOV_3) == Decimal("0.00")

    assert fine == Decimal("1000.00")
    # Money comes back exact: Python says Decimal("1000") == 1000.0, so check the type too (ADR-0024).
    assert type(fine) is Decimal


def test_latest_row_on_or_before_date_wins(shop_a: Shop) -> None:
    # Written in the other order on purpose: the dates decide, not which row was typed first.
    add_row(shop_a, LATE_FINE, "1500", NOV_1)
    add_row(shop_a, LATE_FINE, "800", JAN_1)

    with shop_context(shop_a):
        assert get_setting(LATE_FINE, shop_a, on=DEC_31_2025) == Decimal("1000.00")  # before any row
        assert get_setting(LATE_FINE, shop_a, on=OCT_31) == Decimal("800.00")
        assert get_setting(LATE_FINE, shop_a, on=NOV_1) == Decimal("1500.00")  # on its own day
        assert get_setting(LATE_FINE, shop_a, on=NOV_3) == Decimal("1500.00")


def test_future_row_ignored_until_its_day(shop_a: Shop) -> None:
    # Today is 31 Oct, and the owner sets tomorrow's new fine a day early. Being late today still costs
    # the old fine; devices get the row early and switch on the right day, even offline (03 §5.8).
    add_row(shop_a, LATE_FINE, "1500", NOV_1)

    with shop_context(shop_a):
        assert get_setting(LATE_FINE, shop_a, on=OCT_31) == Decimal("1000.00")
        assert get_setting(LATE_FINE, shop_a, on=NOV_1) == Decimal("1500.00")


def test_side_row_beats_shop_row(shop_a: Shop, dawa: Side, vyakula: Side) -> None:
    # The cash tolerance: 2,000 for the shop, but Dawa has its own, 500.
    add_row(shop_a, CASH_TOLERANCE, "2000", JAN_1)
    add_row(shop_a, CASH_TOLERANCE, "500", JAN_1, side=dawa)

    with shop_context(shop_a):
        assert get_setting(CASH_TOLERANCE, shop_a, dawa, on=NOV_3) == Decimal("500.00")
        assert get_setting(CASH_TOLERANCE, shop_a, vyakula, on=NOV_3) == Decimal("2000.00")
        assert get_setting(CASH_TOLERANCE, shop_a, on=NOV_3) == Decimal("2000.00")

    # Even a newer shop row: Dawa keeps its own value until Dawa gets a new row (02 §4).
    add_row(shop_a, CASH_TOLERANCE, "3000", NOV_1)

    with shop_context(shop_a):
        assert get_setting(CASH_TOLERANCE, shop_a, dawa, on=NOV_3) == Decimal("500.00")
        assert get_setting(CASH_TOLERANCE, shop_a, vyakula, on=NOV_3) == Decimal("3000.00")


def test_same_day_fix_wins(shop_a: Shop) -> None:
    # The owner types 15,000 instead of 1,500. Rows are never edited (ADR-0013), so the fix is one more
    # row for the same day, and the row written last wins.
    add_row(shop_a, LATE_FINE, "15000", NOV_1)
    add_row(shop_a, LATE_FINE, "1500", NOV_1)

    with shop_context(shop_a):
        assert get_setting(LATE_FINE, shop_a, on=NOV_3) == Decimal("1500.00")


def test_system_context_reads_each_shops_own_rows(shop_a: Shop, shop_b: Shop) -> None:
    # A nightly job runs in system_context(), where the guard opens every shop's rows (CORE-2).
    # get_setting still answers for the one shop it is given: shop B's fine, written last, never
    # becomes shop A's.
    add_row(shop_a, LATE_FINE, "1500", JAN_1)
    add_row(shop_b, LATE_FINE, "2000", JAN_1)

    with system_context():
        assert get_setting(LATE_FINE, shop_a, on=NOV_3) == Decimal("1500.00")
        assert get_setting(LATE_FINE, shop_b, on=NOV_3) == Decimal("2000.00")


def test_get_setting_refuses_wrong_arguments(shop_a: Shop, shop_b: Shop) -> None:
    # Each of these is a bug in the calling code, and each would quietly give a wrong rule. So each
    # raises at once: a server error and a log line, never a message on a screen (ADR-0032).
    with shop_context(shop_b):
        side_of_b = Side.objects.create(shop=shop_b, code="D", name="Dawa")

    # No shop open: the guard's own refusal (CORE-2).
    with pytest.raises(NoShopSelected):
        get_setting(LATE_FINE, shop_a, on=NOV_3)

    with shop_context(shop_a):
        # Another shop than the one open: the guard would show none of its rows, and the default would
        # come back without a word. Fail closed instead (ADR-0022).
        with pytest.raises(ValueError, match="not the one open"):
            get_setting(LATE_FINE, shop_b, on=NOV_3)
        # A side of another shop: it would mix two shops' rules (T1).
        with pytest.raises(ValueError, match="another shop"):
            get_setting(CASH_TOLERANCE, shop_a, side_of_b, on=NOV_3)
        # A date and time, such as timezone.now(), instead of the shop's business date (02 §1). In UTC,
        # 22:00 on 31 Oct is already 1 Nov in Tanzania, so the day would be wrong for the last hours of
        # it. A datetime is a kind of date in Python, so mypy lets it through: the check runs here.
        with pytest.raises(TypeError, match="business date"):
            get_setting(LATE_FINE, shop_a, on=datetime(2026, 10, 31, 22, 0, tzinfo=UTC))
