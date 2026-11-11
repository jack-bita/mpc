"""apps/staffpay/tests/test_attendance_event.py — the attendance book: one line per clock-in or clock-out (ATT-1;
02 §12).

    who    in/out  laptop          laptop's time  trusted time  check
    Asha   in      Laptop ya Dawa  07:20          07:20         device_ok    sent later; nothing says the clock moved
    Asha   out     Laptop ya Dawa  17:01          17:01:00      server       sent at once: the server's time of the tap
    Juma   in      Laptop ya Dawa  07:30          —             unverified   a sign the clock moved: a manager decides

These tests pin the rules the database keeps on it (AttendanceEvent, apps/staffpay/models.py): a line is never changed
or deleted, only voided once, with who and why; its trusted time fits its check; and the shop guard. How a clock-in's
time is checked is test_time_check.py's, and how the push saves one is the clock document's tests'. Fake data only:
the repo is public.
"""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.db.models import Model
from django.utils import timezone

from apps.core.models import AppendOnlyError, ShopScoped
from apps.core.tenancy import NoShopSelected, shop_context
from apps.people.models import StaffMember
from apps.staffpay.models import AttendanceEvent, ClockKind, TimeCheck

pytestmark = pytest.mark.django_db

# Asha clocked in at 07:20 in Arusha by the laptop's clock, 04:20 in UTC; the laptop sent it at 12:00, when its line
# came back. Its clock was 4 seconds fast then, and the last time it had heard from the server was 06:50 (03 §6.6).
CLIENT_TIME = dt.datetime(2026, 11, 10, 4, 20, tzinfo=dt.UTC)
RECEIVED_AT = dt.datetime(2026, 11, 10, 9, 0, tzinfo=dt.UTC)
LAST_SERVER_TIME = dt.datetime(2026, 11, 10, 3, 50, tzinfo=dt.UTC)


def _event(shop: Model, device: ShopScoped, staff: StaffMember, **changes: object) -> AttendanceEvent:
    # Asha's clock-in of the table above, kept with the laptop's time; `changes` overrides a fact.
    facts: dict[str, object] = {
        "shop_id": shop.pk,
        "device_id": device.pk,
        "device_seq": 7,
        "client_time": CLIENT_TIME,
        "received_at": RECEIVED_AT,
        "created_by_id": staff.pk,
        "staff_id": staff.pk,
        "kind": ClockKind.IN,
        "trusted_time": CLIENT_TIME,
        "time_check": TimeCheck.DEVICE_OK,
        "last_server_time": LAST_SERVER_TIME,
        "clock_error": dt.timedelta(seconds=4),
    }
    facts.update(changes)
    return AttendanceEvent(**facts)


@pytest.fixture
def event(shop_a: Model, device_a: ShopScoped, staff_a: StaffMember) -> AttendanceEvent:
    row = _event(shop_a, device_a, staff_a)
    row.save()
    return row


def test_a_clock_in_is_never_changed_or_deleted(shop_a: Model, event: AttendanceEvent) -> None:
    # A late fine is worked out from these lines (ATT-4): one that could change could turn 08:10 into 07:30. Refused in
    # Python, and in PostgreSQL whatever sends the change (ADR-0021).
    event.client_time = CLIENT_TIME - dt.timedelta(minutes=40)
    with pytest.raises(AppendOnlyError):
        event.save()
    with shop_context(shop_a):
        rows = AttendanceEvent.objects.filter(pk=event.pk)
        with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
            rows.update(client_time=CLIENT_TIME - dt.timedelta(minutes=40))
        with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
            rows.delete()
    event.refresh_from_db()
    assert event.client_time == CLIENT_TIME


def test_a_clock_in_is_voided_once(shop_a: Model, staff_a: StaffMember, event: AttendanceEvent) -> None:
    # A clock-in made by mistake is voided, never deleted (T3): stamped once with who, when and why, then frozen, so
    # nobody can later rewrite who voided it, or why.
    with shop_context(shop_a):
        rows = AttendanceEvent.objects.filter(pk=event.pk)
        rows.update(voided_at=timezone.now(), voided_by=staff_a, void_reason="Clocked in twice")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(void_reason="Another reason")
    event.refresh_from_db()
    assert (event.voided_by_id, event.void_reason) == (staff_a.pk, "Clocked in twice")


@pytest.mark.parametrize(
    ("who", "why"),
    [(False, ""), (True, ""), (False, "Clocked in twice")],
    ids=["neither_who_nor_why", "no_why", "no_who"],
)
def test_a_void_says_who_and_why(
    shop_a: Model, staff_a: StaffMember, event: AttendanceEvent, who: bool, why: str
) -> None:
    # T3: a void with no person or no reason would hide what happened to Asha's clock-in. The void rule only checks
    # that the stamp is filled once; this table's own rule checks that it is filled whole (CORE-3's Watch out).
    stamp = {"voided_at": timezone.now(), "void_reason": why, **({"voided_by": staff_a} if who else {})}
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="staffpay_attendanceevent_void_complete"),
        transaction.atomic(),
    ):
        AttendanceEvent.objects.filter(pk=event.pk).update(**stamp)


@pytest.mark.parametrize(
    ("changes", "rule"),
    [
        # Sent at once: the server's time of the tap, whatever the laptop's clock said: the laptop's time less its
        # clock's error, which is the push's arrival less the wait. Neither the laptop's own time, nor the arrival.
        ({"time_check": TimeCheck.SERVER}, "trusted_time_fits_its_check"),
        ({"time_check": TimeCheck.SERVER, "trusted_time": RECEIVED_AT}, "trusted_time_fits_its_check"),
        # With no time at all: a comparison with an empty value is "unknown", which a rule lets pass, so the rule says
        # the time is there (ATT-1's review).
        ({"time_check": TimeCheck.SERVER, "trusted_time": None}, "trusted_time_fits_its_check"),
        # Kept from the laptop: its own time, as nothing said it was wrong.
        ({"trusted_time": RECEIVED_AT}, "trusted_time_fits_its_check"),
        ({"trusted_time": None}, "trusted_time_fits_its_check"),
        # A sign that the clock moved: no time is trusted, and a manager decides (ATT-6).
        ({"time_check": TimeCheck.UNVERIFIED}, "trusted_time_fits_its_check"),
        # Only the three checks there are.
        ({"time_check": "guessed"}, "trusted_time_fits_its_check"),
        # In or out, nothing else: a lunch break is two of these. Three letters, the column's length, so the rule is
        # what refuses it.
        ({"kind": "nap"}, "kind_known"),
    ],
    ids=[
        "server_with_the_laptops_time",
        "server_with_the_arrival_time",
        "server_with_no_time",
        "device_ok_with_the_servers_time",
        "device_ok_with_no_time",
        "unverified_with_a_time",
        "unknown_check",
        "unknown_kind",
    ],
)
def test_a_clock_in_must_make_sense(
    shop_a: Model, device_a: ShopScoped, staff_a: StaffMember, changes: dict[str, object], rule: str
) -> None:
    with pytest.raises(IntegrityError, match=f"staffpay_attendanceevent_{rule}"):
        _event(shop_a, device_a, staff_a, **changes).save()


def test_the_three_checks_each_fit_their_trusted_time(
    shop_a: Model, device_a: ShopScoped, staff_a: StaffMember
) -> None:
    # The table above, each line as its check says: saved, every one.
    _event(shop_a, device_a, staff_a, device_seq=1).save()
    tap_by_the_server = CLIENT_TIME - dt.timedelta(seconds=4)
    _event(shop_a, device_a, staff_a, device_seq=2, time_check=TimeCheck.SERVER, trusted_time=tap_by_the_server).save()
    _event(shop_a, device_a, staff_a, device_seq=3, time_check=TimeCheck.UNVERIFIED, trusted_time=None).save()
    with shop_context(shop_a):
        assert AttendanceEvent.objects.count() == 3


def test_clock_ins_keep_the_shop_guard(shop_a: Model, shop_b: Model, event: AttendanceEvent) -> None:
    # Built on two bases, AppendOnly and CounterRecord: the guard stays the default, as on every shop's table
    # (ADR-0042). A shop's attendance is its own: shop B never sees who came to work at shop A.
    with pytest.raises(NoShopSelected):
        AttendanceEvent.objects.count()
    with shop_context(shop_b):
        assert not AttendanceEvent.objects.exists()
    with shop_context(shop_a):
        assert AttendanceEvent.objects.get() == event
