"""apps/staffpay/tests/test_attendance_event.py — the attendance book: one line per clock-in or clock-out (ATT-1;
02 §12).

    who    in/out  laptop          laptop's time  trusted time  check
    Asha   in      Laptop ya Dawa  07:20          07:20         device_ok    sent later; nothing says the clock moved
    Asha   out     Laptop ya Dawa  17:01          17:01:00      server       sent at once: the server's time of the tap
    Juma   in      Laptop ya Dawa  07:30          —             unverified   a sign the clock moved: a manager decides
    Juma   out     —               —              18:30         entered      added in the office by Baba (ATT-13)

These tests pin the rules the database keeps on it (AttendanceEvent, apps/staffpay/models.py): a line is never changed
or deleted, only voided once, with who and why; its trusted time fits its check; only an unverified one names the
record its time disagrees with; a line is a laptop's, with every fact a laptop gives, or the office's, with none of them
and who entered it and why (ATT-13); and the shop guard. How a clock-in's
time is checked is test_time_check.py's, and how the push saves one is the clock document's tests'. Fake data only:
the repo is public.
"""

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import Model
from django.utils import timezone

from apps.core.models import AppendOnlyError, ShopScoped
from apps.core.tenancy import NoShopSelected, shop_context
from apps.people.models import StaffMember
from apps.staffpay.models import AttendanceEvent, ClockKind, NoPhoto, TimeCheck

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


# Juma's Toka at 18:30 in Arusha, 15:30 in UTC, which Baba added that evening at 19:00 as Juma forgot it (ATT-13).
ENTERED_TIME = dt.datetime(2026, 11, 10, 15, 30, tzinfo=dt.UTC)
ENTERED_AT = dt.datetime(2026, 11, 10, 16, 0, tzinfo=dt.UTC)


def _office_tap(shop: Model, manager: StaffMember, staff: StaffMember, **changes: object) -> AttendanceEvent:
    # A tap a manager entered in the office (ATT-13): no laptop, so none of the facts a laptop gives; who entered it
    # (`created_by`), whose it is (`staff`), when it was entered, the minute typed, trusted, and why. `changes`
    # overrides a fact.
    facts: dict[str, object] = {
        "shop_id": shop.pk,
        "received_at": ENTERED_AT,
        "created_by_id": manager.pk,
        "staff_id": staff.pk,
        "kind": ClockKind.OUT,
        "trusted_time": ENTERED_TIME,
        "time_check": TimeCheck.ENTERED,
        "no_photo": NoPhoto.ENTERED,
        "entry_reason": "Alisahau kubonyeza Toka",
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
    # A reason of spaces alone is no reason (ATT-1's review): the first void table, so it sets the pattern.
    [(False, ""), (True, ""), (False, "Clocked in twice"), (True, "   "), (True, "\t\n")],
    ids=["neither_who_nor_why", "no_why", "no_who", "why_only_spaces", "why_only_tabs_and_lines"],
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
        # Why a tap has no photo: only the reasons there are, or none when its photo came (ATT-3). Short enough for
        # the column, so the rule is what refuses it.
        ({"no_photo": "lost"}, "no_photo_known"),
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
        "unknown_reason_for_no_photo",
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


def test_each_reason_for_no_photo_is_kept(shop_a: Model, device_a: ShopScoped, staff_a: StaffMember) -> None:
    # A tap whose photo came has no reason; one without names why (ATT-3). Each is a line the book keeps. Every reason
    # but `entered`, which only a tap entered in the office gives (ATT-13): below.
    reasons = ["", *(reason for reason in NoPhoto.values if reason != NoPhoto.ENTERED)]
    for device_seq, reason in enumerate(reasons, start=1):
        _event(shop_a, device_a, staff_a, device_seq=device_seq, no_photo=reason).save()
    with shop_context(shop_a):
        assert sorted(AttendanceEvent.objects.values_list("no_photo", flat=True)) == sorted(reasons)


def test_only_an_unverified_tap_disagrees(shop_a: Model, device_a: ShopScoped, staff_a: StaffMember) -> None:
    # Juma's Toka says 18:45, then Asha's says 18:30: her tap keeps the id of his, the record its time disagrees with,
    # and no time is trusted for it (ATT-11). A tap whose time is trusted disagrees with nothing, so a line naming a
    # record and keeping a time, as a bug in the saving code could write it, is refused.
    jumas_toka = uuid.uuid7()
    with (
        pytest.raises(IntegrityError, match="staffpay_attendanceevent_disagrees_only_unverified"),
        transaction.atomic(),
    ):
        _event(shop_a, device_a, staff_a, device_seq=1, disagrees_with=jumas_toka).save()
    ashas = _event(
        shop_a,
        device_a,
        staff_a,
        device_seq=2,
        time_check=TimeCheck.UNVERIFIED,
        trusted_time=None,
        disagrees_with=jumas_toka,
    )
    ashas.save()
    # Written once, with the line, as the rest of it is: the void rule keeps it as it was (ADR-0021), so nobody can
    # later take Juma's day out of review by clearing it.
    with (
        shop_context(shop_a),
        pytest.raises(IntegrityError, match="only the void stamp may change"),
        transaction.atomic(),
    ):
        AttendanceEvent.objects.filter(pk=ashas.pk).update(disagrees_with=None)


def test_a_tap_entered_in_the_office_has_no_laptop(shop_a: Model, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # Juma forgot his Toka, and Baba added it (ATT-13): no laptop made it, numbered it or timed it, so each of those
    # facts is empty, and the line says who entered it, when, at what minute, and why. Its time is the one Baba typed,
    # trusted as a laptop's never is: the book reads it as any other tap. It has no photo, and says so.
    _office_tap(shop_a, staff_a2, staff_a).save()
    with shop_context(shop_a):
        tap = AttendanceEvent.objects.get()
    assert (tap.device_id, tap.device_seq, tap.client_time, tap.last_server_time, tap.clock_error) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert (tap.created_by_id, tap.staff_id, tap.received_at) == (staff_a2.pk, staff_a.pk, ENTERED_AT)
    assert (tap.trusted_time, tap.time_check, tap.no_photo) == (ENTERED_TIME, TimeCheck.ENTERED, NoPhoto.ENTERED)
    assert tap.entry_reason == "Alisahau kubonyeza Toka"


@pytest.mark.parametrize(
    "changes",
    [
        # Who entered it: a line nobody entered would hide who fixed Juma's day (T3).
        {"created_by_id": None},
        # Why: none, or spaces alone, which say nothing, as a void's reason (ATT-1's review).
        {"entry_reason": ""},
        {"entry_reason": "   "},
        {"entry_reason": "\t\n"},
        # A fact only a laptop gives, on a line no laptop made: half one and half the other is a bug in our code.
        {"device_seq": 7},
        {"client_time": ENTERED_TIME},
        {"last_server_time": ENTERED_TIME},
        {"clock_error": dt.timedelta(0)},
        # The office's check with a laptop's photo reason, or a laptop's check on a line with no laptop clock. A
        # laptop's check could otherwise pass the trusted time's own rule: with no laptop time, its comparison is
        # "unknown", which a rule lets through, so this rule is the one that says the line is the office's.
        {"no_photo": NoPhoto.FAILED},
        {"no_photo": ""},
        {"time_check": TimeCheck.DEVICE_OK},
        {"time_check": TimeCheck.SERVER, "clock_error": None},
    ],
    ids=[
        "nobody_entered_it",
        "no_reason",
        "reason_only_spaces",
        "reason_only_tabs_and_lines",
        "a_laptops_number",
        "a_laptops_time",
        "a_last_server_time",
        "a_clock_error",
        "a_laptops_photo_reason",
        "a_photo_said_to_have_come",
        "the_laptops_check",
        "the_servers_check",
    ],
)
def test_a_tap_entered_in_the_office_says_who_and_why_and_nothing_of_a_laptop(
    shop_a: Model, staff_a: StaffMember, staff_a2: StaffMember, changes: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError, match="staffpay_attendanceevent_from_a_laptop_or_the_office"):
        _office_tap(shop_a, staff_a2, staff_a, **changes).save()


def test_a_tap_entered_in_the_office_has_a_device_or_none(
    shop_a: Model, device_a: ShopScoped, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # A laptop named on a line entered in the office: it says a laptop made the line, which none did.
    with pytest.raises(IntegrityError, match="staffpay_attendanceevent_from_a_laptop_or_the_office"):
        _office_tap(shop_a, staff_a2, staff_a, device_id=device_a.pk).save()


@pytest.mark.parametrize(
    "changes",
    [
        # A laptop's line with a reason only the office writes, or the office's check or photo reason.
        {"entry_reason": "Alisahau kubonyeza Toka"},
        {"time_check": TimeCheck.ENTERED},
        {"no_photo": NoPhoto.ENTERED},
        # A laptop's line missing a fact a laptop always gives: each column may be empty now, for the office's lines.
        {"device_id": None},
        {"device_seq": None},
        {"client_time": None, "time_check": TimeCheck.UNVERIFIED, "trusted_time": None},
        {"last_server_time": None},
        {"clock_error": None},
    ],
    ids=[
        "an_entry_reason",
        "the_offices_check",
        "the_offices_photo_reason",
        "no_device",
        "no_number",
        "no_laptop_time",
        "no_last_server_time",
        "no_clock_error",
    ],
)
def test_a_laptops_tap_has_every_fact_a_laptop_gives(
    shop_a: Model, device_a: ShopScoped, staff_a: StaffMember, changes: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError, match="staffpay_attendanceevent_from_a_laptop_or_the_office"):
        _event(shop_a, device_a, staff_a, **changes).save()


def test_a_tap_entered_in_the_office_has_its_time(shop_a: Model, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # The minute Baba typed is the line's only time: one with none would land on no day of the book.
    with pytest.raises(IntegrityError, match="staffpay_attendanceevent_trusted_time_fits_its_check"):
        _office_tap(shop_a, staff_a2, staff_a, trusted_time=None).save()


def test_a_tap_entered_in_the_office_never_changes(shop_a: Model, staff_a: StaffMember, staff_a2: StaffMember) -> None:
    # Why Baba entered it, and the minute he typed, are written once with the line, as the rest of it is (T2): nobody
    # can later rewrite "Alisahau kubonyeza Toka" or move 18:30 to 17:00, whatever sends the change; only the void
    # stamp may be filled (ATT-13's review).
    tap = _office_tap(shop_a, staff_a2, staff_a)
    tap.save()
    with shop_context(shop_a):
        rows = AttendanceEvent.objects.filter(pk=tap.pk)
        for change in ({"entry_reason": "Sababu nyingine"}, {"trusted_time": ENTERED_TIME - dt.timedelta(hours=1)}):
            with pytest.raises(IntegrityError, match="only the void stamp may change"), transaction.atomic():
                rows.update(**change)
    tap.refresh_from_db()
    assert (tap.entry_reason, tap.trusted_time) == ("Alisahau kubonyeza Toka", ENTERED_TIME)


def test_a_tap_entered_in_the_office_is_voided_like_any_other(
    shop_a: Model, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Baba typed 18:30 for 13:30: the line is crossed out with who and why, as a laptop's is, and frozen after (T2).
    tap = _office_tap(shop_a, staff_a2, staff_a)
    tap.save()
    with shop_context(shop_a):
        rows = AttendanceEvent.objects.filter(pk=tap.pk)
        rows.update(voided_at=timezone.now(), voided_by=staff_a2, void_reason="Saa si sahihi")
        with pytest.raises(IntegrityError, match="already voided"), transaction.atomic():
            rows.update(entry_reason="Another reason")
    tap.refresh_from_db()
    assert (tap.voided_by_id, tap.void_reason, tap.entry_reason) == (
        staff_a2.pk,
        "Saa si sahihi",
        "Alisahau kubonyeza Toka",
    )


def test_the_trusted_time_rule_holds_in_any_sessions_time_zone(
    shop_a: Model, device_a: ShopScoped, staff_a: StaffMember
) -> None:
    # A laptop whose clock reset itself 200 days back taps at once: its line keeps a clock error of minus 200 days. The
    # rule must hold however the database session's zone is set, as a restore of a backup may run in any: "a time less
    # a length of time" steps whole days in the session's zone, and in New York 200 days cross summer time, an hour
    # off. So the rule compares two times instead, which no zone moves (ATT-1's second review).
    error = dt.timedelta(days=-200)
    line = _event(
        shop_a,
        device_a,
        staff_a,
        time_check=TimeCheck.SERVER,
        clock_error=error,
        trusted_time=CLIENT_TIME - error,
    )
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'America/New_York'")
        line.save()
        # Back to the zone Django reads in, UTC, before the line is read back: a test runs in one transaction, so the
        # zone would otherwise stay New York's until its end.
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
    with shop_context(shop_a):
        assert AttendanceEvent.objects.get().trusted_time == CLIENT_TIME + dt.timedelta(days=200)


def test_clock_ins_keep_the_shop_guard(shop_a: Model, shop_b: Model, event: AttendanceEvent) -> None:
    # Built on two bases, AppendOnly and CounterRecord: the guard stays the default, as on every shop's table
    # (ADR-0042). A shop's attendance is its own: shop B never sees who came to work at shop A.
    with pytest.raises(NoShopSelected):
        AttendanceEvent.objects.count()
    with shop_context(shop_b):
        assert not AttendanceEvent.objects.exists()
    with shop_context(shop_a):
        assert AttendanceEvent.objects.get() == event
