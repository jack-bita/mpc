"""apps/sync/tests/test_maker_checks.py — the checks a pushed record's maker gets again on the server (SYNC-5; 02 §16
X1, X2; 03 §6.3).

The laptop checked them at the counter, offline, against its copy of the shop: who holds which key, who is
suspended. That copy can be old, and a laptop can be tampered with, so the server checks again, and a broken rule
never refuses the record (accept, then flag):

    Asha sells on the Dawa laptop, and holds sale.write on Dawa            saved, nothing more
    Juma sells on the Dawa laptop, and holds no sale.write there           saved + permission_break, naming Juma

Each type of document names the key its maker needs (DocumentType.permission, apps/sync/document_types.py), checked on
the laptop's own side, among the keys the person was given. And a record made while its maker wasn't working here,
suspended or gone, is flagged too:

    Baba suspends Juma at 11:00; Juma sells at 12:00 on a laptop still offline   saved + suspended_staff_activity
    Juma sold at 09:00, offline; Baba suspends him at 11:00                      saved, nothing more: he was working

These tests send pretend "ticket" documents
(tests/probe/documents.py), which need sale.write, through the push service. Fake data only: the repo is public.
"""

import dataclasses
import datetime as dt
import uuid
from collections.abc import Callable, Sequence
from zoneinfo import ZoneInfo

import pytest
from django.db.models import Model

from apps.control.models import AuditEvent, Flag, FlagKind, FlagPerson
from apps.core.links import LINK_TYPES
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.selectors import shop_today
from apps.people.services import add_staff, mark_left, suspend, unsuspend
from apps.shops.models import Shop, Side
from apps.shops.services import add_side
from apps.sync.document_types import DOCUMENT_TYPES
from apps.sync.models import PushedDocument
from apps.sync.push import Answer, Sent, push
from tests.probe.documents import TICKET, TICKET_CODE

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

CLIENT_TIME = dt.datetime(2026, 11, 10, 7, 42, tzinfo=dt.UTC)
RECEIVED_AT = dt.datetime(2026, 11, 10, 11, 5, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def ticket_type(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pretend ticket on the list of document types, and its table's link type code, for as long as each test runs.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET)
    monkeypatch.setitem(LINK_TYPES, TICKET_CODE, "probe.Ticket")


@pytest.fixture
def foods(shop_a: Shop) -> Side:
    # Shop A's second side, Vyakula: a key for it opens nothing on the Dawa laptop (X1).
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


def _sent(device_seq: int, maker: StaffMember, **envelope: object) -> Sent:
    # One ticket as the laptop sent it, its number `device_seq`, made by `maker`; `envelope` overrides its type.
    return Sent(
        id=uuid.uuid7(),
        type=str(envelope.get("type", "ticket")),
        schema_version=1,
        device_seq=device_seq,
        client_time=CLIENT_TIME,
        created_by=maker.pk,
        payload={"text": "2 bags of pumba"},
    )


def _push(device: Device, documents: Sequence[Sent]) -> list[Answer]:
    # The push as the route runs it: inside the laptop's shop, which its key opened.
    with shop_context(device.shop_id):
        return push(device, documents, received_at=RECEIVED_AT, unsent_count=0, app_version="2026.11.1", outages=[])


def _flags(shop: Model, kind: FlagKind) -> list[Flag]:
    with shop_context(shop):
        return list(Flag.objects.filter(kind=kind).order_by("id"))


def _named(flag: Flag) -> list[uuid.UUID]:
    with shop_context(flag.shop_id):
        return list(FlagPerson.objects.filter(flag=flag).values_list("staff_id", flat=True))


def test_offline_permission_break_flagged(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Done when #3: Juma holds no sale.write, yet a sale in his name came from the Dawa laptop: an old copy of the
    # shop's keys on it, or a laptop tampered with. The sale is saved, as every record is (accept, then flag), and one
    # flag about its line names him, on the laptop's side, for that side's managers to see (X1).
    [answer] = _push(device_a, [_sent(1, staff_a)])
    assert answer.status == "accepted"
    [broken] = _flags(shop_a, FlagKind.PERMISSION_BREAK)
    with shop_context(shop_a):
        line = PushedDocument.objects.get()
    assert (broken.subject_type, broken.subject_id) == ("pushed_document", line.pk)
    assert _named(broken) == [staff_a.pk]
    assert (broken.side_id, broken.expected, broken.actual, broken.created_by_id) == (
        device_a.home_side_id,
        None,
        None,
        None,
    )


def test_a_maker_with_the_key_raises_no_flag(
    shop_a: Model, device_a: Device, staff_a: StaffMember, side_a: Side, give_role: GiveRole
) -> None:
    # Asha is a seller on Dawa: her sale on the Dawa laptop is as it should be.
    give_role(staff_a, RoleTemplate.SELLER, side_a)
    _push(device_a, [_sent(1, staff_a)])
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


def test_a_key_on_every_side_counts_on_the_laptops(
    shop_a: Model, device_a: Device, staff_a: StaffMember, give_role: GiveRole
) -> None:
    # The manager holds sale.write on every side: it counts on Dawa too.
    give_role(staff_a, RoleTemplate.MANAGER, None)
    _push(device_a, [_sent(1, staff_a)])
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


def test_a_key_for_another_side_opens_nothing_here(
    shop_a: Model, device_a: Device, staff_a: StaffMember, foods: Side, give_role: GiveRole
) -> None:
    # Juma sells on Vyakula, not Dawa: a sale in his name on the Dawa laptop breaks the rule, as the laptop's own
    # check would have said with a fresh copy (X1).
    give_role(staff_a, RoleTemplate.SELLER, foods)
    _push(device_a, [_sent(1, staff_a)])
    assert len(_flags(shop_a, FlagKind.PERMISSION_BREAK)) == 1


def test_permission_break_raised_once(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # The same sale sent again, after a lost answer: the first answer again, and no second flag.
    sent = _sent(1, staff_a)
    _push(device_a, [sent])
    [again] = _push(device_a, [sent])
    assert again.status == "duplicate"
    assert len(_flags(shop_a, FlagKind.PERMISSION_BREAK)) == 1


def test_an_invalid_document_gets_no_permission_check(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # A record the server can't save was never made here: its own flag says what is wrong with it, and the server
    # can't know the key a type it doesn't take would need.
    [answer] = _push(device_a, [_sent(1, staff_a, type="no_such_type")])
    assert answer.status == "invalid"
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


def test_the_flag_stays_out_of_the_laptops_answer(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # The push's own checks are for the office, not the counter: the answer names only the flags the record's own
    # saving code raised, so a resend gets exactly its first answer (03 §5.5).
    [answer] = _push(device_a, [_sent(1, staff_a)])
    assert answer.flags == []
    assert len(_flags(shop_a, FlagKind.PERMISSION_BREAK)) == 1


# The suspension's checks below: a record made while its maker wasn't working here (X2; Jack, SYNC-5: leaving counts
# too). "Made" is the laptop's clock, the one time the record carries; "suspended" is when the audit trail says it
# happened. Both are real times from now, as the audit trail stamps its lines with the server's clock.


def _made_at(device_seq: int, maker: StaffMember, client_time: dt.datetime) -> Sent:
    return dataclasses.replace(_sent(device_seq, maker), client_time=client_time)


def _status_moves(staff: StaffMember) -> list[dt.datetime]:
    # When each of the person's status moves happened, oldest first, as the audit trail stamped them.
    with shop_context(staff.shop_id):
        return list(
            AuditEvent.objects.filter(subject_type="staff", subject_id=staff.pk)
            .order_by("created_at")
            .values_list("created_at", flat=True)
        )


@pytest.fixture
def asha(staff_a: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    # A seller on Dawa, so her records break no key rule: only her status is in question here.
    give_role(staff_a, RoleTemplate.SELLER, side_a)
    return staff_a


def test_document_after_suspension_flagged(shop_a: Model, device_a: Device, asha: StaffMember) -> None:
    # Done when #3: Baba suspends Asha at 11:00. The Dawa laptop was offline and didn't know, so its PIN check let her
    # in, and she sold at 12:00. The sale is saved, and flagged, naming her, on the laptop's side (X2).
    with shop_context(shop_a):
        suspend(asha, by=None, reason="Uchunguzi wa droo")
    [suspended_at] = _status_moves(asha)
    [answer] = _push(device_a, [_made_at(1, asha, suspended_at + dt.timedelta(hours=1))])
    assert answer.status == "accepted"
    [flag] = _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY)
    with shop_context(shop_a):
        line = PushedDocument.objects.get()
    assert (flag.subject_type, flag.subject_id, flag.side_id) == ("pushed_document", line.pk, device_a.home_side_id)
    assert _named(flag) == [asha.pk]
    # She holds her seller's key still, so the suspension is the one thing wrong: no second flag.
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


def test_document_made_before_the_suspension_is_not_flagged(shop_a: Model, device_a: Device, asha: StaffMember) -> None:
    # Asha sold at 09:00, offline; Baba suspended her at 11:00; the laptop synced at 12:00. She was working when she
    # sold: her status now says nothing about then.
    with shop_context(shop_a):
        suspend(asha, by=None, reason="Uchunguzi wa droo")
    [suspended_at] = _status_moves(asha)
    _push(device_a, [_made_at(1, asha, suspended_at - dt.timedelta(hours=2))])
    assert _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY) == []


def test_document_made_while_suspended_is_flagged_after_her_return(
    shop_a: Model, device_a: Device, asha: StaffMember
) -> None:
    # Suspended, then brought back; a sale made between the two arrives after her return. She is working now, but
    # wasn't when she sold. A sale after her return is hers to make.
    with shop_context(shop_a):
        suspend(asha, by=None, reason="Uchunguzi wa droo")
        unsuspend(asha, by=None, reason="Droo imekaguliwa")
    suspended_at, back_at = _status_moves(asha)
    between = suspended_at + (back_at - suspended_at) / 2
    _push(device_a, [_made_at(1, asha, between), _made_at(2, asha, back_at + dt.timedelta(minutes=5))])
    [flag] = _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY)
    with shop_context(shop_a):
        assert PushedDocument.objects.get(pk=flag.subject_id).device_seq == 1


def test_document_after_leaving_is_flagged(shop_a: Model, device_a: Device, asha: StaffMember) -> None:
    # Jack, SYNC-5: Asha left; a sale in her name made after that is flagged too. Her keys stay given, so step 6's
    # check alone would let it pass.
    with shop_context(shop_a):
        mark_left(asha, left_on=shop_today(asha.shop), by=None, reason="Amehamia Moshi")
    [left_at] = _status_moves(asha)
    _push(device_a, [_made_at(1, asha, left_at + dt.timedelta(minutes=5))])
    assert len(_flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY)) == 1


def test_a_leaving_date_recorded_late_counts_from_the_day_after(
    shop_a: Shop, device_a: Device, side_a: Side, give_role: GiveRole
) -> None:
    # The owner records on Monday that Juma's last day was Friday. His sale on Friday is his; one on Saturday, made
    # before Monday's record, is flagged all the same: he had gone. Here: his last day was yesterday, in the shop's own
    # time zone, recorded now. Hired a month ago, as a person can't leave before they started.
    zone = ZoneInfo(shop_a.timezone)
    last_day = shop_today(shop_a) - dt.timedelta(days=1)
    with shop_context(shop_a):
        juma = add_staff(
            shop=shop_a,
            user=User.objects.create_user(full_name="Juma Mfano"),
            display_name="Juma",
            started_on=last_day - dt.timedelta(days=30),
            by=None,
        )
    give_role(juma, RoleTemplate.SELLER, side_a)
    with shop_context(shop_a):
        mark_left(juma, left_on=last_day, by=None, reason="Amehamia Moshi")
    on_her_last_day = dt.datetime.combine(last_day, dt.time(15, 0), tzinfo=zone)
    day_after = dt.datetime.combine(last_day + dt.timedelta(days=1), dt.time(0, 30), tzinfo=zone)
    _push(device_a, [_made_at(1, juma, on_her_last_day), _made_at(2, juma, day_after)])
    [flag] = _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY)
    with shop_context(shop_a):
        assert PushedDocument.objects.get(pk=flag.subject_id).device_seq == 2


def test_a_working_maker_raises_no_suspension_flag(shop_a: Model, device_a: Device, asha: StaffMember) -> None:
    _push(device_a, [_sent(1, asha)])
    assert _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY) == []
