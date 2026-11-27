"""apps/staffpay/tests/test_mine_routes.py — a worker's own days and pay as Siku na malipo yangu calls them (WAGE-4, 02
A4; 03 §5.10).

    GET  /api/v1/staffpay/mine/attendance/?month=2026-11   their own calendar's days, counts and taps
    GET  /api/v1/staffpay/mine/pay/?month=2026-11          their own pay, line by line, and how it was handed out

What each answer holds is the manager's own reads', asked as the worker (test_mine.py); here, that a worker reaches
only their own, with no key and no id, by a PIN's login or a password's, never cached; and that each answer holds only
what a worker is shown. The rates are made up, each an amount no other number of an answer can be, so a test can look
for it: Asha's 13,579, Baraka's 24,680 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import confirm_pairing, set_pin, start_pairing
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.api.serializers import OwnAttendanceAnswer, OwnPayAnswer
from apps.staffpay.models import ClockKind, Payslip
from apps.staffpay.services import approve_month, pay_month, set_pay_rate
from apps.staffpay.tests.days import JAN_1, MONDAY, job, switch_on, tapped

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes, written out: they are a promise to the app.
DAYS = "/api/v1/staffpay/mine/attendance/"
PAY = "/api/v1/staffpay/mine/pay/"
PIN_LOGIN = "/api/auth/pin-login/"
KEY_COOKIE = "device_key"
PIN = "4829"
NOVEMBER = MONDAY.replace(day=1)


def client_for(staff: StaffMember) -> APIClient:
    # The way the office screens call: logged in as this person, at their shop (backend/conftest.py). No role given:
    # what a worker reaches here, they reach with no key at all.
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def on_a_phone(staff: StaffMember) -> APIClient:
    # A real Django session, as a password's login leaves, so the route's own login checks it on every visit
    # (StaffSessionAuthentication), a temporary password's refusal included: not force_authenticate, which skips it.
    client = APIClient()
    client.force_login(User.objects.get(pk=staff.user_id))
    return client


def paid(shop: Shop, name: str, rate: str) -> StaffMember:
    # A worker since January, paid `rate` a day from then.
    worker = job(shop, name)
    with shop_context(shop):
        set_pay_rate(worker, daily_rate=Decimal(rate), effective_from=JAN_1, by=None)
    return worker


@pytest.fixture
def two(shop_a: Shop, device_a: Device) -> tuple[StaffMember, StaffMember]:
    # Asha and Baraka at shop A, attendance on since January, each in and out on Monday the 16th from the Dawa laptop.
    switch_on(shop_a)
    asha, baraka = paid(shop_a, "Asha", "13579"), paid(shop_a, "Baraka", "24680")
    tapped(asha, (ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45), date=MONDAY)
    tapped(baraka, (ClockKind.IN, 7, 10), (ClockKind.OUT, 18, 5), date=MONDAY)
    return asha, baraka


def month(client: APIClient, route: str, **asked: str) -> Any:
    return client.get(route, {"month": "2026-11"} | asked)


def test_a4_asha_sees_only_her_own_days(two: tuple[StaffMember, StaffMember]) -> None:
    # Asha, who holds no key, opens her November: her own line, her two taps, never Baraka's. Baraka's id sent along in
    # the address is read by nothing: the route has no id to read, only her login's job.
    asha, baraka = two
    reply = month(client_for(asha), DAYS)
    assert reply.status_code == 200
    body = reply.json()
    assert (body["worker"]["staff"], body["worker"]["display_name"], body["worker"]["on_time"]) == (
        str(asha.pk),
        "Asha",
        1,
    )
    assert [(tap["kind"], tap["time"]) for tap in body["taps"]] == [("in", "07:20"), ("out", "18:45")]
    assert "Baraka" not in reply.content.decode()
    assert month(client_for(asha), DAYS, staff=str(baraka.pk)).json() == body


def test_a4_asha_sees_only_her_own_pay(two: tuple[StaffMember, StaffMember]) -> None:
    # Her November's pay so far: one full day at her own 13,579. Nothing of Baraka's, not even his rate, whatever the
    # address names.
    asha, baraka = two
    reply = month(client_for(asha), PAY, staff=str(baraka.pk))
    assert reply.status_code == 200
    body = reply.json()
    assert body["paid_by_day"] is True
    assert [(line["paid_as"], line["days"], line["each"]) for line in body["line"]["pay"]["lines"]] == [
        ("full", 1, "13579.00")
    ]
    assert "24680" not in reply.content.decode()
    assert "Baraka" not in reply.content.decode()


def test_own_answers_hold_only_what_a_worker_is_shown(two: tuple[StaffMember, StaffMember]) -> None:
    # Each answer is the list a worker may read (OwnAttendanceAnswer, OwnPayAnswer), field by field: no tap's photo or
    # doubt, no day's choices or id, no payslip id, no signature, no offer of a correction, nothing of what an approval
    # waits for. A field a later card adds to the manager's answer fails here until someone decides a worker sees it.
    asha, _ = two
    days = month(client_for(asha), DAYS).json()
    assert set(days) == {
        "month",
        "today",
        "worker",
        "started_on",
        "left_on",
        "days",
        "taps",
        "ready_reasons",
        "ready_add_reasons",
        "ready_void_reasons",
    }
    assert set(days["days"][0]) == {
        "date",
        "status",
        "reason",
        "fine",
        "meal_share",
        "first_in",
        "first_out",
        "decision",
    }
    assert set(days["taps"][0]) == {
        "id",
        "date",
        "kind",
        "time",
        "laptop_time",
        "laptop",
        "entered",
        "voided",
        "after_approval",
    }
    # A tap the server trusts shows its own minute alone (own_attendance).
    assert days["taps"][0]["laptop_time"] is None
    pay = month(client_for(asha), PAY).json()
    assert set(pay) == {
        "month",
        "today",
        "counted_to",
        "paid_by_day",
        "no_day_yet",
        "line",
        "corrections",
        "void_reasons",
    }
    assert set(pay["line"]) == {
        "left_on",
        "pay",
        "today",
        "total",
        "carried_from",
        "approval",
        "to_hand_out",
        "payments",
    }


def shape(field: object) -> object:
    # Every field an answer sends, by name, and inside each the fields it sends in turn, every level down: a list as
    # [its item], a value as None. Read from the serializers themselves, so a field a later card adds anywhere inside,
    # in a part shared with the manager's answer too, shows here before any row of it exists.
    if isinstance(field, serializers.ListSerializer):
        return [shape(field.child)]
    if isinstance(field, serializers.Serializer):
        return {name: shape(child) for name, child in field.fields.items()}
    return None


# Who did something to a row, when and why: a tap added or crossed out, a payment or a correction crossed out.
STAMP: dict[str, object] = {"by": None, "at": None, "reason": None}
# A pay over some days, as the manager's lines read it (PaySerializer).
A_PAY: dict[str, object] = {
    "lines": [{"paid_as": None, "days": None, "each": None, "amount": None}],
    "fined_days": None,
    "fines": None,
    "meal_days": None,
    "meals": None,
    "advances": None,
    "carried": None,
    "corrections": None,
    "waiting": None,
    "no_rate": None,
    "total": None,
}


def test_own_answers_list_every_field_inside_them_too() -> None:
    # The review: the test above reads the outer fields of what came, and the own answers still nest the manager's
    # parts (a decision, a tap's stamps, a pay, an approval, a correction). So every field, every level down, is
    # written out here: one added later to any part, a manager's note on a decision say, fails here until someone
    # decides a worker may read it.
    assert shape(OwnAttendanceAnswer()) == {
        "month": None,
        "today": None,
        "worker": {
            "staff": None,
            "display_name": None,
            "on_time": None,
            "late": None,
            "half": None,
            "absent": None,
            "needs_review": None,
        },
        "started_on": None,
        "left_on": None,
        "days": [
            {
                "date": None,
                "status": None,
                "reason": None,
                "fine": None,
                "meal_share": None,
                "first_in": None,
                "first_out": None,
                "decision": {
                    "status": None,
                    "absence_type": None,
                    "fine": None,
                    "by": None,
                    "at": None,
                    "reason": None,
                },
            }
        ],
        "taps": [
            {
                "id": None,
                "date": None,
                "kind": None,
                "time": None,
                "laptop_time": None,
                "laptop": None,
                "entered": STAMP,
                "voided": STAMP,
                "after_approval": None,
            }
        ],
        "ready_reasons": None,
        "ready_add_reasons": None,
        "ready_void_reasons": None,
    }
    assert shape(OwnPayAnswer()) == {
        "month": None,
        "today": None,
        "counted_to": None,
        "paid_by_day": None,
        "no_day_yet": None,
        "line": {
            "left_on": None,
            "pay": A_PAY,
            "today": A_PAY,
            "total": None,
            "carried_from": None,
            "approval": {"by": None, "at": None},
            "to_hand_out": None,
            "payments": [
                {
                    "id": None,
                    "method": None,
                    "reference": None,
                    "amount": None,
                    "by": None,
                    "at": None,
                    "voided": STAMP,
                }
            ],
        },
        "corrections": [{"id": None, "amount": None, "reason": None, "by": None, "at": None, "voided": STAMP}],
        "void_reasons": None,
    }


def test_an_approved_month_answers_its_payslip_and_how_it_was_paid(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, staff_client_a: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 19:05 on Tuesday 1 December in Arusha: November is over. Asha, paid 10,000 a day from November, came on Monday
    # the 16th; the owner (staff_a) approves November through the real approval, so her payslip keeps its lines, then
    # pays it by M-Pesa. Her page says who approved it and when, its lines as they were kept, and how it was handed
    # out, with the number to check against her phone; never the payslip's id, nor a signature (the review: written by
    # hand before, the payslip had no lines, so nothing showed they reach her).
    evening = dt.datetime(2026, 12, 1, 19, 5, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: evening)
    switch_on(shop_a)
    asha = job(shop_a, "Asha")
    with shop_context(shop_a):
        set_pay_rate(asha, daily_rate=Decimal("10000"), effective_from=NOVEMBER, by=None)
    tapped(asha, (ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45), date=MONDAY)
    with shop_context(shop_a):
        Device.objects.update(last_synced_at=timezone.now())
        seen = {line.staff_id: line.total for line in pay_month(shop_a, NOVEMBER).workers}
        approve_month(shop_a, NOVEMBER, run_id=uuid.uuid7(), seen=seen, by=staff_a)
        payslip = Payslip.objects.get(staff=asha, month=NOVEMBER)
    sent = {"id": str(uuid.uuid7()), "method": "mobile_money", "reference": "QK7H2M9XPL"}
    assert staff_client_a.post(f"/api/v1/staffpay/payslips/{payslip.pk}/pay/", sent, format="json").status_code == 200

    line = month(client_for(asha), PAY).json()["line"]

    assert (line["total"], line["to_hand_out"], line["approval"]["by"]) == ("10000.00", "0.00", "Staff A")
    # The payslip's own line, as the approval kept it: one full day at her rate.
    assert [(kept["paid_as"], kept["days"], kept["each"]) for kept in line["pay"]["lines"]] == [("full", 1, "10000.00")]
    [payment] = line["payments"]
    assert set(payment) == {"id", "method", "reference", "amount", "by", "at", "voided"}
    assert (payment["method"], payment["reference"], payment["amount"], payment["by"], payment["voided"]) == (
        "mobile_money",
        "QK7H2M9XPL",
        "10000.00",
        "Staff A",
        None,
    )


def test_no_daily_rate_says_so(shop_a: Shop, device_a: Device) -> None:
    # Neema came on Monday, but the shop pays her by no daily rate: her pay says there is no line of hers, and the page
    # says so in one sentence.
    switch_on(shop_a)
    neema = job(shop_a, "Neema")
    tapped(neema, (ClockKind.IN, 7, 50), (ClockKind.OUT, 18, 45), date=MONDAY)
    body = month(client_for(neema), PAY).json()
    assert (body["paid_by_day"], body["line"]["total"]) == (False, "0.00")


def test_own_answers_are_never_cached(two: tuple[StaffMember, StaffMember]) -> None:
    # A shop's laptop is shared: neither its browser nor a proxy on the way may keep a worker's pay (03 §6.1).
    asha, _ = two
    for route in (DAYS, PAY):
        assert "no-store" in month(client_for(asha), route)["Cache-Control"]


def test_a_month_before_the_job_or_to_come_is_refused_with_its_code(two: tuple[StaffMember, StaffMember]) -> None:
    # Asha started in January 2026: December 2025 is no month of hers, and a month a year ahead has no day yet. Each is
    # a slip of a typed address, refused with its code; no month, or one that is no month, is refused under `month`.
    asha, _ = two
    client = client_for(asha)
    for route in (DAYS, PAY):
        before = client.get(route, {"month": "2025-12"})
        assert (before.status_code, before.json()["code"], before.json()["fields"]) == (400, "mine.before_job", {})
        ahead = client.get(route, {"month": f"{dt.date.today().year + 1}-12"})
        assert (ahead.status_code, ahead.json()["code"]) == (400, "mine.month_to_come")
        assert "month" in client.get(route).json()["fields"]
        assert "month" in client.get(route, {"month": "2026-13"}).json()["fields"]


@pytest.fixture
def laptop_key(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> str:
    # A laptop paired the way the app pairs one: it asks and keeps its key, and a manager confirms its code.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    asked = start_pairing()
    with shop_context(staff_a2.shop_id):
        confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=side_a, by=staff_a2)
    return asked.key


def this_month(staff: StaffMember) -> dict[str, str]:
    # The shop's own month: the only one a job that starts today has. Never a month by name, which a job made by the
    # test, starting today, would not have had once that month is gone (the review: November, asked on 1 December).
    return {"month": shop_today(staff.shop).strftime("%Y-%m")}


def test_a_pin_session_reads_its_own_job(staff_a: StaffMember, laptop_key: str) -> None:
    # Asha at the counter laptop, logged in by her PIN, the way most of the shop logs in (Jack's screen 1): her own
    # month, by the job the PIN's badge names.
    with shop_context(staff_a.shop_id):
        set_pin(staff_a, PIN, by=None)
    laptop = APIClient()
    laptop.cookies[KEY_COOKIE] = laptop_key
    assert laptop.post(PIN_LOGIN, {"staff": str(staff_a.pk), "pin": PIN}, format="json").status_code == 204
    for route in (DAYS, PAY):
        assert laptop.get(route, this_month(staff_a)).status_code == 200
    assert laptop.get(DAYS, this_month(staff_a)).json()["worker"]["staff"] == str(staff_a.pk)


def test_a_password_session_reads_its_own_job(staff_a: StaffMember) -> None:
    # Juma, a manager paid by the day, on his own phone with his password (Jack: A, the office home's button).
    phone = on_a_phone(staff_a)
    for route in (DAYS, PAY):
        assert phone.get(route, this_month(staff_a)).status_code == 200


def test_a_temporary_password_is_refused(staff_a: StaffMember) -> None:
    # A temporary password opens no office route until its person chooses their own (AUTH-6): this one neither.
    User.objects.filter(pk=staff_a.user_id).update(must_change_password=True)
    for route in (DAYS, PAY):
        answer = on_a_phone(staff_a).get(route, this_month(staff_a))
        assert (answer.status_code, answer.json()["code"]) == (403, "password.must_change")
