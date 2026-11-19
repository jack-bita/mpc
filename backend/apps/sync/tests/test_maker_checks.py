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

The same for a key taken away (PPL-7): a sale made before Baba took Asha's Seller role away, synced after, breaks no
rule; one made after does.

These tests send pretend "ticket" documents (tests/probe/documents.py), which need sale.write, through the push
service. Fake data only: the repo is public.
"""

import dataclasses
import datetime as dt
import uuid
from collections.abc import Callable, Sequence
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.db.models import Model
from django.test.utils import CaptureQueriesContext

from apps.control.models import AuditEvent, Flag, FlagKind, FlagPerson
from apps.core.links import LINK_TYPES
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, Role, RoleAssignment, StaffMember, User
from apps.people.services import add_staff, assign_role, end_role, grant_permission, mark_left, suspend, unsuspend
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
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
        return push(
            device,
            documents,
            received_at=RECEIVED_AT,
            sent_at=RECEIVED_AT,
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )


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


def test_a_type_that_needs_no_key_raises_no_key_flag(
    shop_a: Model,
    device_a: Device,
    staff_a: StaffMember,
    foods: Side,
    give_role: GiveRole,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Clocking in needs no key: anyone working at the shop may clock in on any of its laptops (Jack, ATT-1). Baraka
    # works on Vyakula; one morning its laptop is off, so he clocks in on the Dawa laptop, where he holds no key. A
    # type that names no key (permission None) is saved with no permission_break flag, whatever the maker holds.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), dataclasses.replace(TICKET, permission=None))
    give_role(staff_a, RoleTemplate.SELLER, foods)
    [answer] = _push(device_a, [_sent(1, staff_a)])
    assert answer.status == "accepted"
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


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
    # Jack, SYNC-5: Asha left; a sale in her name made after that is flagged too. Her keys stay given, so the key
    # check alone (_maker_breaks' first question) would let it pass.
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


# A key taken away (PPL-7): the record is checked against the keys its maker held when it was made, by the laptop's
# clock, as their status is (02 §5 v1.39), read from the row's own end.


def _seller_role_ended(asha: StaffMember) -> dt.datetime:
    # Baba takes Asha's Seller role on Dawa away now; when the row says it ended. Given a day before, as in a shop, so a
    # sale made hours before the end was made while she held it, not before it was given.
    with shop_context(asha.shop_id):
        [given] = RoleAssignment.objects.filter(staff=asha)
        RoleAssignment.objects.filter(pk=given.pk).update(created_at=given.created_at - dt.timedelta(days=1))
        ended = end_role(given, reason="Amehamia Vyakula", by=None)
    assert ended.ended_at is not None
    return ended.ended_at


def test_a_record_made_before_its_key_was_taken_away_is_no_break(
    shop_a: Model, device_a: Device, asha: StaffMember
) -> None:
    # Asha sold at 09:00 on the Dawa laptop, offline; Baba took her Seller role away at 11:00; the laptop synced at
    # 12:00. She held the key when she sold, so the sale broke no rule: flagging it would accuse her falsely.
    ended_at = _seller_role_ended(asha)
    _push(device_a, [_made_at(1, asha, ended_at - dt.timedelta(hours=2))])
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


def test_a_record_made_the_moment_its_key_ended_is_a_break(shop_a: Model, device_a: Device, asha: StaffMember) -> None:
    # At the very moment of the end, the key is gone, as a suspension counts from its own moment (was_working_at).
    ended_at = _seller_role_ended(asha)
    _push(device_a, [_made_at(1, asha, ended_at)])
    assert len(_flags(shop_a, FlagKind.PERMISSION_BREAK)) == 1


def test_a_record_made_after_its_key_was_taken_away_is_a_break(
    shop_a: Model, device_a: Device, asha: StaffMember
) -> None:
    # A sale made after the end, on a laptop that hadn't heard of it yet, is a break, as for a key never given.
    ended_at = _seller_role_ended(asha)
    _push(
        device_a,
        [_made_at(1, asha, ended_at - dt.timedelta(minutes=5)), _made_at(2, asha, ended_at + dt.timedelta(hours=1))],
    )
    [broken] = _flags(shop_a, FlagKind.PERMISSION_BREAK)
    with shop_context(shop_a):
        assert PushedDocument.objects.get(pk=broken.subject_id).device_seq == 2


def test_a_key_given_after_the_record_still_counts(shop_a: Model, device_a: Device, asha: StaffMember) -> None:
    # The card's default: a laptop lets nobody sell with a key it hasn't heard of, so a record made before its key was
    # given can only be a slow laptop clock, and that is no break. Asha's role was given today; her sale says 10 Nov.
    with shop_context(shop_a):
        [given] = RoleAssignment.objects.filter(staff=asha)
    assert given.created_at > CLIENT_TIME
    _push(device_a, [_sent(1, asha)])
    assert _flags(shop_a, FlagKind.PERMISSION_BREAK) == []


@pytest.mark.parametrize("given_back_as", ["the role", "an extra key"])
def test_a_key_given_back_after_the_sale_hides_no_break(
    given_back_as: str, shop_a: Model, device_a: Device, asha: StaffMember, side_a: Side
) -> None:
    # The PPL-7 review: Baba takes Asha's Seller role at 11:00; she sells at 12:00 on a laptop that hasn't heard; Baba
    # gives it back at 13:00, as the role or as an extra sale.write; the laptop syncs at 14:00. A key given after a sale
    # counts for it only when it is new to her (the slow-clock default): one taken away before the sale and given back
    # after left a gap, and the sale fell in it. A break, as a suspension and a return around it would be.
    ended_at = _seller_role_ended(asha)
    with shop_context(shop_a):
        if given_back_as == "the role":
            back = assign_role(asha, Role.objects.get(template=RoleTemplate.SELLER), side=side_a, by=None).created_at
        else:
            back = grant_permission(asha, Permission.SALE_WRITE, side=side_a, by=None).created_at
    _push(device_a, [_made_at(1, asha, ended_at + (back - ended_at) / 2)])
    assert len(_flags(shop_a, FlagKind.PERMISSION_BREAK)) == 1


def test_a_working_maker_raises_no_suspension_flag(shop_a: Model, device_a: Device, asha: StaffMember) -> None:
    _push(device_a, [_sent(1, asha)])
    assert _flags(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY) == []


def test_the_maker_is_read_before_the_shops_change_counter_is_taken(
    shop_a: Model, device_a: Device, asha: StaffMember
) -> None:
    # The shop's change counter, once a record's block has taken its numbers, stays locked until the record commits,
    # and every save of the shop waits for it (SYNC-1). So the maker's keys and status are read before it, and only
    # writes come after: the line, the laptop's number, the flags (SYNC-5's review). Each read is named by its table.
    with CaptureQueriesContext(connection) as queries:
        _push(device_a, [_sent(1, asha)])
    sql = [query["sql"] for query in queries.captured_queries]
    counter = next(i for i, text in enumerate(sql) if "core_shopsequence" in text)
    reads_after = [
        text
        for text in sql[counter:]
        if text.startswith("SELECT")
        and any(table in text for table in ("people_roleassignment", "people_permissiongrant", "control_auditevent"))
    ]
    assert reads_after == []
