"""apps/staffpay/tests/test_attendance_day.py — the day's rule (ATT-4; spec §8.1, 02 §12), test by test.

Every window of the owner's day is a minute on the shop's clock, as the counter shows it (SYNC-11): a tap's seconds
never count, and the server's UTC is never the shop's time. shop_minute (apps/staffpay/calculations.py) turns a tap's
time into that minute. Pure: no database, no clock of its own. Fake data only: the repo is public.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from apps.staffpay.calculations import shop_minute

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")


def test_shop_minute_reads_the_shops_clock() -> None:
    # The database keeps every time in UTC: Asha's tap at 07:35:40 in Arusha comes back as 04:35:40. The windows are
    # the shop's, three hours ahead, so the minute is read on the shop's clock, or she would look three hours early.
    stored = dt.datetime(2026, 11, 10, 4, 35, 40, tzinfo=dt.UTC)
    assert shop_minute(stored, ARUSHA) == dt.time(7, 35)


def test_shop_minute_drops_the_seconds() -> None:
    # 07:35:59 still shows 07:35 on the laptop, so it is still on time: the minute is cut, never rounded up to 07:36.
    tap = dt.datetime(2026, 11, 10, 7, 35, 59, 999999, tzinfo=ARUSHA)
    assert shop_minute(tap, ARUSHA) == dt.time(7, 35)


def test_shop_minute_refuses_a_time_with_no_zone() -> None:
    # A time with no zone says nothing of where it was read: Python would take it on the server's own clock, three
    # hours off Arusha's, and Asha's 07:35 would turn into 10:35, a day of dharura. So it fails loudly instead.
    with pytest.raises(ValueError):
        shop_minute(dt.datetime(2026, 11, 10, 7, 35), ARUSHA)
