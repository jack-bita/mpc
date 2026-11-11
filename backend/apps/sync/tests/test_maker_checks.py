"""apps/sync/tests/test_maker_checks.py — the checks a pushed record's maker gets again on the server (SYNC-5; 02 §16
X1, X2; 03 §6.3).

The laptop checked them at the counter, offline, against its copy of the shop: who holds which key, who is
suspended. That copy can be old, and a laptop can be tampered with, so the server checks again, and a broken rule
never refuses the record (accept, then flag):

    Asha sells on the Dawa laptop, and holds sale.write on Dawa            saved, nothing more
    Juma sells on the Dawa laptop, and holds no sale.write there           saved + permission_break, naming Juma

Each type of document names the key its maker needs (DocumentType.permission, apps/sync/document_types.py), checked on
the laptop's own side, among the keys the person was given. These tests send pretend "ticket" documents
(tests/probe/documents.py), which need sale.write, through the push service. Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable, Sequence

import pytest
from django.db.models import Model

from apps.control.models import Flag, FlagKind, FlagPerson
from apps.core.links import LINK_TYPES
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
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
