"""apps/staffpay/tests/test_worker_month_route.py — a worker's month's route, /api/v1/staffpay/attendance-worker/{id}/
(ATT-12, 03 §5.10).

    GET  attendance-worker/{id}/?month=2026-10   the worker's days, counts and taps, for their calendar

What a worker's month holds is worker_attendance's, tested in test_worker_month.py; who may open it is pinned in
backend/tests/test_route_permissions.py, beside every other route's. Here, the answer as the page reads it, a worker the
route doesn't show, and a month it can't read. The client from backend/conftest.py holds every key: shop A's owner,
Staff A. Fake data only.
"""

import datetime as dt
import uuid
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

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")


def worker_url(staff_id: uuid.UUID | str) -> str:
    return f"/api/v1/staffpay/attendance-worker/{staff_id}/"


def _worker(shop: Shop, name: str) -> StaffMember:
    # A worker since 1 September, in a shop that switched attendance on in January, paid a made-up 13,579 a day: an
    # amount no other number of the answer can be, so the test can look for it.
    with shop_context(shop):
        Setting.objects.create(shop=shop, key=ATTENDANCE_ON.key, value="true", effective_from=dt.date(2026, 1, 1))
        user = User.objects.create_user(full_name=f"{name} Demo")
        staff = add_staff(shop=shop, user=user, display_name=name, started_on=dt.date(2026, 9, 1), by=None)
        set_pay_rate(staff, daily_rate=Decimal("13579"), effective_from=staff.started_on, by=None)
    return staff


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    return _worker(shop_a, "Asha")


def test_the_workers_month_as_the_page_reads_it(
    staff_client_a: APIClient, shop_a: Shop, device_a: Device, asha: StaffMember
) -> None:
    # Asha came at 09:10 on Friday 2 October, from the Dawa laptop, which kept no photo (the demo's reason): her day
    # waits for a decision, and says why with the book's code; her tap is a minute on the shop's clock, which the page
    # turns into "Ingia 09:10 asubuhi · Laptop ya Dawa". Her line counts her October; no amount but the fine travels.
    moment = dt.datetime(2026, 10, 2, 9, 10, 25, tzinfo=ARUSHA)
    with shop_context(shop_a):
        ingia = AttendanceEvent.objects.create(
            shop=shop_a,
            device=device_a,
            device_seq=1,
            client_time=moment,
            received_at=moment,
            created_by=asha,
            staff=asha,
            kind=ClockKind.IN,
            trusted_time=moment,
            time_check=TimeCheck.DEVICE_OK,
            last_server_time=moment,
            clock_error=dt.timedelta(0),
            no_photo="demo",
        )

    reply = staff_client_a.get(worker_url(asha.pk), {"month": "2026-10"})

    assert reply.status_code == 200
    answer = reply.json()
    assert {key: answer[key] for key in ("month", "today", "worker", "started_on", "left_on", "taps")} == {
        "month": "2026-10",
        "today": shop_today(shop_a).isoformat(),
        "worker": {
            "staff": str(asha.pk),
            "display_name": "Asha",
            "on_time": 0,
            "late": 0,
            "half": 0,
            "absent": 26,
            "needs_review": 1,
        },
        "started_on": "2026-09-01",
        "left_on": None,
        "taps": [
            {
                "id": str(ingia.pk),
                "date": "2026-10-02",
                "kind": "in",
                "time": "09:10",
                "laptop_time": "09:10",
                "laptop": "Laptop ya Dawa",
                "photo": None,
                "no_photo": "demo",
                "doubt": None,
            }
        ],
    }
    # Every day of October the book answers, Sundays too; the 2nd waits for a decision, the 1st was a day away.
    assert len(answer["days"]) == 31
    assert answer["days"][1] == {
        "date": "2026-10-02",
        "status": "needs_review",
        "reason": "came_late",
        "fine": "0.00",
        "first_in": "09:10",
        "first_out": None,
    }
    assert answer["days"][0] == {
        "date": "2026-10-01",
        "status": "absent",
        "reason": None,
        "fine": "0.00",
        "first_in": None,
        "first_out": None,
    }
    assert "13579" not in reply.content.decode()


def test_another_shops_worker_is_not_found(staff_client_a: APIClient, shop_b: Shop) -> None:
    # Bahati works at shop B. Asked for from shop A, her month is "not found", exactly as an id no shop has: the answer
    # never tells that she exists (03 §5.4). The tenancy sweep asks the same of every one of A's workers, as shop B.
    bahati = _worker(shop_b, "Bahati")
    theirs = staff_client_a.get(worker_url(bahati.pk), {"month": "2026-10"})
    nobodys = staff_client_a.get(worker_url(uuid.uuid7()), {"month": "2026-10"})
    assert theirs.status_code == 404
    assert theirs.json() == nobodys.json()


@pytest.mark.parametrize("month", ["2026-13", "2026-10-02", "Oktoba", "", "2026-1", "1999-12"])
def test_a_month_the_route_cant_read_is_refused(staff_client_a: APIClient, asha: StaffMember, month: str) -> None:
    # The page always sends "2026-10", the month it came from. Anything else is refused under `month`, as the month's
    # route refuses it (ATT-5), and no month is worked out.
    reply = staff_client_a.get(worker_url(asha.pk), {"month": month})
    assert reply.status_code == 400
    assert "month" in reply.json()["fields"]


def test_no_month_is_refused(staff_client_a: APIClient, asha: StaffMember) -> None:
    reply = staff_client_a.get(worker_url(asha.pk))
    assert reply.status_code == 400
    assert reply.json()["fields"]["month"] == ["required"]


def test_the_calendars_last_month_answers_nothing(staff_client_a: APIClient, asha: StaffMember) -> None:
    # Someone types ?month=9999-12 into the worker page's address. No day of it is over and no tap can be in it, so the
    # answer is an empty month: never a server error from reading past the calendar's last day (ATT-12's review, as
    # ATT-5's on the month page).
    reply = staff_client_a.get(worker_url(asha.pk), {"month": "9999-12"})
    assert reply.status_code == 200
    assert (reply.json()["days"], reply.json()["taps"]) == ([], [])
