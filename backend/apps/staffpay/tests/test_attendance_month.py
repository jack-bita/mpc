"""apps/staffpay/tests/test_attendance_month.py — a month of attendance, as the month page shows it (ATT-5; 02 §12).

    Mahudhurio ya mwezi        ‹ Oktoba 2026 ›
    Zinahitaji uamuzi (2)
      Baraka · Ijumaa 02/10 · alifika saa 09:10
      Asha   · Jumanne 06/10 · hakuna Toka
    Asha     ✓ 1   Ch 1   ½ 1   H 23   ! 1
    Baraka   ...

attendance_month (apps/staffpay/services.py) asks the book for the month (work_out_days), and answers a line per worker
with a daily pay rate, with the month's counts, and the days a person must decide, each with why. What a day was is the
book's and the rule's, tested in test_attendance_book.py and test_attendance_day.py; here, only what the month makes of
them. October 2026 starts on a Thursday, and its Sundays are the 4th, 11th, 18th and 25th, so it has 27 working days.
Times are Arusha's. Fake data only: the repo is public, and the amounts are made up (rule 10).
"""

import datetime as dt
import itertools
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, change_worker, mark_left
from apps.shops.models import Setting, Shop
from apps.shops.selectors import shop_today
from apps.staffpay.models import AttendanceDay, AttendanceEvent, ClockKind, DayStatus, ReviewReason, TimeCheck
from apps.staffpay.services import AttendanceMonth, WorkerMonth, attendance_month, set_pay_rate

pytestmark = pytest.mark.django_db

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")
OCTOBER = dt.date(2026, 10, 1)
SEPT_1 = dt.date(2026, 9, 1)
# Each tap's number on the laptop, one after another, as a laptop numbers its records (SYNC-4).
_numbers = itertools.count(1)


def on(day: int, hour: int, minute: int, month: dt.date = OCTOBER) -> dt.datetime:
    # A moment on the shop's clock: on(2, 7, 50) is 07:50 in Arusha on 2 October.
    return dt.datetime(month.year, month.month, day, hour, minute, tzinfo=ARUSHA)


@pytest.fixture
def attendance_on(shop_a: Shop) -> None:
    # The owner switched attendance on long ago (ADR-0033): saved as set_setting saves a rule, but on a day gone by,
    # which the service refuses, as these tests read days gone by (test_attendance_book.py does the same).
    with shop_context(shop_a):
        row = Setting(shop=shop_a, key=ATTENDANCE_ON.key, value="true", effective_from=dt.date(2026, 1, 1))
        row.full_clean()
        row.save()


def worker(shop: Shop, name: str, *, started_on: dt.date = SEPT_1, rate: str | None = "10000") -> StaffMember:
    # A worker, made the way the app makes one, with a made-up daily rate from their first day, or none.
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        staff = add_staff(shop=shop, user=user, display_name=name, started_on=started_on, by=None)
        if rate is not None:
            set_pay_rate(staff, daily_rate=Decimal(rate), effective_from=started_on, by=None)
    return staff


def tap(device: Device, staff: StaffMember, kind: ClockKind, moment: dt.datetime) -> AttendanceEvent:
    # One tap kept in the attendance book, sent later from the laptop, its time the laptop's (`device_ok`, ATT-1).
    event = AttendanceEvent(
        shop_id=device.shop_id,
        device=device,
        device_seq=next(_numbers),
        client_time=moment,
        received_at=moment + dt.timedelta(hours=1),
        created_by=staff,
        staff=staff,
        kind=kind,
        trusted_time=moment,
        time_check=TimeCheck.DEVICE_OK,
        last_server_time=moment - dt.timedelta(minutes=30),
        clock_error=dt.timedelta(0),
        no_photo="demo",
    )
    event.save()
    return event


def came(
    device: Device, staff: StaffMember, day: int, arrives: tuple[int, int], leaves: tuple[int, int] | None
) -> None:
    # A day of taps in October: in at `arrives`, out at `leaves`, or never out.
    tap(device, staff, ClockKind.IN, on(day, *arrives))
    if leaves is not None:
        tap(device, staff, ClockKind.OUT, on(day, *leaves))


def month(shop: Shop, first: dt.date = OCTOBER) -> AttendanceMonth:
    with shop_context(shop):
        return attendance_month(shop, first)


def line_of(answer: AttendanceMonth, name: str) -> WorkerMonth:
    return next(line for line in answer.workers if line.display_name == name)


def test_a_line_per_worker_with_the_months_counts(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Asha's October: on time on the 1st, late on the 2nd, the morning's half on the 5th, an Ingia with no Toka on the
    # 6th, and no tap on the other 23 working days. Its four Sundays are off, and counted nowhere.
    asha = worker(shop_a, "Asha")
    came(device_a, asha, 1, (7, 20), (18, 45))
    came(device_a, asha, 2, (7, 50), (18, 45))
    came(device_a, asha, 5, (7, 20), (13, 10))
    came(device_a, asha, 6, (7, 20), None)
    line = line_of(month(shop_a), "Asha")
    assert line.staff_id == asha.pk
    assert (line.on_time, line.late, line.half, line.needs_review, line.absent) == (1, 1, 1, 1, 23)


def test_only_workers_with_a_pay_rate_are_listed(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Baba, the owner, never clocks in and has no daily rate: the book keeps him absent every working day, but he is
    # not a worker to show (ATT-10's review, Jack: A). Juma has no rate yet either, though he came on time: no rate,
    # no line, as the page lists whom the shop pays by the day (WAGE-1). Asha has one.
    worker(shop_a, "Asha")
    worker(shop_a, "Baba", rate=None)
    juma = worker(shop_a, "Juma", rate=None)
    came(device_a, juma, 1, (7, 20), (18, 45))
    assert [line.display_name for line in month(shop_a).workers] == ["Asha"]


def test_a_rate_from_mid_month_lists_the_worker(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Juma's first rate starts on 15 October: a rate on any day of the month the book answers lists him, with every
    # one of his days counted, as the page shows who came, not what they are paid.
    juma = worker(shop_a, "Juma", rate=None)
    with shop_context(shop_a):
        set_pay_rate(juma, daily_rate=Decimal("10000"), effective_from=dt.date(2026, 10, 15), by=None)
    assert line_of(month(shop_a), "Juma").absent == 27


def test_a_worker_gone_before_the_month_is_not_listed(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Neema left on 30 September. Her rate goes on after her last day (rates_between reads no job's days, WAGE-1's
    # review), but the book answers none of her October days, so she has no line in October, and one in September.
    neema = worker(shop_a, "Neema")
    with shop_context(shop_a):
        mark_left(neema, left_on=dt.date(2026, 9, 30), by=None, reason="Amehamia mji mwingine")
    assert month(shop_a).workers == []
    assert [line.display_name for line in month(shop_a, SEPT_1).workers] == ["Neema"]


def test_the_workers_by_name(shop_a: Shop, attendance_on: None) -> None:
    # One line per worker, by name, whatever order they were added in, so the owner finds Juma where he looks.
    for name in ("Zawadi", "asha", "Baraka"):
        worker(shop_a, name)
    assert [line.display_name for line in month(shop_a).workers] == ["asha", "Baraka", "Zawadi"]


def test_the_days_to_decide_oldest_first_with_why(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Baraka came at 09:10 on the 2nd; on the 6th Asha never tapped Toka, and Baraka left at 15:00. The list runs from
    # the oldest day, and by name on a day, each with why and the taps the rule read, for "alifika saa 09:10".
    asha, baraka = worker(shop_a, "Asha"), worker(shop_a, "Baraka")
    came(device_a, baraka, 2, (9, 10), (18, 45))
    came(device_a, asha, 6, (7, 20), None)
    came(device_a, baraka, 6, (7, 20), (15, 0))
    days = month(shop_a).to_decide
    assert [(day.staff.display_name, day.date.day, day.review_reason) for day in days] == [
        ("Baraka", 2, ReviewReason.CAME_LATE),
        ("Asha", 6, ReviewReason.NO_OUT),
        ("Baraka", 6, ReviewReason.LEFT_EARLY),
    ]
    assert (days[0].first_in, days[0].first_out) == (dt.time(9, 10), dt.time(18, 45))
    assert (days[1].staff_id, days[1].first_out) == (asha.pk, None)


def test_only_listed_workers_days_are_to_decide(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Juma has no rate, and forgot his Toka: his day is in the book, but not on a page that doesn't list him.
    worker(shop_a, "Asha")
    juma = worker(shop_a, "Juma", rate=None)
    came(device_a, juma, 6, (7, 20), None)
    assert month(shop_a).to_decide == []


def test_a_day_kept_but_no_longer_answered_is_not_to_decide(
    shop_a: Shop, device_a: Device, attendance_on: None
) -> None:
    # Neema tapped on 1 October, the day before her first day, so the book kept that day to decide (ATT-11). A manager
    # then voided her tap: the kept row stays as it was, to decide (rule 7), but with no tap the book no longer answers
    # a day outside her job. The list is the book's answer, never a row's status (ATT-11's review), so the day is gone
    # from it. Here the kept row is written as the book left it, and no tap counts.
    neema = worker(shop_a, "Neema", started_on=dt.date(2026, 10, 2))
    with shop_context(shop_a):
        AttendanceDay.objects.create(
            shop=shop_a,
            staff=neema,
            date=dt.date(2026, 10, 1),
            status=DayStatus.NEEDS_REVIEW,
            fine=Decimal("0.00"),
            rules_used={"late_fine": "0.00"},
            review_reason=ReviewReason.OUTSIDE_JOB,
        )
    assert month(shop_a).to_decide == []


def test_a_month_to_come_lists_nobody(shop_a: Shop, attendance_on: None) -> None:
    # No day of next month is over, so the book answers none, and nobody is listed: the page shows its one line.
    worker(shop_a, "Asha", started_on=dt.date(2026, 1, 5))
    next_month = (shop_today(shop_a).replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    answer = month(shop_a, next_month)
    assert (answer.workers, answer.to_decide) == ([], [])


def test_the_month_says_whether_a_working_day_is_over(shop_a: Shop, attendance_on: None) -> None:
    # On 1 December, or on Monday 2 March after a Sunday the 1st, no working day of the month is over, so nobody is
    # listed: the page must then say that no day is over yet, not that nobody is paid by the day (ATT-5's review). The
    # book answers the owner's absent days too, so any working day gone by, with attendance on, says so.
    worker(shop_a, "Asha")
    assert month(shop_a).working_day_over is True
    next_month = (shop_today(shop_a).replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    assert month(shop_a, next_month).working_day_over is False


def test_this_months_counts_reach_yesterday(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Asha came today at 07:20 and hasn't tapped Toka: today is not over, so the book keeps nothing of it, and her day
    # is neither counted nor to decide. Every working day before it, from the 1st to yesterday, is counted, absent.
    today = shop_today(shop_a)
    asha = worker(shop_a, "Asha", started_on=today - dt.timedelta(days=60))
    tap(device_a, asha, ClockKind.IN, dt.datetime.combine(today, dt.time(7, 20), tzinfo=ARUSHA))
    first = today.replace(day=1)
    working = sum(1 for n in range((today - first).days) if (first + dt.timedelta(days=n)).weekday() != 6)
    answer = month(shop_a, first)
    assert answer.today == today
    assert answer.to_decide == []
    if working:
        assert line_of(answer, "Asha").absent == working
    else:
        # The 1st of a month, or the 2nd after a Sunday the 1st: no working day is over yet.
        assert all(line.absent == 0 for line in answer.workers)


def test_any_day_of_the_month_asks_for_the_whole_month(shop_a: Shop, attendance_on: None) -> None:
    # The route sends the month's first day, but a day in the middle names the same month.
    worker(shop_a, "Asha")
    assert line_of(month(shop_a, dt.date(2026, 10, 17)), "Asha").absent == 27


def test_a_month_is_read_in_a_few_queries(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # The month page opens October for three workers: the book's dozen queries, one for the rates, and none per worker
    # or per day, as each day comes with its worker (ATT-10's review).
    for name in ("Asha", "Baraka", "Zawadi"):
        came(device_a, worker(shop_a, name), 6, (7, 20), None)
    with shop_context(shop_a), CaptureQueriesContext(connection) as queries:
        answer = attendance_month(shop_a, OCTOBER)
    assert [day.staff.display_name for day in answer.to_decide] == ["Asha", "Baraka", "Zawadi"]
    assert len(queries) <= 14


def test_the_month_names_the_first_day(shop_a: Shop, attendance_on: None) -> None:
    # The answer says which month it is, by its first day, whatever day it was asked by.
    assert month(shop_a, dt.date(2026, 10, 17)).month == OCTOBER


def test_a_day_moved_out_of_a_job_by_a_change_is_not_counted(
    shop_a: Shop, device_a: Device, attendance_on: None
) -> None:
    # Juma's first day is moved from 1 September to 12 October (PPL-10): his October counts start on the 12th, as the
    # book answers only his days now, and his absent days before it are no longer counted.
    juma = worker(shop_a, "Juma")
    with shop_context(shop_a):
        change_worker(juma, version=juma.version, reason="Alianza tarehe 12", by=None, started_on=dt.date(2026, 10, 12))
    # 12 to 31 October: 20 days, less the 18th and the 25th, two Sundays.
    assert line_of(month(shop_a), "Juma").absent == 18
