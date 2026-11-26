"""apps/staffpay/tests/test_who_is_paid.py — the pay, as Mishahara and a payslip read it once it is handed out (WAGE-9;
02 §12): each payslip's payments, crossed out ones too, and the month's Bado kulipa (pay_month and worker_pay,
apps/staffpay/services/pay.py).

    Novemba 2026, approved by Baba on 1 Dec, read on the 1st at 19:05
        Jumla ya wote   20,000
        Bado kulipa     10,000
        Asha            10,000   Amelipwa taslimu na Baba, her signature
        Juma            10,000   Hajalipwa                 ← a payment by M-Pesa crossed out, struck through

The months are approved as WAGE-3 does it, through approve_month, and paid through pay_payslip, as the pages do. The
amounts are made up: the repo is public (rule 10).
"""

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pytest_django import Settings

from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import mark_left
from apps.shops.models import Shop, Side
from apps.staffpay.models import ClockKind, PaymentMethod, Payslip, PayslipPayment
from apps.staffpay.services import (
    PayMonth,
    WorkerPay,
    approve_leaver,
    approve_month,
    pay_month,
    pay_payslip,
    record_advance,
    set_pay_rate,
    void_payslip_payment,
    worker_pay,
)
from apps.staffpay.tests.days import job, kept_day, rule

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

NOVEMBER = dt.date(2026, 11, 1)
MON = dt.date(2026, 11, 16)
FULL = ((ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
DRAWING = b"\xff\xd8\xff\xe0" + b"Asha's signature, made up " * 20
NOTHING = Decimal("0.00")


@pytest.fixture(autouse=True)
def first_of_december(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, device_a: Device) -> None:
    # 19:05 on Tuesday 1 December in Arusha. Attendance is on from 1 November; the laptop sent something this evening.
    moment = dt.datetime(2026, 12, 1, 19, 5, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: moment)
    rule(shop_a, ATTENDANCE_ON, True, NOVEMBER)
    with shop_context(shop_a):
        Device.objects.update(last_synced_at=timezone.now())


@pytest.fixture
def baba(shop_a: Shop, give_role: GiveRole) -> StaffMember:
    staff = job(shop_a, "Baba")
    give_role(staff, RoleTemplate.OWNER, None)
    return staff


def paid_by_day(shop: Shop, name: str) -> StaffMember:
    # A worker since January, at a made-up 10,000 a day from 1 November, with one full day, Monday the 16th.
    staff = job(shop, name)
    with shop_context(shop):
        set_pay_rate(staff, daily_rate=Decimal("10000"), effective_from=NOVEMBER, by=None)
    kept_day(staff, *FULL, date=MON)
    return staff


def month(shop: Shop) -> PayMonth:
    with shop_context(shop):
        return pay_month(shop, NOVEMBER)


def line_of(answer: PayMonth, name: str) -> WorkerPay:
    return next(worker for worker in answer.workers if worker.display_name == name)


def approve(shop: Shop, by: StaffMember) -> None:
    with shop_context(shop):
        shown = {line.staff_id: line.total for line in pay_month(shop, NOVEMBER).workers}
        approve_month(shop, NOVEMBER, run_id=uuid.uuid7(), seen=shown, by=by)


def slip_of(staff: StaffMember) -> Payslip:
    with shop_context(staff.shop_id):
        return Payslip.objects.get(staff=staff, month=NOVEMBER)


def in_cash(staff: StaffMember, by: StaffMember) -> PayslipPayment:
    with shop_context(staff.shop_id):
        return pay_payslip(
            slip_of(staff),
            payment_id=uuid.uuid7(),
            method=PaymentMethod.CASH,
            signature_id=uuid.uuid7(),
            signature=DRAWING,
            by=by,
        )


def by_mpesa(staff: StaffMember, by: StaffMember, number: str = "QK7H2M9XPL") -> PayslipPayment:
    with shop_context(staff.shop_id):
        return pay_payslip(
            slip_of(staff), payment_id=uuid.uuid7(), method=PaymentMethod.MOBILE_MONEY, reference=number, by=by
        )


def test_an_approved_month_says_who_is_paid(shop_a: Shop, baba: StaffMember) -> None:
    # Asha paid in cash with her signature; Juma's M-Pesa payment crossed out, so he is not paid: Bado kulipa is his.
    asha, juma = paid_by_day(shop_a, "Asha"), paid_by_day(shop_a, "Juma")
    approve(shop_a, baba)
    cash = in_cash(asha, baba)
    wrong = by_mpesa(juma, baba)
    with shop_context(shop_a):
        void_payslip_payment(wrong, reason="Nilibonyeza mfanyakazi mwingine", by=baba)

    answer = month(shop_a)

    assert (answer.total, answer.still_to_pay) == (Decimal("20000.00"), Decimal("10000.00"))
    asha_line, juma_line = line_of(answer, "Asha"), line_of(answer, "Juma")
    assert asha_line.payslip_id == slip_of(asha).pk
    [made] = asha_line.payments
    assert made == asha_line.payment
    assert (made.id, made.method, made.amount, made.by, made.reference, made.voided) == (
        cash.pk,
        PaymentMethod.CASH,
        Decimal("10000.00"),
        "Baba",
        "",
        None,
    )
    assert made.signature_id is not None and made.no_signature == ""
    assert asha_line.to_hand_out == NOTHING
    [struck] = juma_line.payments
    assert juma_line.payment is None and juma_line.to_hand_out == Decimal("10000.00")
    assert (struck.reference, struck.signature_id) == ("QK7H2M9XPL", None)
    assert struck.voided is not None
    assert (struck.voided.by, struck.voided.reason) == ("Baba", "Nilibonyeza mfanyakazi mwingine")


def test_once_each_is_paid_nothing_is_left(monkeypatch: pytest.MonkeyPatch, shop_a: Shop, baba: StaffMember) -> None:
    # Wote wamelipwa: Bado kulipa comes to 0 once the last one is paid; and the crossed-out payment before the real one
    # stays on the line, in the order made: the real one five minutes later, at 19:10.
    asha = paid_by_day(shop_a, "Asha")
    approve(shop_a, baba)
    assert month(shop_a).still_to_pay == Decimal("10000.00")
    wrong = by_mpesa(asha, baba)
    with shop_context(shop_a):
        void_payslip_payment(wrong, reason="Namba si sahihi", by=baba)
    later = dt.datetime(2026, 12, 1, 19, 10, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    monkeypatch.setattr(timezone, "now", lambda: later)
    right = by_mpesa(asha, baba, "QK7H2N4ZTR")

    answer = month(shop_a)

    assert answer.still_to_pay == NOTHING
    line = line_of(answer, "Asha")
    assert [made.id for made in line.payments] == [wrong.pk, right.pk]
    assert line.payment is not None and line.payment.id == right.pk


def test_one_who_owes_is_nothing_to_hand_out(shop_a: Shop, baba: StaffMember) -> None:
    # Juma took 15,000 before payday on a 10,000 month: paid 0, so nothing is left to hand him, and he has no Lipa.
    juma = paid_by_day(shop_a, "Juma")
    with shop_context(shop_a):
        record_advance(juma, advance_id=uuid.uuid7(), date=MON, amount=Decimal("15000"), by=baba)
    approve(shop_a, baba)

    answer = month(shop_a)

    assert (answer.total, answer.still_to_pay) == (NOTHING, NOTHING)
    assert line_of(answer, "Juma").to_hand_out == NOTHING


def test_an_open_month_has_no_bado_kulipa(shop_a: Shop, baba: StaffMember) -> None:
    # Its payslips aren't kept yet: nothing to hand out, and no payslip on the line.
    paid_by_day(shop_a, "Asha")
    answer = month(shop_a)
    assert answer.still_to_pay is None
    line = line_of(answer, "Asha")
    assert (line.payslip_id, line.payments, line.to_hand_out) == (None, (), NOTHING)


def test_one_who_left_is_paid_the_evening_they_go(
    monkeypatch: pytest.MonkeyPatch, shop_a: Shop, baba: StaffMember
) -> None:
    # Neema leaves on 14 November, is approved alone, and paid that evening: the month, still open, shows her paid.
    monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 14, 19, 0, tzinfo=dt.UTC))
    neema = job(shop_a, "Neema")
    with shop_context(shop_a):
        set_pay_rate(neema, daily_rate=Decimal("10000"), effective_from=NOVEMBER, by=None)
    kept_day(neema, *FULL, date=dt.date(2026, 11, 13))
    with shop_context(shop_a):
        mark_left(neema, left_on=dt.date(2026, 11, 13), by=None, reason="Ameacha kazi")
        total = worker_pay(shop_a, neema, NOVEMBER).worker.total
        approve_leaver(neema, NOVEMBER, payslip_id=uuid.uuid7(), seen=total, by=baba)
    made = by_mpesa(neema, baba)

    with shop_context(shop_a):
        mine = worker_pay(shop_a, neema, NOVEMBER)
    answer = month(shop_a)

    assert mine.worker.payment is not None and mine.worker.payment.id == made.pk
    assert line_of(answer, "Neema").payment is not None
    assert answer.still_to_pay is None


def test_the_ready_reasons_come_on_the_demo(settings: Settings, shop_a: Shop, baba: StaffMember) -> None:
    # The sheet that crosses one out offers the demo's ready reason, and none elsewhere, where it is typed.
    asha = paid_by_day(shop_a, "Asha")
    with shop_context(shop_a):
        assert worker_pay(shop_a, asha, NOVEMBER).void_reasons == ()
        settings.DEMO_SEED = True
        assert worker_pay(shop_a, asha, NOVEMBER).void_reasons == ("marked_by_mistake",)


def test_who_is_paid_is_read_in_a_few_queries(shop_a: Shop, baba: StaffMember) -> None:
    # The run, the payslips, their lines, their payments and the signatures: five, whatever the number of workers or
    # payments. Nothing is locked or written.
    names = ("Asha", "Baraka", "Juma", "Zawadi")
    workers = [paid_by_day(shop_a, name) for name in names]
    approve(shop_a, baba)
    in_cash(workers[0], baba)
    by_mpesa(workers[1], baba)
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        answer = pay_month(shop_a, NOVEMBER)
    assert len(answer.workers) == 4
    assert len(queries) <= 5
    assert all(query["sql"].startswith("SELECT") and "FOR NO KEY UPDATE" not in query["sql"] for query in queries)
