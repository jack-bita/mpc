"""apps/sync/tests/test_clock_in.py — the clock document: a tap of Ingia or Toka, pushed by a shop laptop and saved in
the attendance book (ATT-1; 02 §12, 03 §6.3, §6.6).

    sent at once                         → saved with the server's time                     server
    sent later, and the evidence agrees  → saved with the laptop's time                     device_ok
    sent later, and the clock moved back → saved with no trusted time, and a flag           unverified + unverified_time
    by a worker suspended meanwhile      → saved, and flagged by the push (SYNC-5)          + suspended_staff_activity
    by anyone working here, any laptop   → no key needed (Jack, ATT-1)

Through the push service, as the route runs it, so each test meets the whole path: the list of document types, the
push's own checks, the saving code (apps/staffpay/documents.py) and the time check (apps/staffpay/calculations.py).
Here in `sync`, not `staffpay`, as only the layer above may call the push (ADR-0041). The time check's every case is
apps/staffpay/tests/test_time_check.py's. Fake data only: the repo is public.
"""

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.db.models import Model

from apps.control.models import Flag, FlagKind, FlagPerson
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import suspend
from apps.shops.models import Shop, Side
from apps.shops.services import add_side
from apps.staffpay.models import AttendanceEvent, TimeCheck
from apps.sync.models import PushedDocument
from apps.sync.push import Answer, Sent, push

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
    # but its trusted time is the server's, as the push arrived: the clock's mistake costs her nothing.
    [answer] = _push(
        device_a, [_clock(1, staff_a, arusha(7, 0))], sent_at=arusha(7, 0, 2), received_at=arusha(7, 20, 3)
    )
    assert answer.status == "accepted"
    assert answer.posted_seq is not None
    [event] = _events(shop_a)
    assert (event.time_check, event.trusted_time, event.client_time) == (
        TimeCheck.SERVER,
        arusha(7, 20, 3),
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
    # is kept, with no time trusted, and a flag about it, naming him, for a manager to decide (02 §12).
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
    assert _named(flag) == [staff_a.pk]
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


def test_suspended_worker_clock_in_flagged(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Done when #4: Baba suspends Juma. The laptop was offline and didn't know, so its PIN check let him in, and he
    # clocked in an hour later. The line is kept, as every record is, and the push flags who made it (SYNC-5, X2):
    # the clock-in needs no check of its own. Times from now, as the audit trail stamps the suspension with the
    # server's clock.
    with shop_context(shop_a):
        suspend(staff_a, by=None, reason="Uchunguzi wa droo")
        line_count_before = PushedDocument.objects.count()
    tapped = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    later = tapped + dt.timedelta(hours=3)
    [answer] = _push(device_a, [_clock(1, staff_a, tapped, last_server_time=tapped)], sent_at=later, received_at=later)
    assert answer.status == "accepted"
    [event] = _events(shop_a)
    assert event.staff_id == staff_a.pk
    [flag] = _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY)
    with shop_context(shop_a):
        [line] = PushedDocument.objects.all()[line_count_before:]
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
    ours = Sent(**{**theirs.__dict__, "created_by": staff_a.pk, "client_time": arusha(9, 0)})
    [answer] = _push(device_a, [ours], sent_at=arusha(9, 0, 2), received_at=arusha(9, 0, 2))
    assert (answer.status, answer.code, answer.fields) == ("invalid", "id.taken", {})
    assert _events(shop_a) == []
    [kept] = _events(shop_b)
    assert (kept.staff_id, kept.client_time) == (staff_b.pk, arusha(7, 20))
