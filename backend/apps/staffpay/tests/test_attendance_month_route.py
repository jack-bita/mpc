"""apps/staffpay/tests/test_attendance_month_route.py — the month page's route, /api/v1/staffpay/attendance-month/
(ATT-5, 03 §5.10).

    GET  attendance-month/?month=2026-10   the month, the shop's today, a line per worker, and the days to decide

What the month holds is attendance_month's, tested in test_attendance_month.py; who may open it is pinned in
backend/tests/test_route_permissions.py, beside every other route's. Here, the answer as the page reads it, and a month
the route can't read. The client from backend/conftest.py holds every key: shop A's owner, Staff A. Fake data only.
"""

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff
from apps.shops.models import Setting, Shop
from apps.shops.selectors import shop_today
from apps.staffpay.models import AttendanceEvent, ClockKind, TimeCheck
from apps.staffpay.services import set_pay_rate

pytestmark = pytest.mark.django_db

MONTH = "/api/v1/staffpay/attendance-month/"
ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    # Asha, paid a made-up 13,579 a day since 1 September, in a shop that switched attendance on in January: an amount
    # no other number of the answer can be, so the test can look for it.
    with shop_context(shop_a):
        Setting.objects.create(shop=shop_a, key=ATTENDANCE_ON.key, value="true", effective_from=dt.date(2026, 1, 1))
        user = User.objects.create_user(full_name="Asha Demo")
        asha = add_staff(shop=shop_a, user=user, display_name="Asha", started_on=dt.date(2026, 9, 1), by=None)
        set_pay_rate(asha, daily_rate=Decimal("13579"), effective_from=asha.started_on, by=None)
    return asha


def test_the_month_as_the_page_reads_it(
    staff_client_a: APIClient, shop_a: Shop, device_a: Device, asha: StaffMember
) -> None:
    # Asha came at 09:10 on Friday 2 October: a day to decide, said with its reason's code and her two taps as minutes
    # on the shop's clock, which the page turns into "alifika saa 09:10 asubuhi". Her line counts her October; no
    # amount travels, as a manager with the attendance key alone may not see pay.
    for kind, minute in ((ClockKind.IN, dt.time(9, 10)), (ClockKind.OUT, dt.time(18, 45))):
        moment = dt.datetime.combine(dt.date(2026, 10, 2), minute, tzinfo=ARUSHA)
        with shop_context(shop_a):
            AttendanceEvent.objects.create(
                shop=shop_a,
                device=device_a,
                device_seq=1 if kind == ClockKind.IN else 2,
                client_time=moment,
                received_at=moment,
                created_by=asha,
                staff=asha,
                kind=kind,
                trusted_time=moment,
                time_check=TimeCheck.DEVICE_OK,
                last_server_time=moment,
                clock_error=dt.timedelta(0),
                no_photo="demo",
            )

    reply = staff_client_a.get(MONTH, {"month": "2026-10"})

    assert reply.status_code == 200
    assert reply.json() == {
        "month": "2026-10",
        "today": shop_today(shop_a).isoformat(),
        "working_day_over": True,
        "workers": [
            {
                "staff": str(asha.pk),
                "display_name": "Asha",
                "on_time": 0,
                "late": 0,
                "half": 0,
                "absent": 26,
                "needs_review": 1,
            }
        ],
        "to_decide": [
            {
                "staff": str(asha.pk),
                "display_name": "Asha",
                "date": "2026-10-02",
                "reason": "came_late",
                "first_in": "09:10",
                "first_out": "18:45",
            }
        ],
    }
    assert "13579" not in reply.content.decode()


@pytest.mark.parametrize("month", ["2026-13", "2026-10-02", "Oktoba", ""])
def test_a_month_the_route_cant_read_is_refused(staff_client_a: APIClient, month: str) -> None:
    # The page always sends "2026-10". Anything else is refused under `month`, and no month is worked out.
    reply = staff_client_a.get(MONTH, {"month": month})
    assert reply.status_code == 400
    assert "month" in reply.json()["fields"]


def test_no_month_is_refused(staff_client_a: APIClient) -> None:
    reply = staff_client_a.get(MONTH)
    assert reply.status_code == 400
    assert reply.json()["fields"]["month"] == ["required"]


def test_the_calendars_last_month_lists_nobody(staff_client_a: APIClient) -> None:
    # Someone types ?month=9999-12 into the address. No day of it is over, so nobody is listed: an answer, never a
    # server error from a sum that runs past the calendar's last day (ATT-5's review).
    reply = staff_client_a.get(MONTH, {"month": "9999-12"})
    assert reply.status_code == 200
    assert (reply.json()["workers"], reply.json()["to_decide"]) == ([], [])
