"""apps/sync/tests/test_carried.py — a record a rescue file carried from a dying laptop to another of the shop (SYNC-12,
03 §6.7), as the push saves it: checked against the laptop that made it, and its line saying where it was made.

    Dawa laptop      #4 Asha 07:00 (sent)       #5 Asha 07:30 (dying, rescued)
    Vyakula laptop   #1 Baraka 10:00 (sent)     #2 = Dawa's #5, loaded by Neema

Dawa's #5 is checked against Dawa's #4, 07:00, not Vyakula's #1, 10:00, which would look like a clock moved back and
hold Asha's hours for a manager, with a flag naming Baraka too (SYNC-12's review).

These tests send pretend "ticket" documents (tests/probe/documents.py) through the push service. Fake data only: the
repo is public.
"""

import dataclasses
import datetime as dt
import uuid
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from django.db.models import Model
from django.utils import timezone

from apps.control.models import Flag, FlagKind, FlagPerson
from apps.core.links import LINK_TYPES
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.people.services import suspend
from apps.shops.models import Shop, Side
from apps.shops.services import add_side
from apps.staffpay.models import AttendanceEvent, TimeCheck
from apps.sync.api.serializers import PushedEnvelope
from apps.sync.document_types import DOCUMENT_TYPES, Document
from apps.sync.models import PushedDocument
from apps.sync.push import Answer, Carried, Sent, push
from tests.probe.documents import TICKET, TICKET_CODE, post_ticket

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

RECEIVED_AT = dt.datetime(2026, 11, 10, 11, 5, tzinfo=dt.UTC)


def _at(hour: int, minute: int = 0) -> dt.datetime:
    # A time on 10 November, by a laptop's clock, in UTC.
    return dt.datetime(2026, 11, 10, hour, minute, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def ticket_type(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pretend ticket on the list of document types, and its table's link type code, for as long as each test runs.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET)
    monkeypatch.setitem(LINK_TYPES, TICKET_CODE, "probe.Ticket")


@pytest.fixture
def handed(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, dt.datetime | None]]:
    # The pretend ticket on the list of document types, its saving code made to note each document's number and the
    # time it was handed of the record before it, in the order handed.
    noted: list[tuple[int, dt.datetime | None]] = []

    def post(document: Document, payload: dict[str, Any]) -> list[Flag]:
        noted.append((document.device_seq, document.time_before))
        return post_ticket(document, payload)

    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, post=post))
    return noted


@pytest.fixture
def vyakula_laptop(shop_a: Shop, side_a: Side) -> Device:
    # A second laptop of shop A: the one the dying Dawa laptop's rescue file is loaded on. Only the row.
    with shop_context(shop_a):
        return Device.objects.create(shop=shop_a, home_side=side_a, name="Laptop ya Vyakula", code=2, key_hash="c" * 64)


@pytest.fixture
def neema(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    # The manager who loads the file: device.manage on the laptops' side, as the laptop asks before its button shows.
    give_role(staff_a2, RoleTemplate.MANAGER, side_a)
    return staff_a2


def _sent(device_seq: int, maker: StaffMember, at: dt.datetime, carried: Carried | None = None) -> Sent:
    # One ticket, its number `device_seq` on the laptop that sends it, made at `at` by the laptop's clock that made it.
    return Sent(
        id=uuid.uuid7(),
        type="ticket",
        schema_version=1,
        device_seq=device_seq,
        client_time=at,
        created_by=maker.pk,
        payload={"text": "2 bags of pumba"},
        carried_from=carried,
    )


def _push(device: Device, documents: Sequence[Sent]) -> list[Answer]:
    # The push as the route runs it, inside the laptop's shop, its clock right as it sends.
    with shop_context(device.shop_id):
        return push(
            device,
            documents,
            received_at=RECEIVED_AT,
            sent_at=RECEIVED_AT,
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )


def _line(shop: Model, sent: Sent) -> PushedDocument:
    with shop_context(shop):
        return PushedDocument.objects.get(document_id=sent.id)


def _flags_naming(shop: Model, kind: FlagKind, person: StaffMember) -> list[Flag]:
    with shop_context(shop):
        named = FlagPerson.objects.filter(staff=person).values("flag")
        return list(Flag.objects.filter(kind=kind, pk__in=named))


def test_a_carried_record_is_checked_against_the_laptop_that_made_it(
    handed: list[tuple[int, dt.datetime | None]],
    device_a: Device,
    vyakula_laptop: Device,
    staff_a: StaffMember,
    neema: StaffMember,
) -> None:
    _push(device_a, [_sent(seq, staff_a, _at(6, seq)) for seq in range(1, 4)] + [_sent(4, staff_a, _at(7))])
    _push(vyakula_laptop, [_sent(1, staff_a, _at(10))])
    rescued = _sent(2, staff_a, _at(7, 30), Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk))

    (answer,) = _push(vyakula_laptop, [rescued])

    assert answer.status == "accepted"
    # Dawa's #4 at 07:00, not Vyakula's #1 at 10:00.
    assert handed[-1] == (2, _at(7))


def test_a_carried_line_says_where_it_was_made_and_who_loaded_it(
    shop_a: Model, device_a: Device, vyakula_laptop: Device, staff_a: StaffMember, neema: StaffMember
) -> None:
    rescued = _sent(2, staff_a, _at(7, 30), Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk))
    _push(vyakula_laptop, [rescued])

    line = _line(shop_a, rescued)
    assert (line.device_id, line.device_seq) == (vyakula_laptop.pk, 2)
    assert (line.carried_from_id, line.carried_seq, line.loaded_by_id) == (device_a.pk, 5, neema.pk)
    # Loaded by a manager: no flag about who loaded it.
    assert _flags_naming(shop_a, FlagKind.PERMISSION_BREAK, neema) == []


def test_a_record_made_here_carries_nothing(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    sent = _sent(1, staff_a, _at(7))
    _push(device_a, [sent])
    line = _line(shop_a, sent)
    assert (line.carried_from_id, line.carried_seq, line.loaded_by_id) == (None, None, None)


def test_the_laptop_that_made_it_reads_it_as_the_record_before_its_next(
    handed: list[tuple[int, dt.datetime | None]],
    device_a: Device,
    vyakula_laptop: Device,
    staff_a: StaffMember,
    neema: StaffMember,
) -> None:
    # Dawa comes back to life: its #5 reached the server from Vyakula, and is still the record before its #6.
    _push(device_a, [_sent(seq, staff_a, _at(7, seq)) for seq in range(1, 5)])
    _push(
        vyakula_laptop,
        [_sent(1, staff_a, _at(7, 30), Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk))],
    )

    _push(device_a, [_sent(6, staff_a, _at(7, 40))])

    assert handed[-1] == (6, _at(7, 30))


def test_the_sending_laptop_leaves_its_carried_lines_out_of_its_own(
    handed: list[tuple[int, dt.datetime | None]],
    device_a: Device,
    vyakula_laptop: Device,
    staff_a: StaffMember,
    neema: StaffMember,
) -> None:
    # A carried line's time is Dawa's clock, which says nothing of Vyakula's: Vyakula's #3 is checked against its #1.
    _push(vyakula_laptop, [_sent(1, staff_a, _at(10))])
    _push(
        vyakula_laptop,
        [_sent(2, staff_a, _at(11), Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk))],
    )

    _push(vyakula_laptop, [_sent(3, staff_a, _at(10, 5))])

    assert handed[-1] == (3, _at(10))


@pytest.mark.parametrize("origin", ["another shop's", "unknown", "the sending laptop itself"])
def test_a_record_carried_from_no_other_laptop_of_this_shop_is_set_aside(
    shop_a: Model,
    shop_b: Shop,
    side_b: Side,
    vyakula_laptop: Device,
    staff_a: StaffMember,
    neema: StaffMember,
    origin: str,
) -> None:
    # One answer for all three, so it tells nothing of another shop's laptops (03 §5.4).
    if origin == "another shop's":
        with shop_context(shop_b):
            elsewhere = Device.objects.create(shop=shop_b, home_side=side_b, name="Laptop B", code=1, key_hash="b" * 64)
        device_id = elsewhere.pk
    elif origin == "unknown":
        device_id = uuid.uuid7()
    else:
        device_id = vyakula_laptop.pk
    sent = _sent(1, staff_a, _at(7), Carried(device=device_id, device_seq=5, loaded_by=neema.pk))

    (answer,) = _push(vyakula_laptop, [sent])

    assert (answer.status, answer.code) == ("invalid", "document.carried_from_unknown")
    # A refused record names nothing more than its reason.
    assert _line(shop_a, sent).carried_from_id is None


def test_a_record_loaded_by_no_one_of_this_shop_is_set_aside(
    shop_a: Model, device_a: Device, vyakula_laptop: Device, staff_a: StaffMember, staff_b: StaffMember
) -> None:
    sent = _sent(1, staff_a, _at(7), Carried(device=device_a.pk, device_seq=5, loaded_by=staff_b.pk))

    (answer,) = _push(vyakula_laptop, [sent])

    assert (answer.status, answer.code) == ("invalid", "document.loaded_by_unknown")


def test_a_loader_without_device_manage_is_flagged_and_the_record_kept(
    shop_a: Model, device_a: Device, vyakula_laptop: Device, staff_a: StaffMember, neema: StaffMember
) -> None:
    # Neema's record, loaded by Asha, who holds no key at all: the laptop shouldn't have let her, as a file edited by
    # hand could clock in a colleague who never came. Kept (accept, then flag), and a flag naming her.
    sent = _sent(1, neema, _at(7), Carried(device=device_a.pk, device_seq=5, loaded_by=staff_a.pk))

    (answer,) = _push(vyakula_laptop, [sent])

    assert answer.status == "accepted"
    (flag,) = _flags_naming(shop_a, FlagKind.PERMISSION_BREAK, staff_a)
    with shop_context(shop_a):
        assert flag.subject_id == _line(shop_a, sent).pk


def test_the_envelope_reads_where_a_carried_record_was_made() -> None:
    # The route's check of one document's envelope: the carried part is read into its own shape, and left out for a
    # record made on the sending laptop, as every app before SYNC-12 sends it.
    envelope = {
        "id": str(uuid.uuid7()),
        "type": "clock",
        "schema_version": 1,
        "device_seq": 141,
        "client_time": "2026-11-10T04:30:00Z",
        "created_by": str(uuid.uuid7()),
        "payload": {},
    }
    plain = PushedEnvelope(data=envelope)
    assert plain.is_valid(), plain.errors
    assert "carried_from" not in plain.validated_data

    origin, loader = uuid.uuid7(), uuid.uuid7()
    carried = PushedEnvelope(
        data={**envelope, "carried_from": {"device": str(origin), "device_seq": 5, "loaded_by": str(loader)}}
    )
    assert carried.is_valid(), carried.errors
    assert carried.validated_data["carried_from"] == Carried(device=origin, device_seq=5, loaded_by=loader)

    broken = PushedEnvelope(
        data={**envelope, "carried_from": {"device": str(origin), "device_seq": 0, "loaded_by": str(loader)}}
    )
    assert not broken.is_valid()
    assert "carried_from" in broken.errors


def test_a_carried_clock_in_waits_for_a_manager_naming_only_its_worker(
    shop_a: Model, device_a: Device, vyakula_laptop: Device, staff_a: StaffMember, neema: StaffMember
) -> None:
    # Asha's 07:30 tap on Dawa, rescued, sent by Vyakula at once, at 07:31: never trusted, as its time came from a file
    # (Jack, SYNC-12's review). The flag names Asha alone: no other record disagreed.
    tapped = dt.datetime(2026, 11, 10, 4, 30, tzinfo=dt.UTC)
    sent = Sent(
        id=uuid.uuid7(),
        type="clock",
        schema_version=1,
        device_seq=1,
        client_time=tapped,
        created_by=staff_a.pk,
        payload={"kind": "in", "last_server_time": "2026-11-10T03:50:00Z"},
        carried_from=Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk),
    )
    with shop_context(vyakula_laptop.shop_id):
        (answer,) = push(
            vyakula_laptop,
            [sent],
            received_at=tapped + dt.timedelta(minutes=1),
            sent_at=tapped + dt.timedelta(minutes=1),
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )

    assert answer.status == "accepted"
    with shop_context(shop_a):
        event = AttendanceEvent.objects.get(pk=sent.id)
        (flag,) = Flag.objects.filter(kind=FlagKind.UNVERIFIED_TIME)
        named = list(FlagPerson.objects.filter(flag=flag).values_list("staff_id", flat=True))
    assert (event.time_check, event.trusted_time) == (TimeCheck.UNVERIFIED, None)
    assert named == [staff_a.pk]


def test_a_loader_who_was_suspended_is_flagged_and_the_record_kept(
    shop_a: Model, device_a: Device, vyakula_laptop: Device, staff_a: StaffMember, neema: StaffMember
) -> None:
    # Neema, a manager, was suspended while the Vyakula laptop was offline, and loaded a file all the same: her key is
    # still given, so only her status shows it. Kept (accept, then flag), and a flag naming her (SYNC-12's second
    # review), as a maker's is (X2).
    with shop_context(shop_a):
        suspend(neema, reason="Fake reason for a test", by=None)
    # The push arrives after her suspension, by the server's clock: the load can have been no later.
    arrived = timezone.now() + dt.timedelta(minutes=1)
    sent = _sent(1, staff_a, _at(7), Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk))

    with shop_context(shop_a):
        (answer,) = push(
            vyakula_laptop,
            [sent],
            received_at=arrived,
            sent_at=arrived,
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )

    assert answer.status == "accepted"
    (flag,) = _flags_naming(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY, neema)
    with shop_context(shop_a):
        assert flag.subject_id == _line(shop_a, sent).pk


def test_a_carried_record_set_aside_keeps_where_it_was_made(
    handed: list[tuple[int, dt.datetime | None]],
    shop_a: Model,
    device_a: Device,
    vyakula_laptop: Device,
    staff_a: StaffMember,
    neema: StaffMember,
) -> None:
    # Dawa's #5, rescued, is of a type this server doesn't take, so it is set aside. Its time is still Dawa's clock:
    # its line keeps where it was made, so Vyakula's next record leaves it out of its own, and Dawa's next reads it as
    # its record before (SYNC-12's second review).
    _push(vyakula_laptop, [_sent(1, staff_a, _at(10))])
    refused = dataclasses.replace(
        _sent(2, staff_a, _at(7, 30), Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk)),
        type="no_such_type",
    )
    (answer,) = _push(vyakula_laptop, [refused])
    assert (answer.status, answer.code) == ("invalid", "document.type_unknown")
    line = _line(shop_a, refused)
    assert (line.carried_from_id, line.carried_seq, line.loaded_by_id) == (device_a.pk, 5, neema.pk)

    _push(vyakula_laptop, [_sent(3, staff_a, _at(10, 5))])
    _push(device_a, [_sent(6, staff_a, _at(7, 40))])

    assert handed[-2:] == [(3, _at(10)), (6, _at(7, 30))]


def test_a_carried_records_maker_is_checked_on_the_side_it_was_made_on(
    shop_a: Shop,
    device_a: Device,
    side_a: Side,
    staff_a: StaffMember,
    staff_a2: StaffMember,
    give_role: GiveRole,
) -> None:
    # Asha sells on Dawa, and holds the ticket's key there only. Her sale, rescued from the Dawa laptop, is sent by a
    # laptop of the Vyakula side, where she holds none: she made it where she held the key, so no flag names her, and
    # any flag about it goes to Dawa's managers (SYNC-12's second review).
    with shop_context(shop_a):
        vyakula = add_side(shop=shop_a, code="F", name="Vyakula", by=None)
        foods_laptop = Device.objects.create(
            shop=shop_a, home_side=vyakula, name="Laptop ya Vyakula", code=2, key_hash="d" * 64
        )
    give_role(staff_a, RoleTemplate.SELLER, side_a)
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    sent = _sent(1, staff_a, _at(7), Carried(device=device_a.pk, device_seq=5, loaded_by=staff_a2.pk))

    (answer,) = _push(foods_laptop, [sent])

    assert answer.status == "accepted"
    assert _flags_naming(shop_a, FlagKind.PERMISSION_BREAK, staff_a) == []
