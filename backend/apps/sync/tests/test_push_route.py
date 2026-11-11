"""apps/sync/tests/test_push_route.py — the address a shop laptop sends its documents to (SYNC-4; 03 §6.3).

    the cookie holds              POST /api/sync/v1/push/  {"documents": [...]}
    nothing, or a made-up key     401 not_authenticated
    a blocked device's key        401 device.blocked
    a paired device's key         200 {"answers": [...]}: one per document, in the laptop's order (test_push.py)
    ... and a broken envelope     400 invalid, under the field: `documents.0.device_seq`; nothing saved
    ... or more than 100

What each answer says is test_push.py's, through the service; these test the route around it: the key, the CSRF token,
the envelope's checks, and that an answer holds nothing of another shop, which the tenancy sweep can't read for a route
with no GET (DEVICE_ROUTES_WITHOUT_A_LOOK). Fake data only: the repo is public (03 §10).
"""

import datetime as dt
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.links import LINK_TYPES
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, DeviceOutage, StaffMember
from apps.people.services import block, confirm_pairing, start_pairing
from apps.shops.models import Shop, Side
from apps.sync.document_types import DOCUMENT_TYPES
from apps.sync.models import PushedDocument
from tests.change_log import last_line
from tests.probe.documents import TICKET, TICKET_CODE
from tests.probe.models import Ticket

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The routes and the cookie's name, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
PUSH = "/api/sync/v1/push/"
DEVICE_ME = "/api/devices/v1/me/"
KEY_COOKIE = "device_key"
# 10:42 by the laptop's clock, in UTC, as the laptop sends it (03 §6.6).
CLIENT_TIME = "2026-11-10T07:42:00Z"
# Any id, as JSON writes one: for finding every id an answer holds.
AN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture(autouse=True)
def ticket_type(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pretend ticket on the list of document types, and its table's link type code, for as long as each test runs.
    monkeypatch.setitem(DOCUMENT_TYPES, ("ticket", 1), TICKET)
    monkeypatch.setitem(LINK_TYPES, TICKET_CODE, "probe.Ticket")


def a_browser(key: str, *, csrf: bool = False) -> APIClient:
    # A browser that holds this device's key in its cookie. `csrf`: check CSRF as a real browser's visit is checked.
    client = APIClient(enforce_csrf_checks=csrf)
    client.cookies[KEY_COOKIE] = key
    return client


def pair(manager: StaffMember, side: Side, name: str) -> tuple[Device, str]:
    # A laptop paired the way the app pairs one: it asks and keeps its key, and the manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        device = confirm_pairing(asked.request.code, name=name, home_side=side, by=manager)
    return device, asked.key


@pytest.fixture
def manager(staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def laptop(manager: StaffMember, side_a: Side) -> tuple[Device, str]:
    return pair(manager, side_a, "Laptop ya Dawa")


def envelope(device_seq: int, maker: StaffMember, *, text: str = "2 bags of pumba", **changes: Any) -> dict[str, Any]:
    # One ticket as the laptop sends it, its number `device_seq`, made by `maker`; `changes` overrides a part.
    return {
        "id": str(uuid.uuid7()),
        "type": "ticket",
        "schema_version": 1,
        "device_seq": device_seq,
        "client_time": CLIENT_TIME,
        "created_by": str(maker.pk),
        "payload": {"text": text},
        **changes,
    }


def send(client: APIClient, documents: list[dict[str, Any]], *, csrf_token: str | None = None, **report: Any) -> Any:
    # One push, with the laptop's report on itself (`report` overrides a part), and the CSRF token as the app sends
    # it, when given.
    body = {"documents": documents, "app_version": "2026.11.1", "unsent_count": 0, "outages": [], **report}
    if csrf_token is None:
        return client.post(PUSH, body, format="json")
    return client.post(PUSH, body, format="json", HTTP_X_CSRFTOKEN=csrf_token)


def _tickets(shop: Shop) -> int:
    with shop_context(shop):
        return Ticket.objects.count()


def test_push_saves_and_answers_each_document(shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember) -> None:
    # Asha's two sales from the morning, sent with the laptop's key: both saved, each answered, in the laptop's order,
    # with the last change number its save took.
    _device, key = laptop
    first, second = envelope(1, staff_a), envelope(2, staff_a)
    start = last_line(shop_a)
    answer = send(a_browser(key), [second, first])
    assert answer.status_code == 200
    assert answer.json() == {
        "answers": [
            {
                "id": first["id"],
                "status": "accepted",
                "first": None,
                "posted_seq": start + 1,
                "flags": [],
                "code": "",
                "fields": {},
            },
            {
                "id": second["id"],
                "status": "accepted",
                "first": None,
                "posted_seq": start + 2,
                "flags": [],
                "code": "",
                "fields": {},
            },
        ]
    }
    assert _tickets(shop_a) == 2


def test_push_needs_a_paired_device(
    shop_a: Shop, manager: StaffMember, laptop: tuple[Device, str], staff_a: StaffMember
) -> None:
    # A device's key alone opens it: no key, a made-up one, or a person's own login saves nothing (DeviceView). A
    # blocked laptop, a stolen one, say, saves nothing either, and learns why.
    documents = [envelope(1, staff_a)]
    for client in (APIClient(), a_browser("a" * 43)):
        refused = send(client, documents)
        assert (refused.status_code, refused.json()["code"]) == (401, "not_authenticated")
    phone = APIClient()
    phone.force_login(manager.user)
    refused = send(phone, documents)
    assert (refused.status_code, refused.json()["code"]) == (401, "not_authenticated")
    device, key = laptop
    with shop_context(shop_a):
        block(device, by=manager, reason="Laptop imeibiwa")
    refused = send(a_browser(key), documents)
    assert (refused.status_code, refused.json()["code"]) == (401, "device.blocked")
    assert _tickets(shop_a) == 0


def test_push_needs_csrf(shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember) -> None:
    # The laptop's cookie goes with every request to our address, even one another website makes the laptop send:
    # without the token, that website could push made-up sales in the laptop's name (ADR-0038).
    _device, key = laptop
    client = a_browser(key, csrf=True)
    refused = send(client, [envelope(1, staff_a)])
    assert (refused.status_code, refused.json()["code"]) == (403, "permission_denied")
    assert _tickets(shop_a) == 0
    # With the token, as the app sends it: from the cookie `me` hands out.
    client.get(DEVICE_ME)
    sent = send(client, [envelope(1, staff_a)], csrf_token=client.cookies["csrftoken"].value)
    assert sent.status_code == 200
    assert _tickets(shop_a) == 1


def test_push_takes_at_most_100_documents(shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember) -> None:
    # A laptop sends its outbox 100 at a time (03 §6.3), so one push stays short on a slow line: exactly 100 are taken,
    # each answered. More is refused whole, before anything is saved.
    _device, key = laptop
    refused = send(a_browser(key), [envelope(seq, staff_a) for seq in range(1, 102)])
    assert (refused.status_code, refused.json()["fields"]) == (400, {"documents": ["max_length"]})
    assert _tickets(shop_a) == 0
    taken = send(a_browser(key), [envelope(seq, staff_a) for seq in range(1, 101)])
    assert taken.status_code == 200
    assert len(taken.json()["answers"]) == 100
    assert _tickets(shop_a) == 100


@pytest.mark.parametrize(
    ("changes", "field", "code"),
    [
        ({"device_seq": 0}, "documents.0.device_seq", "min_value"),
        # Past the highest a missing number's flag can hold with the one awaited after it (HIGHEST_DEVICE_SEQ).
        ({"device_seq": 10**12 - 1}, "documents.0.device_seq", "max_value"),
        # A random UUID (version 4), not one made with the time, as every id a device makes is (ADR-0007).
        ({"id": "6f1c2e8a-3b4d-4c5e-9f6a-7b8c9d0e1f2a"}, "documents.0.id", "id.not_uuid7"),
        ({"created_by": "not-an-id"}, "documents.0.created_by", "invalid"),
        ({"payload": ["2 bags of pumba"]}, "documents.0.payload", "not_a_dict"),
        ({"type": "t" * 41}, "documents.0.type", "max_length"),
    ],
    ids=["seq_0", "seq_too_long", "not_uuid7", "maker_not_an_id", "payload_not_an_object", "type_too_long"],
)
def test_a_broken_envelope_refuses_the_whole_push(
    shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember, changes: dict[str, Any], field: str, code: str
) -> None:
    # The envelope is the laptop's own sync code's work, not a person's: a broken one is a bug in the app, refused
    # loudly before anything is saved, with the field it is in. A broken payload is the document's own, answered
    # `invalid` for that document alone (test_push.py).
    _device, key = laptop
    refused = send(a_browser(key), [{**envelope(1, staff_a), **changes}, envelope(2, staff_a)])
    assert refused.status_code == 400
    assert refused.json()["fields"] == {field: [code]}
    assert _tickets(shop_a) == 0


def test_push_keeps_the_laptops_report(shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember) -> None:
    # Every sync pushes, an empty one too (03 §6.6): the laptop says how many records it holds besides these, and which
    # app it runs, and the server's clock says when. An empty push is how a laptop with nothing to send still reports.
    device, key = laptop
    before = timezone.now()
    answer = send(a_browser(key), [], app_version="2026.11.2", unsent_count=4)
    after = timezone.now()
    assert (answer.status_code, answer.json()) == (200, {"answers": []})
    with shop_context(shop_a):
        held = Device.objects.get(pk=device.pk)
    assert (held.unsent_count, held.app_version) == (4, "2026.11.2")
    assert held.last_synced_at is not None
    assert before <= held.last_synced_at <= after


def test_push_takes_the_laptops_offline_periods(shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember) -> None:
    # The laptop's offline periods ride on its next push, each with an id it made (ADR-0007), in UTC (03 §6.6).
    device, key = laptop
    offline = {"id": str(uuid.uuid7()), "started_at": "2026-11-10T06:10:00Z", "ended_at": "2026-11-10T06:40:00Z"}
    answer = send(a_browser(key), [], outages=[offline])
    assert answer.status_code == 200
    with shop_context(shop_a):
        [kept] = DeviceOutage.objects.filter(device=device)
    assert (str(kept.pk), kept.started_at, kept.ended_at) == (
        offline["id"],
        dt.datetime(2026, 11, 10, 6, 10, tzinfo=dt.UTC),
        dt.datetime(2026, 11, 10, 6, 40, tzinfo=dt.UTC),
    )


@pytest.mark.parametrize(
    ("report", "field", "code"),
    [
        ({"app_version": None}, "app_version", "null"),
        ({"app_version": ""}, "app_version", "blank"),
        ({"app_version": "v" * 65}, "app_version", "max_length"),
        ({"unsent_count": -1}, "unsent_count", "min_value"),
        # The column holds 2**31 - 1, and the push adds back up to 100 documents it couldn't save (SYNC-5's review).
        ({"unsent_count": 2**31 - 100}, "unsent_count", "max_value"),
        ({"unsent_count": None}, "unsent_count", "null"),
        ({"outages": None}, "outages", "null"),
        # A random UUID (version 4), not one made with the time, as every id a device makes is (ADR-0007).
        (
            {
                "outages": [
                    {"id": "6f1c2e8a-3b4d-4c5e-9f6a-7b8c9d0e1f2a", "started_at": CLIENT_TIME, "ended_at": CLIENT_TIME}
                ]
            },
            "outages.0.id",
            "id.not_uuid7",
        ),
        ({"outages": [{"id": str(uuid.uuid7()), "started_at": CLIENT_TIME}]}, "outages.0.ended_at", "required"),
        (
            {"outages": [{"id": str(uuid.uuid7()), "started_at": "today", "ended_at": CLIENT_TIME}]},
            "outages.0.started_at",
            "invalid",
        ),
        (
            {"outages": [{"id": str(uuid.uuid7()), "started_at": CLIENT_TIME, "ended_at": CLIENT_TIME}] * 101},
            "outages",
            "max_length",
        ),
    ],
    ids=[
        "no_app_version",
        "blank_app_version",
        "app_version_too_long",
        "unsent_below_0",
        "unsent_too_many",
        "no_unsent_count",
        "no_outages",
        "outage_not_uuid7",
        "outage_with_no_end",
        "outage_time_not_a_time",
        "too_many_outages",
    ],
)
def test_push_needs_the_laptops_report(
    shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember, report: dict[str, Any], field: str, code: str
) -> None:
    # The report is the laptop's sync code's work, as the envelope is: one missing or broken is a bug in the app,
    # refused whole and loudly before anything is saved.
    device, key = laptop
    refused = send(a_browser(key), [envelope(1, staff_a)], **report)
    assert (refused.status_code, refused.json()["fields"]) == (400, {field: [code]})
    assert _tickets(shop_a) == 0
    with shop_context(shop_a):
        assert Device.objects.get(pk=device.pk).last_synced_at is None


def test_push_saves_the_keys_laptop_and_the_servers_clock(
    shop_a: Shop, laptop: tuple[Device, str], staff_a: StaffMember
) -> None:
    # The laptop is the one whose key sent the push, whatever the body says, so one laptop can't push in another's
    # name (AUTH-2). Its clock is kept as sent; the time it arrived is the server's own.
    device, key = laptop
    before = timezone.now()
    send(a_browser(key), [envelope(7, staff_a, device_id=str(uuid.uuid7()))])
    after = timezone.now()
    with shop_context(shop_a):
        ticket = Ticket.objects.get()
        line = PushedDocument.objects.get()
    assert (ticket.device_id, line.device_id, ticket.device_seq) == (device.pk, device.pk, 7)
    assert ticket.client_time == dt.datetime(2026, 11, 10, 7, 42, tzinfo=dt.UTC)
    assert before <= ticket.received_at <= after


def test_push_answers_hold_nothing_of_another_shop(
    shop_a: Shop,
    laptop: tuple[Device, str],
    staff_a: StaffMember,
    staff_b: StaffMember,
    side_b: Side,
    give_role: GiveRole,
) -> None:
    # The tenancy sweep sends this route only empty POSTs, so it looks here for what a real push answers. Shop B's
    # laptop sends the id of a sale shop A saved, and one naming A's staff member as its maker: both are refused, and
    # neither answer holds a word of shop A, not a name, a shop, a text, nor an id B didn't send itself (03 §5.4).
    _device_a, key_a = laptop
    saved = envelope(1, staff_a, text="Mbolea ya MFANO")
    send(a_browser(key_a), [saved])
    give_role(staff_b, RoleTemplate.MANAGER, None)
    _device_b, key_b = pair(staff_b, side_b, "Laptop B")
    same_id = envelope(1, staff_b, id=saved["id"])
    a_maker = envelope(2, staff_a)
    answer = send(a_browser(key_b), [same_id, a_maker])
    assert answer.status_code == 200
    assert [(each["status"], each["code"]) for each in answer.json()["answers"]] == [
        ("invalid", "id.taken"),
        ("invalid", "document.maker_unknown"),
    ]
    shown = answer.content.decode()
    with shop_context(shop_a):
        ticket = Ticket.objects.get()
    for of_a in (
        staff_a.display_name,
        staff_a.user.full_name,
        str(shop_a.pk),
        shop_a.name,
        shop_a.code,
        ticket.text,
        str(ticket.device_id),
    ):
        assert of_a not in shown
    # And every id in the answers is one B's laptop sent itself, a document's or a maker's: none the server made or
    # found, of either shop.
    sent_ids = {str(each[part]) for each in (same_id, a_maker) for part in ("id", "created_by")}
    assert set(AN_ID.findall(shown)) <= sent_ids
