"""apps/staffpay/tests/test_payslip.py — an approved month, as the database keeps it (WAGE-3; 02 §12, A3): the rules the
tables hold on a pay run, a payslip and its lines (PayRun, Payslip, PayslipLine, apps/staffpay/models.py), and on a day
once a payslip paid it (AttendanceDay.payslip).

    Novemba 2026, approved by Baba
        Juma    14 full × 10,000   140,000
                 2 half ×  5,000    10,000
                 2 fines            −2,000
                                   148,000

All three are ledgers (T2): written once, never changed, deleted or undone. Making them, with who may and when, is the
services' (approve_month and approve_leaver); these tests write rows straight in, as the tables' rules hold whoever
writes. The amounts are made up: the repo is public (rule 10).
"""

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, transaction

from apps.control.models import EditEvent
from apps.core.models import AppendOnlyError
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop
from apps.staffpay.models import AttendanceDay, ClockKind, DayStatus, PayRun, Payslip, PayslipLine, PayslipLineKind
from apps.staffpay.tests.days import job, kept_day, switch_on

pytestmark = pytest.mark.django_db

NOVEMBER = dt.date(2026, 11, 1)
FULL, HALF = PayslipLineKind.FULL, PayslipLineKind.HALF
FINES, MEALS = PayslipLineKind.FINES, PayslipLineKind.MEALS
ADVANCE, CARRIED = PayslipLineKind.ADVANCE, PayslipLineKind.CARRIED
CORRECTION = PayslipLineKind.CORRECTION


def _run(shop: Shop, by: StaffMember | None, month: dt.date = NOVEMBER) -> PayRun:
    return PayRun(shop=shop, month=month, created_by=by)


def _slip(shop: Shop, staff: StaffMember, by: StaffMember | None, **other: Any) -> Payslip:
    return Payslip(
        **{"shop": shop, "staff": staff, "month": NOVEMBER, "total": Decimal("148000.00")} | other, created_by=by
    )


@pytest.fixture
def run(shop_a: Shop, staff_a2: StaffMember) -> PayRun:
    # November, approved by Baba (staff_a2).
    row = _run(shop_a, staff_a2)
    with shop_context(shop_a):
        row.full_clean()
        row.save()
    return row


@pytest.fixture
def slip(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, run: PayRun) -> Payslip:
    # Juma's (staff_a) November.
    row = _slip(shop_a, staff_a, staff_a2, pay_run=run)
    with shop_context(shop_a):
        row.full_clean()
        row.save()
    return row


def test_a_month_is_approved_once(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, run: PayRun) -> None:
    # Baba and Meneja both tap Idhinisha: one run, whoever came first.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_payrun_one_per_month"),
        transaction.atomic(),
    ):
        _run(shop_a, staff_a).save()
    # Another month is another run.
    _run(shop_a, staff_a2, dt.date(2026, 12, 1)).save()


def test_two_shops_approve_the_same_month(shop_b: Shop, staff_b: StaffMember, run: PayRun) -> None:
    _run(shop_b, staff_b).save()


@pytest.mark.parametrize("day", [2, 30])
def test_a_month_is_named_by_its_first_day(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, day: int) -> None:
    # Kept as the 30th as well as the 1st, one November could be approved, or paid, twice.
    month = dt.date(2026, 11, day)
    with pytest.raises(IntegrityError, match="staffpay_payrun_month_by_its_first_day"), transaction.atomic():
        _run(shop_a, staff_a2, month).save()
    with pytest.raises(IntegrityError, match="staffpay_payslip_month_by_its_first_day"), transaction.atomic():
        _slip(shop_a, staff_a, staff_a2, month=month).save()


def test_an_approval_is_somebodys(shop_a: Shop, staff_a: StaffMember) -> None:
    # Never the system's: closing a month is a person's word, and the page names them.
    with pytest.raises(IntegrityError, match="staffpay_payrun_approved_by_someone"), transaction.atomic():
        _run(shop_a, None).save()
    with pytest.raises(IntegrityError, match="staffpay_payslip_approved_by_someone"), transaction.atomic():
        _slip(shop_a, staff_a, None).save()


def test_a_job_is_paid_a_month_once(
    shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember, run: PayRun, slip: Payslip
) -> None:
    # Approved alone as he left, then with the month: the second would pay him twice.
    for pay_run in (run, None):
        with (
            pytest.raises(IntegrityError, match="staffpay_payslip_one_per_job_and_month"),
            transaction.atomic(),
        ):
            _slip(shop_a, staff_a, staff_a2, pay_run=pay_run).save()


def test_one_approved_alone_has_no_run(shop_a: Shop, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # Neema, gone on the 14th: no run of November exists yet, and none is made for her.
    slip = _slip(shop_a, staff_a, staff_a2, total=Decimal("-18000.00"))
    slip.save()
    # A total below 0 is kept as it is: what she owes (debt_left).
    slip.refresh_from_db()
    assert (slip.pay_run_id, slip.total) == (None, Decimal("-18000.00"))


# The lines, each holding what its kind has: (kind, days, each, date, amount).
A_FULL_LINE = (FULL, 14, "10000.00", None, "140000.00")
GOOD_LINES: list[tuple[Any, ...]] = [
    A_FULL_LINE,
    (HALF, 2, "4501.00", None, "9002.00"),
    # Half of a small rate may round to 0, at a shop that rounds to 50: the day is on the payslip all the same.
    (HALF, 1, "0.00", None, "0.00"),
    (FINES, 2, None, None, "-2000.00"),
    (MEALS, 16, None, None, "-16000.00"),
    (ADVANCE, None, None, dt.date(2026, 11, 10), "-20000.00"),
    (CARRIED, None, None, dt.date(2026, 10, 1), "-18000.00"),
    # A correction (WAGE-10): its reason, and money either way.
    (CORRECTION, None, None, None, "9000.00", "Oktoba: siku ya 7/10 haikuhesabiwa"),
    (CORRECTION, None, None, None, "-2000.00", "Oktoba: faini mara mbili"),
]


def _line(slip: Payslip, by: StaffMember, line: tuple[Any, ...], position: int = 1) -> PayslipLine:
    # A line's parts, its note last, on a correction's alone.
    kind, days, each, date, amount, *note = line
    return PayslipLine(
        shop_id=slip.shop_id,
        payslip=slip,
        position=position,
        kind=kind,
        days=days,
        each=None if each is None else Decimal(each),
        date=date,
        amount=Decimal(amount),
        note=note[0] if note else "",
        created_by=by,
    )


def test_a_payslips_lines_are_kept_in_their_order(shop_a: Shop, staff_a2: StaffMember, slip: Payslip) -> None:
    for position, line in enumerate(GOOD_LINES, start=1):
        _line(slip, staff_a2, line, position).save()
    with shop_context(shop_a):
        kept = PayslipLine.objects.filter(payslip=slip).order_by("position")
        assert [(row.kind, row.days, row.date) for row in kept] == [
            (kind, days, date) for kind, days, _, date, *_ in GOOD_LINES
        ]


def test_a_place_on_a_payslip_holds_one_line(staff_a2: StaffMember, slip: Payslip) -> None:
    _line(slip, staff_a2, A_FULL_LINE).save()
    with pytest.raises(IntegrityError, match="staffpay_payslipline_one_per_position"), transaction.atomic():
        _line(slip, staff_a2, (FINES, 2, None, None, "-2000.00")).save()


@pytest.mark.parametrize(
    "line",
    [
        # 14 × 10,000 is 140,000: a line that shows another sum can't be checked with a calculator.
        (FULL, 14, "10000.00", None, "140001.00"),
        (HALF, 2, "4501.00", None, "9001.00"),
        # Days that pay say how many and at what, and pay nobody for owing.
        (FULL, None, "10000.00", None, "10000.00"),
        (FULL, 14, None, None, "140000.00"),
        (FULL, 0, "10000.00", None, "0.00"),
        (FULL, 1, "-10000.00", None, "-10000.00"),
        (FULL, 1, "10000.00", dt.date(2026, 11, 10), "10000.00"),
        # A fine, meals, an advance and a debt take off, never add.
        (FINES, 2, None, None, "2000.00"),
        (FINES, 2, None, None, "0.00"),
        (MEALS, 16, None, None, "16000.00"),
        (ADVANCE, None, None, dt.date(2026, 11, 10), "20000.00"),
        (CARRIED, None, None, dt.date(2026, 10, 1), "18000.00"),
        # Fines and meals say how many days, and nothing else.
        (FINES, None, None, None, "-2000.00"),
        (MEALS, 0, None, None, "-16000.00"),
        (MEALS, 16, "1000.00", None, "-16000.00"),
        (MEALS, 16, None, dt.date(2026, 11, 10), "-16000.00"),
        # An advance says its day, a debt its month by its first day; neither counts days.
        (ADVANCE, None, None, None, "-20000.00"),
        (ADVANCE, 1, None, dt.date(2026, 11, 10), "-20000.00"),
        (ADVANCE, None, "20000.00", dt.date(2026, 11, 10), "-20000.00"),
        (CARRIED, None, None, None, "-18000.00"),
        (CARRIED, None, None, dt.date(2026, 10, 2), "-18000.00"),
        (CARRIED, 1, None, dt.date(2026, 10, 1), "-18000.00"),
        (CARRIED, None, "18000.00", dt.date(2026, 10, 1), "-18000.00"),
        # A correction says why, and corrects something, with nothing else on it (WAGE-10).
        (CORRECTION, None, None, None, "9000.00"),
        (CORRECTION, None, None, None, "9000.00", "   "),
        (CORRECTION, None, None, None, "0.00", "Oktoba: kosa"),
        (CORRECTION, 1, None, None, "9000.00", "Oktoba: kosa"),
        (CORRECTION, None, "9000.00", None, "9000.00", "Oktoba: kosa"),
        (CORRECTION, None, None, dt.date(2026, 10, 7), "9000.00", "Oktoba: kosa"),
        # And no other line has a note.
        (FULL, 14, "10000.00", None, "140000.00", "Kazi nzuri"),
        (FINES, 2, None, None, "-2000.00", "Kosa"),
        (ADVANCE, None, None, dt.date(2026, 11, 10), "-20000.00", "Ada"),
        (CARRIED, None, None, dt.date(2026, 10, 1), "-18000.00", "Deni"),
        # No other kind there is.
        ("bonus", 1, "10000.00", None, "10000.00"),
    ],
)
def test_a_line_holds_what_its_kind_has(staff_a2: StaffMember, slip: Payslip, line: tuple[Any, ...]) -> None:
    with pytest.raises(IntegrityError, match="staffpay_payslipline_fits_its_kind"), transaction.atomic():
        _line(slip, staff_a2, line).save()


def test_an_approved_month_is_never_changed_or_deleted(
    shop_a: Shop, staff_a2: StaffMember, run: PayRun, slip: Payslip
) -> None:
    # T2, A3: Python refuses a second save and a delete; PostgreSQL refuses whatever goes past it. A payslip of 148,000
    # that became 14,800 a year later would show what was never paid.
    line = _line(slip, staff_a2, A_FULL_LINE)
    line.save()
    rows: list[tuple[Any, dict[str, Any]]] = [
        (run, {"month": dt.date(2026, 12, 1)}),
        (slip, {"total": Decimal("14800.00")}),
        (line, {"amount": Decimal("1.00")}),
    ]
    with shop_context(shop_a):
        for row, change in rows:
            for field, value in change.items():
                setattr(row, field, value)
            with pytest.raises(AppendOnlyError):
                row.save()
            with pytest.raises(AppendOnlyError):
                row.delete()
            same = type(row).objects.filter(pk=row.pk)
            with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
                same.update(**change)
            # A bulk delete of a run would meet PROTECT first, as its payslips link to it; this one is the plain DELETE
            # a person might type, which only the trigger is left to refuse.
            with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
                same._raw_delete(using="default")


def test_an_approved_month_is_read_inside_its_own_shop(
    shop_a: Shop, shop_b: Shop, staff_a2: StaffMember, run: PayRun, slip: Payslip
) -> None:
    # The guard (rule 1): shop B sees nothing of A's.
    _line(slip, staff_a2, A_FULL_LINE).save()
    for table in (PayRun, Payslip, PayslipLine):
        with shop_context(shop_a):
            assert table.objects.count() == 1
        with shop_context(shop_b):
            assert not table.objects.exists()


# A day a payslip paid.


@pytest.fixture
def paid_day(shop_a: Shop, device_a: Device, staff_a2: StaffMember, run: PayRun) -> AttendanceDay:
    # Juma's Monday 16 November, on time, then marked as paid by his payslip, as the approval marks it.
    switch_on(shop_a)
    juma = job(shop_a, "Juma")
    day = kept_day(juma, (ClockKind.IN, 7, 20), (ClockKind.OUT, 18, 45))
    slip = _slip(shop_a, juma, staff_a2, pay_run=run)
    slip.save()
    with shop_context(shop_a):
        AttendanceDay.objects.filter(pk=day.pk).update(payslip=slip)
    day.refresh_from_db()
    return day


def test_a_paid_day_never_changes(shop_a: Shop, staff_a2: StaffMember, paid_day: AttendanceDay) -> None:
    # A late tap, a decision, a share split again, or the mark itself taken off: PostgreSQL refuses them all (A3).
    changes: list[dict[str, Any]] = [
        {"status": DayStatus.LATE, "fine": Decimal("500.00")},
        {"meal_share": Decimal("889.00")},
        {"payslip": None},
    ]
    with shop_context(shop_a):
        for change in changes:
            with (
                pytest.raises(IntegrityError, match="frozen, as its payslip_id is filled"),
                transaction.atomic(),
            ):
                AttendanceDay.objects.filter(pk=paid_day.pk).update(**change)
        # And a save of the row, as a decision is saved.
        paid_day.decision_reason = "Alisahau"
        with pytest.raises(IntegrityError, match="frozen"), transaction.atomic():
            paid_day.save(update_fields=["decision_reason"])
        with pytest.raises(IntegrityError, match="refused"), transaction.atomic():
            AttendanceDay.objects.filter(pk=paid_day.pk).delete()


def test_paying_a_day_is_in_its_edit_history(shop_a: Shop, paid_day: AttendanceDay) -> None:
    # The day Juma's Monday was paid, and by which payslip, is one line of the day's history (ADR-0036).
    with shop_context(shop_a):
        last = EditEvent.objects.filter(subject_id=paid_day.pk).order_by("-created_at", "-id").first()
    assert last is not None
    assert last.before["payslip_id"] is None
    assert last.after["payslip_id"] == str(paid_day.payslip_id)
