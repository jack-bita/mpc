"""apps/sync/tests/test_clock_in.py — the clock document: a tap of Ingia or Toka, pushed by a shop laptop and saved in
the attendance book (ATT-1; 02 §12, 03 §6.3, §6.6).

    sent at once                         → saved with the server's time                     server
    sent later, and the evidence agrees  → saved with the laptop's time                     device_ok
    sent later, and the clock moved back → saved with no trusted time, and a flag           unverified + unverified_time
                                           and the record its time disagrees with (ATT-11)  + disagrees_with
    by a worker suspended meanwhile      → saved, and flagged by the push (SYNC-5)          + suspended_staff_activity
    by anyone working here, any laptop   → no key needed (Jack, ATT-1)
    of a day whose pay is approved       → saved, counted nowhere, and a flag (WAGE-10)       + late_record

Through the push service, as the route runs it, so each test meets the whole path: the list of document types, the
push's own checks, the saving code (apps/staffpay/documents.py) and the time check (apps/staffpay/calculations.py). Here
in `sync`, not `staffpay`, as only the layer above may call the push (ADR-0043); last, two taps from the push to the
book of days (ATT-11); and last, a tap of a day whose pay is approved (WAGE-10). The time check's every case is
apps/staffpay/tests/test_time_check.py's. Fake data only: the repo is public.
"""

import dataclasses
import datetime as dt
import itertools
import uuid
import uuid as _uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.db import transaction
from django.db.models import Model
from django.utils import timezone

from apps.control.models import Flag, FlagKind, FlagPerson
from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, suspend
from apps.shops.models import Setting, Shop, Side
from apps.shops.services import add_side
from apps.staffpay.models import AttendanceEvent, DayStatus, PayRate, PayRun, Payslip, TimeCheck
from apps.staffpay.services import approve_month, pay_month, work_out_days, worker_attendance
from apps.sync.models import PushedDocument
from apps.sync.push import Answer, Sent, push
from tests.concurrency import in_another_transaction, wait_until_someone_waits_for_me

pytestmark = pytest.mark.django_db

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")


def arusha(hour: int, minute: int, second: int = 0) -> dt.datetime:
    # A time on 10 November 2026, as a clock in Arusha shows it.
    return dt.datetime(2026, 11, 10, hour, minute, second, tzinfo=ARUSHA)


# The last time the Dawa laptop had heard from the server that morning, unless a test says otherwise.
LAST_HEARD = arusha(6, 50)


def _clock(
    device_seq: int,
    maker: StaffMember,
    tapped: dt.datetime,
    *,
    kind: str = "in",
    last_server_time: dt.datetime = LAST_HEARD,
) -> Sent:
    # One tap of Ingia (or Toka), as the laptop sends it: made by `maker` at `tapped` by the laptop's clock, which had
    # last heard from the server at `last_server_time`, 06:50 unless said.
    return Sent(
        id=uuid.uuid7(),
        type="clock",
        schema_version=1,
        device_seq=device_seq,
        client_time=tapped,
        created_by=maker.pk,
        payload={"kind": kind, "last_server_time": last_server_time.isoformat()},
    )


def _push(device: Device, documents: Sequence[Sent], *, sent_at: dt.datetime, received_at: dt.datetime) -> list[Answer]:
    # The push as the route runs it: inside the laptop's shop, which its key opened. `sent_at`: the laptop's clock as it
    # sends; `received_at`: the server's as the push arrives.
    with shop_context(device.shop_id):
        return push(
            device,
            documents,
            received_at=received_at,
            sent_at=sent_at,
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )


def _events(shop: Model) -> list[AttendanceEvent]:
    with shop_context(shop):
        return list(AttendanceEvent.objects.order_by("device_seq"))


def _flags(shop: Model, kind: FlagKind) -> list[Flag]:
    with shop_context(shop):
        return list(Flag.objects.filter(kind=kind).order_by("id"))


def _named(flag: Flag) -> list[uuid.UUID]:
    with shop_context(flag.shop_id):
        return list(FlagPerson.objects.filter(flag=flag).values_list("staff_id", flat=True))


def test_online_clock_in_uses_server_time(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Done when #1: the Dawa laptop's clock is 20 minutes slow. Asha taps Ingia at 07:20 by the server's clock, which
    # the laptop shows as 07:00, and it sends two seconds later, so she was online. Her line keeps the laptop's 07:00,
    # but its trusted time is the server's: the push arrived at 07:20:03, less the 2 seconds it waited on the laptop.
    # The clock's mistake costs her nothing.
    [answer] = _push(
        device_a, [_clock(1, staff_a, arusha(7, 0))], sent_at=arusha(7, 0, 2), received_at=arusha(7, 20, 3)
    )
    assert answer.status == "accepted"
    assert answer.posted_seq is not None
    [event] = _events(shop_a)
    assert (event.time_check, event.trusted_time, event.client_time) == (
        TimeCheck.SERVER,
        arusha(7, 20, 1),
        arusha(7, 0),
    )
    # Whose line it is, what she tapped, from which laptop, and the evidence, as the laptop sent it.
    assert (event.staff_id, event.created_by_id, event.kind, event.device_id, event.device_seq) == (
        staff_a.pk,
        staff_a.pk,
        "in",
        device_a.pk,
        1,
    )
    assert (event.last_server_time, event.clock_error) == (LAST_HEARD, dt.timedelta(minutes=-20, seconds=-1))
    assert _flags(shop_a, FlagKind.UNVERIFIED_TIME) == []


def test_offline_clock_in_kept_when_evidence_agrees(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Done when #2: the power went at 07:00. Neema tapped Ingia at 07:05 and Asha at 07:20, by a laptop clock that was
    # right; it sends both at 12:00, when the power comes back. Nothing disagrees: each keeps the laptop's own time.
    taps = [_clock(1, staff_a2, arusha(7, 5)), _clock(2, staff_a, arusha(7, 20))]
    answers = _push(device_a, taps, sent_at=arusha(12, 0), received_at=arusha(12, 0, 1))
    assert [answer.status for answer in answers] == ["accepted", "accepted"]
    assert [(event.time_check, event.trusted_time) for event in _events(shop_a)] == [
        (TimeCheck.DEVICE_OK, arusha(7, 5)),
        (TimeCheck.DEVICE_OK, arusha(7, 20)),
    ]
    assert _flags(shop_a, FlagKind.UNVERIFIED_TIME) == []


def test_clock_moved_back_is_unverified(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Done when #3: offline, Neema taps Ingia at 08:05. Juma comes at 08:10, sets the laptop back to 07:30, taps, and
    # sets it right again. At 12:00 the laptop sends both: Juma's says 07:30, yet it came after Neema's 08:05. His line
    # is kept, with no time trusted, and a flag about it for a manager to decide (02 §12). It names both of them: the
    # server sees that a clock moved between the two taps, not whether it went back for his or forward for hers.
    taps = [_clock(1, staff_a2, arusha(8, 5)), _clock(2, staff_a, arusha(7, 30))]
    neemas, juma = _push(device_a, taps, sent_at=arusha(12, 0), received_at=arusha(12, 0, 1))
    first, second = _events(shop_a)
    assert (first.time_check, second.time_check, second.trusted_time) == (
        TimeCheck.DEVICE_OK,
        TimeCheck.UNVERIFIED,
        None,
    )
    [flag] = _flags(shop_a, FlagKind.UNVERIFIED_TIME)
    assert (flag.subject_type, flag.subject_id, flag.side_id, flag.created_by_id) == (
        "attendance_event",
        second.pk,
        None,
        None,
    )
    assert _named(flag) == [staff_a.pk, staff_a2.pk]
    # The flag is the saving code's own, so it reaches the laptop's answer; Neema's has none.
    assert (neemas.status, neemas.flags) == ("accepted", [])
    assert (juma.status, juma.flags) == ("accepted", [{"id": str(flag.pk), "kind": "unverified_time"}])


def test_a_toka_timed_after_sending_is_unverified(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Juma leaves at 15:00. He takes the laptop off the network, sets it to 17:00, taps Toka, sets it right again and
    # plugs it back in; it sends at 15:01. His Toka says 17:00, after the laptop's own clock as it sent: no time is
    # trusted, and a flag names him, so his early leave can't pass as a full day (ATT-1's review).
    tap = _clock(1, staff_a, arusha(17, 0), kind="out", last_server_time=arusha(14, 0))
    [answer] = _push(device_a, [tap], sent_at=arusha(15, 1), received_at=arusha(15, 1))
    assert answer.status == "accepted"
    [event] = _events(shop_a)
    assert (event.kind, event.time_check, event.trusted_time) == ("out", TimeCheck.UNVERIFIED, None)
    [flag] = _flags(shop_a, FlagKind.UNVERIFIED_TIME)
    assert (flag.subject_id, _named(flag)) == (event.pk, [staff_a.pk])


def test_a_clock_moved_forward_names_both_workers(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Offline afternoon. Juma sets the laptop forward to 17:00, taps Toka, and sets it back to 16:00; then Asha taps
    # Toka, honestly, at 16:00. Her tap is the one that looks wrong, after his "17:00", but the server can't tell
    # which moved: the flag about her line names them both, so a manager checks his too (Jack, ATT-1's review).
    taps = [_clock(1, staff_a2, arusha(17, 0), kind="out"), _clock(2, staff_a, arusha(16, 0), kind="out")]
    _push(device_a, taps, sent_at=arusha(18, 0), received_at=arusha(18, 0))
    jumas, ashas = _events(shop_a)
    assert (jumas.time_check, ashas.time_check) == (TimeCheck.DEVICE_OK, TimeCheck.UNVERIFIED)
    [flag] = _flags(shop_a, FlagKind.UNVERIFIED_TIME)
    assert (flag.subject_id, _named(flag)) == (ashas.pk, [staff_a.pk, staff_a2.pk])


def test_a_clock_in_keeps_the_record_it_disagrees_with(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Juma's Toka says 17:00, then Asha's, the record after it, says 16:00. The flag about hers names him too, but a
    # flag names people, not records: so her tap keeps the id of his, the record its time disagrees with, for the book
    # to send his day to review as well (Jack, ATT-11: A). His own tap disagrees with nothing.
    jumas_toka = _clock(1, staff_a2, arusha(17, 0), kind="out")
    taps = [jumas_toka, _clock(2, staff_a, arusha(16, 0), kind="out")]
    _push(device_a, taps, sent_at=arusha(18, 0), received_at=arusha(18, 0))
    jumas, ashas = _events(shop_a)
    assert (ashas.time_check, ashas.disagrees_with) == (TimeCheck.UNVERIFIED, jumas_toka.id)
    assert (jumas.time_check, jumas.disagrees_with) == (TimeCheck.DEVICE_OK, None)


def test_another_sign_keeps_no_record(
    shop_a: Model, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Neema taps Toka at 14:00. Then Juma takes the laptop off the network, sets it to 17:00, taps Toka, and sets it
    # back; it sends at 15:01. His Toka is unverified for being after the laptop's own clock as it sent, not for
    # disagreeing with Neema's, which came before it with an earlier time: so it keeps no record, and Neema's day is
    # not sent to review for his trick.
    taps = [
        _clock(1, staff_a2, arusha(14, 0), kind="out", last_server_time=arusha(13, 0)),
        _clock(2, staff_a, arusha(17, 0), kind="out", last_server_time=arusha(14, 0)),
    ]
    _push(device_a, taps, sent_at=arusha(15, 1), received_at=arusha(15, 1))
    neemas, jumas = _events(shop_a)
    assert (neemas.time_check, jumas.time_check) == (TimeCheck.DEVICE_OK, TimeCheck.UNVERIFIED)
    assert (neemas.disagrees_with, jumas.disagrees_with) == (None, None)


def test_a_record_before_by_nobody_known_names_only_the_worker(
    shop_a: Model, device_a: Device, staff_a: StaffMember
) -> None:
    # The record before was set aside, its maker no one of this shop, so its line names nobody: the flag names the
    # worker alone, as there is no one else to ask.
    stranger = dataclasses.replace(_clock(1, staff_a, arusha(8, 5)), created_by=uuid.uuid7())
    _push(device_a, [stranger, _clock(2, staff_a, arusha(7, 30))], sent_at=arusha(12, 0), received_at=arusha(12, 0))
    [flag] = _flags(shop_a, FlagKind.UNVERIFIED_TIME)
    assert _named(flag) == [staff_a.pk]


def test_suspended_worker_clock_in_flagged(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Done when #4: Baba suspends Juma. The laptop was offline and didn't know, so its PIN check let him in, and he
    # clocked in an hour later. The line is kept, as every record is, and the push flags who made it (SYNC-5, X2):
    # the clock-in needs no check of its own. Times from now, as the audit trail stamps the suspension with the
    # server's clock.
    with shop_context(shop_a):
        suspend(staff_a, by=None, reason="Uchunguzi wa droo")
    tapped = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    later = tapped + dt.timedelta(hours=3)
    tap = _clock(1, staff_a, tapped, last_server_time=tapped)
    [answer] = _push(device_a, [tap], sent_at=later, received_at=later)
    assert answer.status == "accepted"
    [event] = _events(shop_a)
    assert event.staff_id == staff_a.pk
    [flag] = _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY)
    with shop_context(shop_a):
        # The clock-in's own line in the answer log, found by the document's id: the flag is about it.
        line = PushedDocument.objects.get(document_id=tap.id)
    assert (flag.subject_type, flag.subject_id) == ("pushed_document", line.pk)
    assert _named(flag) == [staff_a.pk]


@pytest.fixture
def foods(shop_a: Shop) -> Side:
    # Shop A's second side, Vyakula.
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


def test_clock_in_needs_no_key_on_any_laptop(
    shop_a: Model, device_a: Device, staff_a: StaffMember, foods: Side, give_role: Any
) -> None:
    # Baraka works on Vyakula. Its laptop is off one morning, so he clocks in on the Dawa laptop, where he holds no
    # key: saved, and no permission_break (Jack, ATT-1).
    give_role(staff_a, RoleTemplate.WORKER, foods)
    [answer] = _push(
        device_a, [_clock(1, staff_a, arusha(7, 20))], sent_at=arusha(7, 20, 2), received_at=arusha(7, 20, 2)
    )
    assert answer.status == "accepted"
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


def test_clock_in_sent_twice_is_saved_once(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # The answer was lost on a bad line, so the laptop sends Juma's clock-in again: one line in the book, one flag, and
    # the first answer again (03 §5.5).
    tap = _clock(1, staff_a, arusha(7, 30), last_server_time=arusha(7, 50))
    [first] = _push(device_a, [tap], sent_at=arusha(12, 0), received_at=arusha(12, 0))
    [again] = _push(device_a, [tap], sent_at=arusha(12, 5), received_at=arusha(12, 5))
    assert (again.status, again.first, again.flags) == ("duplicate", "accepted", first.flags)
    assert len(_events(shop_a)) == 1
    assert len(_flags(shop_a, FlagKind.UNVERIFIED_TIME)) == 1


@pytest.mark.parametrize(
    ("payload", "field", "code"),
    [
        ({"kind": "nap"}, "kind", "invalid_choice"),
        ({"last_server_time": "early"}, "last_server_time", "invalid"),
        ({"last_server_time": None}, "last_server_time", "null"),
        # 06:50 in Arusha with no zone: read as UTC, it would be 09:50 there, and the clock-in flagged for it.
        ({"last_server_time": "2026-11-10T06:50:00"}, "last_server_time", "invalid"),
    ],
    ids=["unknown_kind", "server_time_not_a_time", "no_server_time", "server_time_with_no_zone"],
)
def test_clock_in_of_a_wrong_shape_is_invalid(
    shop_a: Model, device_a: Device, staff_a: StaffMember, payload: dict[str, Any], field: str, code: str
) -> None:
    # A tap the laptop's code wrote wrong is set aside under "needs attention", with the field that is wrong, and
    # nothing goes in the book: there is no time to check.
    tap = _clock(1, staff_a, arusha(7, 20))
    wrong = dataclasses.replace(tap, payload={**tap.payload, **payload})
    [answer] = _push(device_a, [wrong], sent_at=arusha(12, 0), received_at=arusha(12, 0))
    assert (answer.status, answer.fields) == ("invalid", {field: [code]})
    assert _events(shop_a) == []


def test_a_clock_in_from_year_one_never_stops_the_push(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # A laptop's code wrote year 1 as the last server time it had seen. The clock-in is answered like any other, and
    # the record after it is saved too: a crash would answer retry, and every later push of that laptop would stop at
    # this one (ATT-1's review).
    tap = _clock(1, staff_a, arusha(7, 20), last_server_time=dt.datetime(1, 1, 1, tzinfo=dt.UTC))
    answers = _push(
        device_a, [tap, _clock(2, staff_a, arusha(17, 0), kind="out")], sent_at=arusha(18, 0), received_at=arusha(18, 0)
    )
    assert [answer.status for answer in answers] == ["accepted", "accepted"]
    assert len(_events(shop_a)) == 2


@pytest.fixture
def device_b(shop_b: Shop, side_b: Side) -> Device:
    # A laptop of the second shop. Only the row, as device_a is (backend/conftest.py).
    with shop_context(shop_b):
        return Device.objects.create(shop=shop_b, home_side=side_b, name="Laptop B", code=1, key_hash="b" * 64)


def test_a_clock_in_id_another_shop_holds_is_refused(
    shop_a: Model, shop_b: Model, device_a: Device, device_b: Device, staff_a: StaffMember, staff_b: StaffMember
) -> None:
    # Shop B's line has this id already. Shop A's laptop sends a clock-in with the same id: an insert, never an update,
    # so it clashes and is set aside as `id.taken`, telling nothing of B's line, which stays as it was (03 §5.4).
    theirs = _clock(1, staff_b, arusha(7, 20))
    _push(device_b, [theirs], sent_at=arusha(7, 20, 2), received_at=arusha(7, 20, 2))
    ours = dataclasses.replace(theirs, created_by=staff_a.pk, client_time=arusha(9, 0))
    [answer] = _push(device_a, [ours], sent_at=arusha(9, 0, 2), received_at=arusha(9, 0, 2))
    assert (answer.status, answer.code, answer.fields) == ("invalid", "id.taken", {})
    assert _events(shop_a) == []
    [kept] = _events(shop_b)
    assert (kept.staff_id, kept.client_time) == (staff_b.pk, arusha(7, 20))


# From the push to the book of days (ATT-11): the push's two halves the book reads, the suspension's flag on a line in
# the answer log and the record a tap keeps, proven to join, as the book's own tests build each half by hand.


def _worker_since_january(shop: Shop, name: str) -> StaffMember:
    # A worker whose first day was long ago, and attendance switched on long ago (ADR-0033), so 10 November is one of
    # their days: staff_a's first day is today, and every tap before it would need review for that reason alone.
    with shop_context(shop):
        if not Setting.objects.filter(key=ATTENDANCE_ON.key).exists():
            switch = Setting(shop=shop, key=ATTENDANCE_ON.key, value="true", effective_from=dt.date(2026, 1, 1))
            switch.full_clean()
            switch.save()
        user = User.objects.create_user(full_name=f"{name} Demo")
        return add_staff(shop=shop, user=user, display_name=name, started_on=dt.date(2026, 1, 1), by=None)


def _book(shop: Shop, day: dt.date) -> dict[str, str]:
    # Each worker's status on `day`, as the book works it out, by nickname.
    with shop_context(shop):
        return {kept.staff.display_name: kept.status for kept in work_out_days(shop, day, day)}


def test_a_suspended_workers_pushed_tap_sends_its_day_to_review(
    shop_a: Shop, device_a: Device, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Baba suspends Juma on Monday 9 November at 11:00, by the server's clock, which the audit trail stamps (fixed here
    # to that hour). The Dawa laptop, offline, doesn't know: on Tuesday Juma clocks in at 07:20 and out at 18:45, a
    # full day on time by the rule. The push flags the taps on their lines; the book reads those flags, and his Tuesday
    # needs review.
    juma = _worker_since_january(shop_a, "Juma")
    with monkeypatch.context() as clock:
        clock.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 9, 11, 0, tzinfo=ARUSHA))
        with shop_context(shop_a):
            suspend(juma, by=None, reason="Uchunguzi wa droo")
    taps = [_clock(1, juma, arusha(7, 20)), _clock(2, juma, arusha(18, 45), kind="out")]
    _push(device_a, taps, sent_at=arusha(19, 0), received_at=arusha(19, 0))
    assert [event.time_check for event in _events(shop_a)] == [TimeCheck.DEVICE_OK, TimeCheck.DEVICE_OK]
    assert _book(shop_a, arusha(0, 0).date()) == {"Juma": DayStatus.NEEDS_REVIEW}


def test_two_pushed_taps_that_disagree_send_both_days_to_review(shop_a: Shop, device_a: Device) -> None:
    # Tuesday 10 November on the Dawa laptop, offline all day, sent at 19:00. Juma and Asha come at 07:20 and 07:25.
    # Juma's Toka says 18:45, then Asha's, the laptop's next record, says 18:30: a clock moved, and nobody knows
    # whose. Hers has no trusted time; his keeps the laptop's, and alone would be a full day. Her tap keeps his id, and
    # the book sends both days to review (Jack, ATT-11: A).
    juma, asha = _worker_since_january(shop_a, "Juma"), _worker_since_january(shop_a, "Asha")
    taps = [
        _clock(1, juma, arusha(7, 20)),
        _clock(2, asha, arusha(7, 25)),
        _clock(3, juma, arusha(18, 45), kind="out"),
        _clock(4, asha, arusha(18, 30), kind="out"),
    ]
    _push(device_a, taps, sent_at=arusha(19, 0), received_at=arusha(19, 0))
    jumas_toka, ashas_toka = _events(shop_a)[2:]
    assert (jumas_toka.time_check, ashas_toka.disagrees_with) == (TimeCheck.DEVICE_OK, jumas_toka.pk)
    assert _book(shop_a, arusha(0, 0).date()) == {"Asha": DayStatus.NEEDS_REVIEW, "Juma": DayStatus.NEEDS_REVIEW}


# A tap of a day whose pay is approved (WAGE-10): kept, counted nowhere, as that pay never changes (A3), and flagged.

NOVEMBER = dt.date(2026, 11, 1)


def late(hour: int, minute: int) -> dt.datetime:
    # A time on Monday 30 November 2026, in Arusha: the Vyakula laptop's tap, offline over the weekend.
    return dt.datetime(2026, 11, 30, hour, minute, tzinfo=ARUSHA)


# When it is sent: Wednesday 2 December, 09:14, after November's approval.
SENT = dt.datetime(2026, 12, 2, 9, 14, tzinfo=ARUSHA)
HEARD = dt.datetime(2026, 11, 30, 6, 50, tzinfo=ARUSHA)


def _approved(shop: Shop, by: StaffMember) -> None:
    # November approved, as its row says: what closes it for every job (is_closed).
    with shop_context(shop):
        PayRun.objects.create(shop=shop, month=NOVEMBER, created_by=by)


def _late_tap(device: Device, maker: StaffMember, tapped: dt.datetime | None = None, **clock: Any) -> Answer:
    # Her Ingia at 07:20 on the 30th, unless said.
    [answer] = _push(
        device,
        [_clock(1, maker, tapped or late(7, 20), **({"last_server_time": HEARD} | clock))],
        sent_at=SENT,
        received_at=SENT,
    )
    return answer


def test_a_tap_whose_day_is_approved_is_kept_and_flagged(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, staff_a2: StaffMember
) -> None:
    # Asha's Ingia of 30/11 at 07:20 comes on 2/12, after November's approval: the push takes it, as it takes every
    # record, the book keeps it, and Tofauti says so, naming her, on no side, about the tap itself.
    asha = _worker_since_january(shop_a, "Asha")
    _approved(shop_a, staff_a2)
    answer = _late_tap(device_a, asha)
    assert answer.status == "accepted"
    [event] = _events(shop_a)
    assert (event.time_check, event.trusted_time) == (TimeCheck.DEVICE_OK, late(7, 20))
    [flag] = _flags(shop_a, FlagKind.LATE_RECORD)
    assert (flag.subject_id, flag.side_id, _named(flag)) == (event.pk, None, [asha.pk])
    assert [kind for kind in (each["kind"] for each in answer.flags)] == [FlagKind.LATE_RECORD]


def test_a_tap_whose_day_is_open_raises_none(shop_a: Shop, device_a: Device, staff_a2: StaffMember) -> None:
    # November still open: the tap is one more of its taps, and the book reads it. Nothing to say.
    asha = _worker_since_january(shop_a, "Asha")
    _late_tap(device_a, asha)
    assert _flags(shop_a, FlagKind.LATE_RECORD) == []


def test_the_day_is_the_shops_own(shop_a: Shop, device_a: Device, staff_a2: StaffMember) -> None:
    # Asha's Toka at 23:50 on the 30th is November's, approved: flagged. Juma's Ingia at 00:30 on Tuesday 1 December in
    # Arusha, the laptop's next record, is still 30 November by UTC, but December's day by the shop's, still open: no
    # flag.
    asha, juma = _worker_since_january(shop_a, "Asha"), _worker_since_january(shop_a, "Juma")
    _approved(shop_a, staff_a2)
    taps = [
        _clock(1, asha, late(23, 50), kind="out", last_server_time=late(23, 0)),
        _clock(2, juma, dt.datetime(2026, 12, 1, 0, 30, tzinfo=ARUSHA), last_server_time=late(23, 0)),
    ]
    answers = _push(device_a, taps, sent_at=SENT, received_at=SENT)
    assert [[each["kind"] for each in answer.flags] for answer in answers] == [[FlagKind.LATE_RECORD], []]
    [flag] = _flags(shop_a, FlagKind.LATE_RECORD)
    assert _named(flag) == [asha.pk]


def test_a_tap_in_doubt_and_late_raises_both(shop_a: Shop, device_a: Device, staff_a2: StaffMember) -> None:
    # Its time before the last the laptop heard from the server: a clock moved (sign 2), so it is in doubt, and its day,
    # by the laptop's time, is approved. Two flags, the time's first: two things for a manager to look at.
    asha = _worker_since_january(shop_a, "Asha")
    _approved(shop_a, staff_a2)
    answer = _late_tap(device_a, asha, late(6, 0))
    assert [each["kind"] for each in answer.flags] == [FlagKind.UNVERIFIED_TIME, FlagKind.LATE_RECORD]


def test_one_approved_alone_is_flagged_alone(shop_a: Shop, device_a: Device, staff_a2: StaffMember) -> None:
    # Neema was approved alone as she left on the 30th; Asha's November is still open. Both their taps of the 30th come
    # late: only Neema's is flagged, as only her pay of that day is approved.
    asha, neema = _worker_since_january(shop_a, "Asha"), _worker_since_january(shop_a, "Neema")
    with shop_context(shop_a):
        Payslip.objects.create(shop=shop_a, staff=neema, month=NOVEMBER, total=Decimal("10000.00"), created_by=staff_a2)
    taps = [_clock(1, asha, late(7, 20), last_server_time=HEARD), _clock(2, neema, late(7, 25), last_server_time=HEARD)]
    _push(device_a, taps, sent_at=SENT, received_at=SENT)
    [flag] = _flags(shop_a, FlagKind.LATE_RECORD)
    assert _named(flag) == [neema.pk]


# A tap and an approval at the same moment: the tap is counted by the approval, or flagged, never neither.


def _paid_in_november(shop: Shop, name: str) -> StaffMember:
    # A worker paid a made-up 10,000 a day from 1 November, written past set_pay_rate.
    staff = _worker_since_january(shop, name)
    with shop_context(shop):
        PayRate(shop=shop, staff=staff, daily_rate=Decimal("10000.00"), effective_from=NOVEMBER).save()
    return staff


def _ticking(start: dt.datetime) -> Any:
    # A clock that moves a millisecond each time it is read, as a real one does, from `start`: one stopped at a moment
    # would give the approval and the tap kept after it the very same time, and hide their order.
    ticks = itertools.count()
    return lambda: start + dt.timedelta(milliseconds=next(ticks))


def _seen(shop: Shop) -> dict[_uuid.UUID, Decimal]:
    with shop_context(shop):
        return {line.staff_id: line.total for line in pay_month(shop, NOVEMBER).workers}


@pytest.mark.django_db(transaction=True)
def test_a_tap_beside_an_approval_waits_and_is_flagged(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, give_role: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Baba approves November while the Vyakula laptop's push of Asha's tap is on its way: the tap waits for her job's
    # row, which the approval holds, then finds November approved, and is flagged; and her day says it came after the
    # approval, by when it was kept, though the push arrived before it (the review). Without the push's lock it would be
    # read by neither, and her pay would be short with nobody told.
    monkeypatch.setattr(timezone, "now", _ticking(SENT))
    give_role(staff_a, RoleTemplate.OWNER, None)
    asha = _paid_in_november(shop_a, "Asha")
    seen = _seen(shop_a)

    def pushes() -> list[str]:
        return [each["kind"] for each in _late_tap(device_a, asha).flags]

    with shop_context(shop_a), transaction.atomic():
        approve_month(shop_a, NOVEMBER, run_id=_uuid.uuid7(), seen=seen, by=staff_a)
        thread, ended = in_another_transaction(pushes)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == [[FlagKind.LATE_RECORD]]
    with shop_context(shop_a):
        [tap] = worker_attendance(shop_a, asha, NOVEMBER, viewer=None).taps
    assert tap.after_approval is True


@pytest.mark.django_db(transaction=True)
def test_an_approval_beside_a_tap_waits_and_sees_it(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, give_role: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other way round: the push of Asha's Ingia first, not committed yet, and Baba approves the totals he read
    # before it. He waits for it, and the approval reads her 30th with its Ingia and no Toka, a day that waits for a
    # decision: refused, and no flag, as the tap is November's to count.
    monkeypatch.setattr(timezone, "now", lambda: SENT)
    give_role(staff_a, RoleTemplate.OWNER, None)
    asha = _paid_in_november(shop_a, "Asha")
    seen = _seen(shop_a)

    def approves() -> str:
        with shop_context(shop_a):
            try:
                approve_month(shop_a, NOVEMBER, run_id=_uuid.uuid7(), seen=seen, by=staff_a)
            except Exception as refusal:  # the refusal's code, which the test reads
                return str(getattr(refusal, "code", refusal))
        return "approved"

    with transaction.atomic():
        _late_tap(device_a, asha)
        thread, ended = in_another_transaction(approves)
        wait_until_someone_waits_for_me()
    thread.join()
    assert ended == ["pay_run.days_waiting"]
    assert _flags(shop_a, FlagKind.LATE_RECORD) == []
