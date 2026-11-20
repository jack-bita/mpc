"""apps/staffpay/tests/test_worker_month.py — one worker's month, as their calendar and a day of it show it (ATT-12;
02 §12).

    ←  Asha                      Alhamisi 01/10/2026
       Oktoba 2026               ✓ Kwa wakati
       ✓ 1  Ch 1  ½ 0  H 25  ! 0 Ingia  07:20 asubuhi · Laptop ya Dawa · [picha]
       Jt Jn Jtn Al Ij Jm Jp     Toka   18:45 jioni  · Laptop ya Dawa · Hakuna picha: demo
                ✓  Ch …

worker_attendance (apps/staffpay/services.py) asks the book for the month (work_out_days), as the month page does, and
answers one job's days and counts, and every tap of the job in the month, today's too, each with its time on the shop's
clock, its laptop, its photo or why it has none, and whether it is in doubt. What a day was is the book's and the
rule's (test_attendance_book.py, test_attendance_day.py); here, only what a worker's month makes of them. October 2026
starts on a Thursday; its Sundays are the 4th, 11th, 18th and 25th. Times are Arusha's, three hours ahead of UTC. The
fine is a made-up 500 (rule 10). Fake data only: the repo is public.
"""

import datetime as dt
import hashlib
import itertools
import uuid
from decimal import Decimal
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.control.models import Attachment, AttachmentKind, AttachmentType, FlagKind
from apps.control.services import expect_attachment, raise_flag, receive_attachment_file, remove_attachment_file
from apps.core.links import table_of
from apps.core.settings_registry import ATTENDANCE_ON, LATE_FINE, SettingKey
from apps.core.tenancy import ShopMismatch, shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, hire_again, mark_left
from apps.shops.models import Setting, Shop
from apps.shops.selectors import shop_today
from apps.staffpay.models import AttendanceEvent, ClockKind, DayStatus, NoPhoto, ReviewReason, TimeCheck
from apps.staffpay.services import PhotoState, TapLine, WorkerAttendance, worker_attendance

pytestmark = pytest.mark.django_db

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")
OCTOBER = dt.date(2026, 10, 1)
JAN_1 = dt.date(2026, 1, 1)
# Each tap's number on the laptop, one after another, as a laptop numbers its records (SYNC-4).
_numbers = itertools.count(1)


def on(day: int, hour: int, minute: int) -> dt.datetime:
    # A moment on the shop's clock in October: on(2, 7, 50) is 07:50 in Arusha on 2 October.
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=ARUSHA)


def _setting(shop: Shop, key: SettingKey[Any], value: Any) -> None:
    # A rule of the shop's from 1 January, saved as set_setting saves one, but on a day gone by, which the service
    # refuses, as these tests read days gone by (test_attendance_book.py does the same).
    with shop_context(shop):
        row = Setting(shop=shop, key=key.key, value=key.kind.to_text(value), effective_from=JAN_1)
        row.full_clean()
        row.save()


@pytest.fixture
def attendance_on(shop_a: Shop) -> None:
    # The owner switched attendance on in January (ADR-0033), with a made-up first fine of 500.
    _setting(shop_a, ATTENDANCE_ON, True)
    _setting(shop_a, LATE_FINE, Decimal("500"))


def worker(shop: Shop, name: str, started_on: dt.date = dt.date(2026, 9, 1)) -> StaffMember:
    # A worker, made the way the app makes one: create_user, then the people service, inside the shop (PPL-2).
    user = User.objects.create_user(full_name=f"{name} Demo")
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=name, started_on=started_on, by=None)


@pytest.fixture
def asha(shop_a: Shop, attendance_on: None) -> StaffMember:
    return worker(shop_a, "Asha")


@pytest.fixture
def juma(shop_a: Shop, attendance_on: None) -> StaffMember:
    return worker(shop_a, "Juma")


def tap(
    device: Device,
    staff: StaffMember,
    kind: ClockKind,
    moment: dt.datetime,
    *,
    check: TimeCheck = TimeCheck.DEVICE_OK,
    **changes: object,
) -> AttendanceEvent:
    # One tap kept in the attendance book, as the clock document keeps one (ATT-1): `moment` by the laptop's clock,
    # sent later, its time the laptop's (`device_ok`), or with no time trusted (`unverified`).
    facts: dict[str, object] = {
        "shop_id": device.shop_id,
        "device": device,
        "device_seq": next(_numbers),
        "client_time": moment,
        "received_at": moment + dt.timedelta(hours=1),
        "created_by": staff,
        "staff": staff,
        "kind": kind,
        "trusted_time": moment if check == TimeCheck.DEVICE_OK else None,
        "time_check": check,
        "last_server_time": moment - dt.timedelta(minutes=30),
        "clock_error": dt.timedelta(0),
        "no_photo": NoPhoto.DEMO,
    }
    facts.update(changes)
    event = AttendanceEvent(**facts)
    event.save()
    return event


def month_of(shop: Shop, staff: StaffMember, month: dt.date = OCTOBER) -> WorkerAttendance:
    with shop_context(shop):
        return worker_attendance(shop, staff, month)


def tap_of(answer: WorkerAttendance, event: AttendanceEvent) -> TapLine:
    return next(line for line in answer.taps if line.id == event.pk)


def test_the_workers_days_and_counts(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # Asha's October: on time on the 1st, late on the 2nd with the first fine, and no tap on the other 25 working days.
    # Every day of the month the book answers is hers alone, Sundays off; Juma's days, beside her, are not in it.
    tap(device_a, asha, ClockKind.IN, on(1, 7, 20))
    tap(device_a, asha, ClockKind.OUT, on(1, 18, 45))
    tap(device_a, asha, ClockKind.IN, on(2, 7, 50))
    tap(device_a, asha, ClockKind.OUT, on(2, 18, 45))
    tap(device_a, juma, ClockKind.IN, on(1, 7, 20))
    answer = month_of(shop_a, asha)
    line = answer.worker
    assert (line.staff_id, line.display_name, answer.month) == (asha.pk, "Asha", OCTOBER)
    assert (line.on_time, line.late, line.half, line.absent, line.needs_review) == (1, 1, 0, 25, 0)
    days = {day.date: day for day in answer.days}
    assert len(days) == 31
    assert (days[dt.date(2026, 10, 1)].status, days[dt.date(2026, 10, 1)].fine) == (DayStatus.ON_TIME, Decimal("0"))
    assert (days[dt.date(2026, 10, 2)].status, days[dt.date(2026, 10, 2)].fine) == (DayStatus.LATE, Decimal("500"))
    assert days[dt.date(2026, 10, 4)].status == DayStatus.OFF
    assert all(day.reason is None for day in answer.days)
    assert answer.today == shop_today(shop_a)


def test_a_day_to_decide_says_why(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # An Ingia on Tuesday 6 October, and no Toka: the day waits for a decision, and says why, as the month page does.
    tap(device_a, asha, ClockKind.IN, on(6, 7, 20))
    day = next(day for day in month_of(shop_a, asha).days if day.date == dt.date(2026, 10, 6))
    assert (day.status, day.reason, day.fine) == (DayStatus.NEEDS_REVIEW, ReviewReason.NO_OUT, Decimal("0"))
    # The tap the rule read, for a reason that names one: here, when she came.
    assert (day.first_in, day.first_out) == (dt.time(7, 20), None)


def test_each_tap_with_its_time_and_laptop(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha's two taps of 1 October, in the order she made them, each with its minute on the shop's clock, its seconds
    # dropped as the counter showed it, and the laptop's name, as the day shows "Ingia 07:20 asubuhi · Laptop ya Dawa".
    out = tap(device_a, asha, ClockKind.OUT, on(1, 18, 45))
    ingia = tap(device_a, asha, ClockKind.IN, on(1, 7, 20) + dt.timedelta(seconds=40))
    answer = month_of(shop_a, asha)
    assert [line.id for line in answer.taps] == [ingia.pk, out.pk]
    assert tap_of(answer, ingia) == TapLine(
        id=ingia.pk,
        date=dt.date(2026, 10, 1),
        kind=ClockKind.IN,
        time=dt.time(7, 20),
        laptop_time=dt.time(7, 20),
        laptop="Laptop ya Dawa",
        photo=None,
        no_photo=NoPhoto.DEMO,
        doubt=None,
    )


def test_a_tap_falls_on_the_shops_date(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # 21:30 in UTC on 1 October is 00:30 in Arusha on the 2nd: the tap is the 2nd's, at 00:30, never the 1st's.
    late_night = tap(device_a, asha, ClockKind.IN, dt.datetime(2026, 10, 1, 21, 30, tzinfo=dt.UTC))
    line = tap_of(month_of(shop_a, asha), late_night)
    assert (line.date, line.time) == (dt.date(2026, 10, 2), dt.time(0, 30))


def test_a_tap_with_no_trusted_time_shows_the_laptops(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # The laptop's clock moved, so the server trusts no time for this Ingia (`unverified`, ATT-1): the day shows the
    # laptop's own, 07:10, marked as not trusted, on the laptop's date, and the day waits for a decision.
    moved = tap(device_a, asha, ClockKind.IN, on(5, 7, 10), check=TimeCheck.UNVERIFIED)
    answer = month_of(shop_a, asha)
    line = tap_of(answer, moved)
    assert (line.date, line.time, line.laptop_time) == (dt.date(2026, 10, 5), None, dt.time(7, 10))
    day = next(day for day in answer.days if day.date == dt.date(2026, 10, 5))
    assert day.reason == ReviewReason.TIME_UNKNOWN


def _photo_of(event: AttendanceEvent, *, sent: bool = True) -> uuid.UUID:
    # The tap's clock-in photo, its row written as the clock document writes it (expect_attachment), and its file sent
    # after it, as the laptop does (CTRL-6), unless `sent` is False: the file hasn't come yet.
    photo = b"\xff\xd8\xff" + f"made-up photo of tap {event.pk}".encode()
    photo_id = uuid.uuid7()
    with shop_context(event.shop_id):
        expect_attachment(
            id=photo_id,
            kind=AttachmentKind.CLOCK_PHOTO,
            subject=event,
            content_type=AttachmentType.JPEG,
            size=len(photo),
            sha256=hashlib.sha256(photo).hexdigest(),
            by=event.staff,
            device=event.device,
        )
        if sent:
            receive_attachment_file(photo_id, content=photo)
    return photo_id


def test_a_photo_kept_waiting_or_removed(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Three clock-ins with a photo each: one whose file came, one whose file the laptop hasn't sent yet, and one whose
    # file was taken away (90 days after its pay run, ATT-7). The page shows only the first, and says what became of
    # the other two, never a broken picture. A tap with a photo has no reason for none.
    kept = tap(device_a, asha, ClockKind.IN, on(1, 7, 20), no_photo="")
    waiting = tap(device_a, asha, ClockKind.IN, on(2, 7, 20), no_photo="")
    removed = tap(device_a, asha, ClockKind.IN, on(5, 7, 20), no_photo="")
    kept_id, waiting_id, removed_id = _photo_of(kept), _photo_of(waiting, sent=False), _photo_of(removed)
    with shop_context(shop_a):
        remove_attachment_file(Attachment.objects.get(pk=removed_id), reason="Siku 90 baada ya malipo")
    answer = month_of(shop_a, asha)
    photos = {line.id: (line.photo.id, line.photo.state) for line in answer.taps if line.photo is not None}
    assert photos == {
        kept.pk: (kept_id, PhotoState.KEPT),
        waiting.pk: (waiting_id, PhotoState.WAITING),
        removed.pk: (removed_id, PhotoState.REMOVED),
    }
    assert all(line.no_photo is None for line in answer.taps)


def test_a_tap_with_no_photo_says_why(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Someone told the browser to block the camera: the tap is kept with its reason (ATT-3), and no photo.
    blocked = tap(device_a, asha, ClockKind.IN, on(1, 7, 20), no_photo=NoPhoto.BLOCKED)
    line = tap_of(month_of(shop_a, asha), blocked)
    assert (line.photo, line.no_photo) == (None, NoPhoto.BLOCKED)


def _flag_its_line(event: AttendanceEvent) -> None:
    # The push's flag on the tap's line in the answer log, as it raises one when the tap's maker wasn't working (X2):
    # the line's document_id is the tap's own id. The log is a table of `sync`, a layer above `staffpay`, so it is named
    # by its link code, never imported (ADR-0043), as the book reads it (test_attendance_book.py writes it the same).
    answer_log = cast(Any, table_of("pushed_document"))
    with shop_context(event.shop_id):
        line = answer_log.objects.create(
            shop_id=event.shop_id,
            device=event.device,
            device_seq=event.device_seq,
            client_time=event.client_time,
            received_at=event.received_at,
            created_by=event.created_by,
            document_id=event.pk,
            type="clock",
            schema_version=2,
            status="accepted",
        )
        raise_flag(kind=FlagKind.SUSPENDED_STAFF_ACTIVITY, subject=line, people=[event.staff], by=None)


def test_a_suspended_workers_tap_says_so(shop_a: Shop, device_a: Device, juma: StaffMember) -> None:
    # Baba suspended Juma; the Dawa laptop, offline, let his Ingia of Tuesday 6 October through, and the push flagged
    # it (X2). The day waits for a decision, and the tap itself says why, on its own line, so the owner sees which tap.
    ingia = tap(device_a, juma, ClockKind.IN, on(6, 7, 20))
    out = tap(device_a, juma, ClockKind.OUT, on(6, 18, 45))
    _flag_its_line(ingia)
    answer = month_of(shop_a, juma)
    assert (tap_of(answer, ingia).doubt, tap_of(answer, out).doubt) == (ReviewReason.NOT_WORKING, None)
    day = next(day for day in answer.days if day.date == dt.date(2026, 10, 6))
    assert day.reason == ReviewReason.NOT_WORKING


def test_the_tap_a_later_one_disagrees_with_says_so(
    shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember
) -> None:
    # Juma's Toka says 18:45, then Asha's, the laptop's next record, says 18:30: a clock moved between the two, and
    # nobody knows whose (ATT-11). Her tap has no trusted time; his is the one in doubt, and says so on its line.
    jumas_toka = tap(device_a, juma, ClockKind.OUT, on(6, 18, 45))
    tap(device_a, asha, ClockKind.OUT, on(6, 18, 30), check=TimeCheck.UNVERIFIED, disagrees_with=jumas_toka.pk)
    answer = month_of(shop_a, juma)
    assert tap_of(answer, jumas_toka).doubt == ReviewReason.CLOCK_DISAGREES
    day = next(day for day in answer.days if day.date == dt.date(2026, 10, 6))
    assert day.reason == ReviewReason.CLOCK_DISAGREES


def test_a_voided_tap_is_left_out(shop_a: Shop, device_a: Device, asha: StaffMember, staff_a: StaffMember) -> None:
    # A clock-in tapped twice by mistake, the second voided by a manager (ATT-6): it counts for nothing (T2), so the
    # day doesn't show it, as the book doesn't read it. ATT-6 shows voided taps, crossed out (A2).
    first = tap(device_a, asha, ClockKind.IN, on(1, 7, 20))
    tap(
        device_a,
        asha,
        ClockKind.IN,
        on(1, 7, 21),
        voided_at=on(1, 9, 0),
        voided_by=staff_a,
        void_reason="Aliingia mara mbili",
    )
    assert [line.id for line in month_of(shop_a, asha).taps] == [first.pk]


def test_todays_taps_show_though_the_day_isnt_over(shop_a: Shop, device_a: Device, asha: StaffMember) -> None:
    # Asha came in a minute ago. The book keeps no day until it is over (ATT-10), so today has no day yet, but her tap
    # is there, as it comes, for the day under the calendar to show.
    now = timezone.now() - dt.timedelta(minutes=1)
    ingia = tap(device_a, asha, ClockKind.IN, now)
    today = shop_today(shop_a)
    answer = month_of(shop_a, asha, today.replace(day=1))
    assert tap_of(answer, ingia).date == today
    assert today not in {day.date for day in answer.days}


def test_the_jobs_days_and_a_tap_outside_them(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Neema's first day is Saturday 10 October, but she tapped on Thursday the 8th: the book answers that day too, to
    # decide (ATT-11), and the answer gives her first and last day, for the day to say why. No day before the 8th.
    neema = worker(shop_a, "Neema", started_on=dt.date(2026, 10, 10))
    tap(device_a, neema, ClockKind.IN, on(8, 7, 20))
    tap(device_a, neema, ClockKind.OUT, on(8, 18, 45))
    answer = month_of(shop_a, neema)
    assert (answer.started_on, answer.left_on) == (dt.date(2026, 10, 10), None)
    assert min(day.date for day in answer.days) == dt.date(2026, 10, 8)
    eighth = next(day for day in answer.days if day.date == dt.date(2026, 10, 8))
    assert eighth.reason == ReviewReason.OUTSIDE_JOB
    assert dt.date(2026, 10, 9) not in {day.date for day in answer.days}


def test_a_person_hired_again_keeps_each_jobs_month_apart(shop_a: Shop, device_a: Device, attendance_on: None) -> None:
    # Baraka left on Friday 9 October and Baba hired him again from Monday the 19th (PPL-11): one person, two jobs, so
    # two lines of one name on the month page (ATT-5's review), each opening its own job's calendar. The first job's
    # taps and days never show on the second's, nor the second's on the first's.
    old = worker(shop_a, "Baraka")
    with shop_context(shop_a):
        mark_left(old, left_on=dt.date(2026, 10, 9), by=None, reason="Ameacha kazi")
        old.refresh_from_db()
        new = hire_again(old, display_name="Baraka", started_on=dt.date(2026, 10, 19), by=None)
    before = tap(device_a, old, ClockKind.IN, on(1, 7, 20))
    after = tap(device_a, new, ClockKind.IN, on(20, 7, 20))
    first_job, second_job = month_of(shop_a, old), month_of(shop_a, new)
    assert [line.id for line in first_job.taps] == [before.pk]
    assert [line.id for line in second_job.taps] == [after.pk]
    # Each job's days are its own: the first's end on the 9th, the second's start on the 19th.
    assert max(day.date for day in first_job.days) == dt.date(2026, 10, 9)
    assert min(day.date for day in second_job.days) == dt.date(2026, 10, 19)
    assert (first_job.left_on, second_job.started_on) == (dt.date(2026, 10, 9), dt.date(2026, 10, 19))


def test_a_month_in_a_few_queries(shop_a: Shop, device_a: Device, asha: StaffMember, juma: StaffMember) -> None:
    # Asha tapped on two days, Juma on ten, each tap with its photo: their months take as many queries, whatever the
    # number of taps, as each tap's laptop, doubt and photo come in the month's reads, never one read per tap. Asked a
    # second time, as the book writes the month's days on the first (ATT-5's review).
    for staff, days in ((asha, range(1, 3)), (juma, range(1, 11))):
        for day in days:
            event = tap(device_a, staff, ClockKind.IN, on(day, 7, 20), no_photo="")
            _photo_of(event)
    month_of(shop_a, asha)
    counts = []
    for staff in (asha, juma):
        with CaptureQueriesContext(connection) as queries:
            month_of(shop_a, staff)
        counts.append(len(queries))
    assert counts[0] == counts[1]


def test_another_shops_worker_is_refused(shop_a: Shop, shop_b: Shop, attendance_on: None) -> None:
    # A job of shop B, asked for inside shop A: refused loudly, never answered with shop A's taps (T1). The route never
    # sends one, as its worker is found through the guard (test_worker_month_route.py).
    bahati = worker(shop_b, "Bahati")
    with shop_context(shop_a), pytest.raises(ShopMismatch):
        worker_attendance(shop_a, bahati, OCTOBER)
