"""backend/tests/test_flag_routes.py — the flags on their office pages, *Tofauti* (CTRL-4, 02 §13).

    GET  /api/v1/control/flags/?state=waiting     what waits, newest found first, in pages, and how many wait
    GET  /api/v1/control/flags/?state=closed      the closed ones
    GET  /api/v1/control/flags/{id}/              one flag: what happened, and every note
    POST /api/v1/control/flags/{id}/explain/      say why; it still waits
    POST /api/v1/control/flags/{id}/resolve/      close it: a real problem, dealt with
    POST /api/v1/control/flags/{id}/dismiss/      close it: no problem after all

Each flag shows only to whoever may close it: `flag.review` on its side, or on the whole shop for a flag of no side, as
attendance's are. The rest are "not found". The rule itself, a side's rows shown behind a key of their own, is the
base's and has its own tests (backend/tests/test_route_permissions.py); these check that the flags keep it.

    shop      sides                    laptops            who asks
    MFANO     Dawa (D), Vyakula (F)    one on each side   Baba, the owner; a manager of one side; a seller

It lives outside `apps`, as the flags are `control`'s (layer 0), and what they are about, pushed records and taps, and
who may see them, roles, belong to higher apps, which its own tests may not import (ADR-0043). Fake data only: the repo
is public (03 §10).
"""

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.control.api.pagination import FlagPage
from apps.control.models import Flag, FlagKind, FlagNote
from apps.control.services import dismiss_flag, explain_flag, raise_flag, resolve_flag
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.services import add_staff, grant_permission, hire_again, mark_left, suspend
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.shops.services import add_side
from apps.sync.models import PushedDocument, PushedStatus
from apps.sync.push import Carried, Sent, push

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

FLAGS = "/api/v1/control/flags/"
SUNDAY_0752 = dt.datetime(2026, 11, 22, 4, 52, tzinfo=dt.UTC)  # 07:52 in Arusha


def client_for(staff: StaffMember) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


@pytest.fixture
def foods(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="F", name="Vyakula", by=None)


@pytest.fixture
def foods_laptop(shop_a: Shop, foods: Side) -> Device:
    with shop_context(shop_a):
        return Device.objects.create(shop=shop_a, home_side=foods, name="Laptop ya Vyakula", code=2, key_hash="b" * 64)


@pytest.fixture
def baba(shop_a: Shop, staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.OWNER, None)
    return staff_a2


def pushed(device: Device, number: int, *, at: dt.datetime = SUNDAY_0752, **parts: Any) -> PushedDocument:
    # A pushed record's line in the answer log, as a flag of the push's names it (SYNC-5).
    with shop_context(device.shop_id):
        return PushedDocument.objects.create(
            shop_id=device.shop_id,
            device=device,
            device_seq=number,
            client_time=at,
            received_at=at + dt.timedelta(days=1),
            document_id=uuid.uuid7(),
            type="clock",
            schema_version=2,
            **{"status": PushedStatus.ACCEPTED, **parts},
        )


def flagged(line: PushedDocument, kind: FlagKind, *people: StaffMember, side: Side | None, **numbers: Any) -> Flag:
    with shop_context(line.shop_id):
        return raise_flag(kind=kind, subject=line, people=people, side=side, by=None, **numbers)


def shown(client: APIClient, **query: str) -> list[str]:
    return [line["id"] for line in client.get(FLAGS, query).json()["results"]]


def ids(*flags: Flag) -> list[str]:
    return [str(flag.pk) for flag in flags]


# --- The list


def test_the_list_shows_what_waits_newest_found_first(
    shop_a: Shop,
    side_a: Side,
    foods: Side,
    device_a: Device,
    foods_laptop: Device,
    staff_a: StaffMember,
    baba: StaffMember,
) -> None:
    # Juma, suspended, tapped on the Dawa laptop on Sunday; on Monday it sent record 43 before 42; then Vyakula's sent a
    # record the server couldn't keep. Newest found first: each says its kind, its side, who it names, and its record's
    # laptop and time, the time the laptop showed, not when the server found it.
    suspended = flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
    missing = flagged(pushed(device_a, 43), FlagKind.DEVICE_GAP, side=side_a, expected=42, actual=43)
    refused = flagged(
        pushed(foods_laptop, 1, status=PushedStatus.INVALID, reason="document.type_unknown"),
        FlagKind.INVALID_DOCUMENT,
        staff_a,
        side=None,
    )

    answer = client_for(baba).get(FLAGS).json()

    assert [line["id"] for line in answer["results"]] == ids(refused, missing, suspended)
    assert answer["waiting"] == 3
    assert answer["results"][2] == {
        "id": str(suspended.pk),
        "kind": "suspended_staff_activity",
        "status": "open",
        "side": "Dawa",
        "people": ["Staff A"],
        "device": "Laptop ya Dawa",
        "made_at": "2026-11-22T04:52:00Z",
        "raised_at": suspended.created_at.isoformat().replace("+00:00", "Z"),
    }
    # A flag that names nobody, and one of the whole shop.
    assert (answer["results"][1]["people"], answer["results"][0]["side"]) == ([], None)


def test_closed_flags_have_a_list_of_their_own(
    shop_a: Shop, side_a: Side, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # An explained flag still waits: only a close ends it (02 §13).
    opened, explained, resolved, dismissed = (
        flagged(pushed(device_a, number), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
        for number in range(1, 5)
    )
    with shop_context(shop_a):
        explain_flag(explained, text="Alikuja kuchukua vitu vyake", by=baba)
        resolve_flag(resolved, text="Tumezungumza naye", by=baba)
        dismiss_flag(dismissed, text="Alikuwa amerudishwa kazini", by=baba)
    client = client_for(baba)

    assert shown(client, state="waiting") == ids(explained, opened)
    assert shown(client, state="closed") == ids(dismissed, resolved)
    # No state asked: what waits, as the page opens on it.
    assert shown(client) == ids(explained, opened)
    assert client.get(FLAGS, {"state": "closed"}).json()["waiting"] == 2


def test_the_list_keeps_to_a_kind_and_a_side(
    shop_a: Shop,
    side_a: Side,
    foods: Side,
    device_a: Device,
    foods_laptop: Device,
    staff_a: StaffMember,
    baba: StaffMember,
) -> None:
    # *Chuja*: a side, the whole shop's own, a kind, or a side and a kind together. How many wait follows the filter,
    # as the tab counts the lines under it.
    dawa = flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
    dawa_gap = flagged(pushed(device_a, 43), FlagKind.DEVICE_GAP, side=side_a, expected=42, actual=43)
    vyakula = flagged(pushed(foods_laptop, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=foods)
    whole = flagged(pushed(foods_laptop, 2), FlagKind.INVALID_DOCUMENT, staff_a, side=None)
    client = client_for(baba)

    assert shown(client, side=str(side_a.pk)) == ids(dawa_gap, dawa)
    assert shown(client, side=str(foods.pk)) == ids(vyakula)
    assert shown(client, whole_shop="true") == ids(whole)
    assert shown(client, kind="suspended_staff_activity") == ids(vyakula, dawa)
    assert shown(client, kind="suspended_staff_activity", side=str(side_a.pk)) == ids(dawa)
    assert client.get(FLAGS, {"kind": "device_gap"}).json()["waiting"] == 1
    # A side no shop has, and another shop's, hold none, alike.
    assert shown(client, side=str(uuid.uuid7())) == []
    for wrong in ({"state": "open"}, {"kind": "no_such_kind"}, {"side": "Dawa"}):
        answer = client.get(FLAGS, wrong)
        assert (answer.status_code, list(answer.json()["fields"])) == (400, list(wrong)), wrong


def test_a_flag_shows_only_to_whoever_may_close_it(
    shop_a: Shop,
    side_a: Side,
    foods: Side,
    device_a: Device,
    foods_laptop: Device,
    staff_a: StaffMember,
    baba: StaffMember,
    give_role: GiveRole,
) -> None:
    # `flag.review` on Dawa alone: Dawa's flags, never Vyakula's, though she sells there too, and none of the whole
    # shop's (02 §13). Baba, on every side, sees the three.
    dawa = flagged(pushed(device_a, 1), FlagKind.PERMISSION_BREAK, baba, side=side_a)
    vyakula = flagged(pushed(foods_laptop, 1), FlagKind.PERMISSION_BREAK, baba, side=foods)
    whole = flagged(pushed(foods_laptop, 2), FlagKind.INVALID_DOCUMENT, baba, side=None)
    give_role(staff_a, RoleTemplate.SELLER, foods)

    # A seller holds it nowhere: refused, not shown an empty list that would say nothing waits.
    seller = client_for(staff_a).get(FLAGS)
    assert (seller.status_code, seller.json()["code"]) == (403, "permission_denied")

    with shop_context(shop_a):
        grant_permission(staff_a, Permission.FLAG_REVIEW, side=side_a, by=None)
    asha = client_for(staff_a)
    assert shown(asha) == ids(dawa)
    assert asha.get(FLAGS).json()["waiting"] == 1
    assert shown(asha, side=str(foods.pk)) == []
    assert shown(asha, whole_shop="true") == []
    assert shown(client_for(baba)) == ids(whole, vyakula, dawa)


def test_a_long_list_comes_in_pages(
    monkeypatch: pytest.MonkeyPatch, side_a: Side, device_a: Device, baba: StaffMember
) -> None:
    # *Onyesha zaidi* follows the page's own `next`, which keeps the state and the filters asked.
    monkeypatch.setattr(FlagPage, "page_size", 2)
    flags = [flagged(pushed(device_a, number), FlagKind.PERMISSION_BREAK, side=side_a) for number in range(1, 4)]
    client = client_for(baba)

    first = client.get(FLAGS, {"kind": "permission_break"}).json()
    second = client.get(first["next"]).json()

    assert [line["id"] for line in first["results"]] == ids(flags[2], flags[1])
    assert [line["id"] for line in second["results"]] == ids(flags[0])
    assert second["next"] is None
    assert (first["waiting"], second["waiting"]) == (3, 3)


def test_the_list_costs_the_same_queries_for_many(
    side_a: Side, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # One query per table for what the flags are about, never one per line (CTRL-1's note).
    def queries() -> int:
        with CaptureQueriesContext(
            connection,
        ) as asked:
            assert client_for(baba).get(FLAGS).status_code == 200
        return len(asked)

    flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
    for_one = queries()
    for number in range(2, 12):
        flagged(pushed(device_a, number), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)

    assert queries() == for_one


# --- One flag


ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")


def clock(number: int, maker: StaffMember, tapped: dt.datetime, *, kind: str = "in", **parts: Any) -> Sent:
    # One tap of Ingia or Toka, as a laptop pushes it; `parts` override the envelope.
    return Sent(
        **{
            "id": uuid.uuid7(),
            "type": "clock",
            "schema_version": 1,
            "device_seq": number,
            "client_time": tapped,
            "created_by": maker.pk,
            "payload": {"kind": kind, "last_server_time": (tapped - dt.timedelta(hours=1)).isoformat()},
            **parts,
        }
    )


def send(device: Device, *documents: Sent, sent_at: dt.datetime, received_at: dt.datetime | None = None) -> None:
    # The push as the route runs it, inside the laptop's shop. A right clock, unless `received_at` says otherwise.
    with shop_context(device.shop_id):
        push(
            device,
            documents,
            received_at=received_at or sent_at,
            sent_at=sent_at,
            unsent_count=0,
            app_version="2026.11.1",
            outages=[],
        )


def only_flag(shop: Shop, kind: FlagKind) -> Flag:
    with shop_context(shop):
        return Flag.objects.get(kind=kind)


def page_of(viewer: StaffMember, flag: Flag) -> dict[str, Any]:
    answer = client_for(viewer).get(f"{FLAGS}{flag.pk}/")
    assert answer.status_code == 200, answer.json()
    return answer.json()  # type: ignore[no-any-return]


def test_a_flag_about_a_tap_names_the_day_to_open(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # Asha tapped Toka at 00:30 on Monday in Arusha, Sunday still in UTC, on a laptop whose clock was 40 minutes slow as
    # it sent the tap hours later: no time is trusted, and the flag is the whole shop's. Its page opens her Monday, the
    # shop's own day, as the book reads an untrusted tap by the laptop's time.
    tapped = dt.datetime(2026, 11, 23, 0, 30, tzinfo=ARUSHA)
    sent_at = tapped + dt.timedelta(hours=8)
    send(
        device_a,
        clock(1, staff_a, tapped, kind="out"),
        sent_at=sent_at,
        received_at=sent_at + dt.timedelta(minutes=40),
    )
    flag = only_flag(shop_a, FlagKind.UNVERIFIED_TIME)

    page = page_of(baba, flag)

    assert page["tap"] == {"staff": str(staff_a.pk), "kind": "out", "day": "2026-11-23"}
    assert (page["kind"], page["side"], page["people"], page["device"]) == (
        "unverified_time",
        None,
        ["Staff A"],
        "Laptop ya Dawa",
    )
    assert page["made_at"] == "2026-11-22T21:30:00Z"
    assert (page["refused_for"], page["brought_from"], page["loaded_by"]) == ("", None, None)


def test_a_suspended_workers_tap_names_its_day(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # The flag is about the tap's line in the answer log, as the push's checks are, so the tap is found by it.
    with shop_context(shop_a):
        suspend(staff_a, by=None, reason="Hakuja kazini siku 3")
    tapped = timezone.now() + dt.timedelta(minutes=1)
    send(device_a, clock(1, staff_a, tapped), sent_at=tapped)

    page = page_of(baba, only_flag(shop_a, FlagKind.SUSPENDED_STAFF_ACTIVITY))

    day = tapped.astimezone(ARUSHA).date().isoformat()
    assert page["tap"] == {"staff": str(staff_a.pk), "kind": "in", "day": day}
    assert (page["side"], page["device"]) == ("Dawa", "Laptop ya Dawa")


def test_a_device_gap_says_its_numbers_and_the_systems_note(
    shop_a: Shop, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # Record 1, then 4: numbers 2 and 3 are missing. They came late, so the system closed the flag with a note of its
    # own, naming nobody (SYNC-5), whose text is a code the page says in words.
    first = dt.datetime(2026, 11, 23, 7, 0, tzinfo=ARUSHA)
    minute = dt.timedelta(minutes=1)
    send(device_a, clock(1, staff_a, first), sent_at=first)
    send(device_a, clock(4, staff_a, first + 4 * minute), sent_at=first + 4 * minute)
    flag = only_flag(shop_a, FlagKind.DEVICE_GAP)

    page = page_of(baba, flag)
    assert (page["expected"], page["actual"], page["difference"]) == ("2.000", "4.000", "2.000")
    assert (page["people"], page["notes"], page["status"]) == ([], [], "open")
    # Its line is record 4's, a tap of Asha's that came after the gap: the flag is about the missing records, names
    # nobody, and opens nobody's day.
    assert page["tap"] is None

    send(device_a, clock(2, staff_a, first + 2 * minute), sent_at=first + 5 * minute)
    send(device_a, clock(3, staff_a, first + 3 * minute), sent_at=first + 6 * minute)
    closed = page_of(baba, flag)
    assert closed["status"] == "resolved"
    (note,) = closed["notes"]
    assert (note["step"], note["text"], note["by"]) == ("resolved", "flag.device_gap_filled", None)


def test_a_refused_record_says_why(shop_a: Shop, device_a: Device, staff_a: StaffMember, baba: StaffMember) -> None:
    at = dt.datetime(2026, 11, 23, 7, 0, tzinfo=ARUSHA)
    send(device_a, clock(1, staff_a, at, type="no_such_record"), sent_at=at)

    page = page_of(baba, only_flag(shop_a, FlagKind.INVALID_DOCUMENT))

    assert page["refused_for"] == "document.type_unknown"
    assert (page["tap"], page["people"], page["device"]) == (None, ["Staff A"], "Laptop ya Dawa")


def test_a_carried_record_says_where_it_was_made_and_who_loaded_it(
    shop_a: Shop, device_a: Device, foods_laptop: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # Asha, who holds no device.manage, loaded the dying Dawa laptop's file on the Vyakula laptop (SYNC-12).
    at = dt.datetime(2026, 11, 23, 7, 0, tzinfo=ARUSHA)
    carried = Carried(device=device_a.pk, device_seq=5, loaded_by=staff_a.pk)
    send(foods_laptop, clock(1, baba, at, carried_from=carried), sent_at=at)

    page = page_of(baba, only_flag(shop_a, FlagKind.PERMISSION_BREAK))

    assert (page["device"], page["brought_from"], page["loaded_by"]) == (
        "Laptop ya Vyakula",
        "Laptop ya Dawa",
        "Staff A",
    )
    assert (page["people"], page["side"]) == (["Staff A"], "Vyakula")
    # It names Asha, who loaded the file: the tap in it is Baba's, whose day says nothing of her.
    assert page["tap"] is None
    assert page["about_loading"] is True


def test_a_flag_says_whether_it_is_about_loading_a_file_or_the_record_in_it(
    shop_a: Shop, device_a: Device, foods_laptop: Device, staff_a: StaffMember, baba: StaffMember, give_role: GiveRole
) -> None:
    # Two flags about one record, its maker's and its loader's, of one kind: told apart by the people, never by their
    # nicknames, which are unique among current workers alone. Juma, suspended, tapped; Neema, suspended too, loaded the
    # file. And a manager who loaded a record of her own, suspended: both of hers read as the record's.
    with shop_context(shop_a):
        juma, neema = (
            add_staff(shop=shop_a, user=User.objects.create_user(full_name=name), display_name=name, by=None)
            for name in ("Juma", "Neema")
        )
        give_role(neema, RoleTemplate.MANAGER, None)
        for worker in (juma, neema):
            suspend(worker, by=None, reason="Hakuja kazini siku 3")
    at = timezone.now() + dt.timedelta(minutes=1)
    theirs = Carried(device=device_a.pk, device_seq=5, loaded_by=neema.pk)
    send(foods_laptop, clock(1, juma, at, carried_from=theirs), sent_at=at)
    with shop_context(shop_a):
        flags = {
            flag.people.get().display_name: flag for flag in Flag.objects.filter(kind=FlagKind.SUSPENDED_STAFF_ACTIVITY)
        }
    assert {name: page_of(baba, flag)["about_loading"] for name, flag in flags.items()} == {
        "Juma": False,
        "Neema": True,
    }

    her_own = Carried(device=device_a.pk, device_seq=6, loaded_by=neema.pk)
    send(foods_laptop, clock(2, neema, at, carried_from=her_own), sent_at=at)
    with shop_context(shop_a):
        hers = list(
            Flag.objects.filter(kind=FlagKind.SUSPENDED_STAFF_ACTIVITY).exclude(
                pk__in=[flag.pk for flag in flags.values()]
            )
        )
    assert [page_of(baba, flag)["about_loading"] for flag in hers] == [False, False]

    # A missing number, about the line of a carried record: it names nobody, so it is about nobody's loading.
    late = Carried(device=device_a.pk, device_seq=7, loaded_by=neema.pk)
    send(foods_laptop, clock(9, juma, at, carried_from=late), sent_at=at)
    assert page_of(baba, only_flag(shop_a, FlagKind.DEVICE_GAP))["about_loading"] is False


def test_every_note_shows_with_who_and_when(
    shop_a: Shop, side_a: Side, device_a: Device, staff_a: StaffMember, baba: StaffMember
) -> None:
    # Oldest first, as they were written; none replaces another (02 §13).
    flag = flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)
    with shop_context(shop_a):
        explain_flag(flag, text="Nilikuja kuchukua vitu vyangu", by=staff_a)
        explain_flag(flag, text="Ni kweli, nilimwona", by=baba)
        resolve_flag(flag, text="Nimezungumza naye", by=baba)
        times = list(FlagNote.objects.order_by("created_at").values_list("created_at", flat=True))

    notes = page_of(baba, flag)["notes"]

    assert [(note["step"], note["text"], note["by"]) for note in notes] == [
        ("explained", "Nilikuja kuchukua vitu vyangu", "Staff A"),
        ("explained", "Ni kweli, nilimwona", "Staff A2"),
        ("resolved", "Nimezungumza naye", "Staff A2"),
    ]
    assert [dt.datetime.fromisoformat(note["at"]) for note in notes] == times


def test_a_flag_says_whether_it_names_the_viewer(
    shop_a: Shop, side_a: Side, device_a: Device, staff_a: StaffMember, baba: StaffMember, give_role: GiveRole
) -> None:
    # So the page shows *Eleza* alone to the one it names, whom the services refuse a close; under an old job too
    # (PPL-11), as they read the person.
    flag = flagged(pushed(device_a, 1), FlagKind.PERMISSION_BREAK, staff_a, side=side_a)
    give_role(staff_a, RoleTemplate.MANAGER, None)
    assert page_of(staff_a, flag)["names_you"] is True
    assert page_of(baba, flag)["names_you"] is False

    with shop_context(shop_a):
        mark_left(StaffMember.objects.get(pk=staff_a.pk), left_on=shop_today(shop_a), by=None, reason="Ameacha kazi")
        again = hire_again(StaffMember.objects.get(pk=staff_a.pk), display_name="Staff A Again", by=None)
    give_role(again, RoleTemplate.MANAGER, None)
    assert page_of(again, flag)["names_you"] is True


def test_a_flag_about_a_row_no_laptop_made_shows_its_own_facts(shop_a: Shop, side_a: Side, baba: StaffMember) -> None:
    # As a later card's may be: no laptop, no time, no tap; what the flag itself says, and never a broken page.
    with shop_context(shop_a):
        flag = raise_flag(kind=FlagKind.TOTAL_MISMATCH, subject=side_a, side=side_a, by=None)

    page = page_of(baba, flag)

    assert (page["side"], page["device"], page["made_at"], page["tap"]) == ("Dawa", None, None, None)
    assert shown(client_for(baba)) == ids(flag)


def test_a_flag_the_viewer_may_not_close_is_not_found(
    shop_a: Shop,
    side_a: Side,
    foods: Side,
    device_a: Device,
    foods_laptop: Device,
    staff_a: StaffMember,
    baba: StaffMember,
) -> None:
    # `flag.review` on Dawa alone opens neither Vyakula's flag nor the whole shop's, alike, as an id no shop has: none
    # of the three answers tells that a flag is there (03 §5.4).
    vyakula = flagged(pushed(foods_laptop, 1), FlagKind.PERMISSION_BREAK, baba, side=foods)
    whole = flagged(pushed(foods_laptop, 2), FlagKind.INVALID_DOCUMENT, baba, side=None)
    with shop_context(shop_a):
        grant_permission(staff_a, Permission.FLAG_REVIEW, side=side_a, by=None)
    asha = client_for(staff_a)
    dawa = flagged(pushed(device_a, 1), FlagKind.PERMISSION_BREAK, baba, side=side_a)
    assert asha.get(f"{FLAGS}{dawa.pk}/").status_code == 200

    for hidden in (vyakula.pk, whole.pk, uuid.uuid7()):
        answer = asha.get(f"{FLAGS}{hidden}/")
        assert (answer.status_code, answer.json()["code"]) == (404, "not_found")


# --- Explain, resolve, dismiss


STEPS = [
    ("explain", "explained", "waiting"),
    ("resolve", "resolved", "closed"),
    ("dismiss", "dismissed", "closed"),
]
CLOSES = ["resolve", "dismiss"]


def note(text: str = "Nimezungumza naye", **parts: Any) -> dict[str, Any]:
    # A note as the sheet sends it, with the id the phone made for it (ADR-0007).
    return {"id": str(uuid.uuid7()), "text": text, **parts}


def step(viewer: StaffMember, flag: Flag, name: str, sent: dict[str, Any]) -> Any:
    return client_for(viewer).post(f"{FLAGS}{flag.pk}/{name}/", sent, format="json")


@pytest.fixture
def waiting(side_a: Side, device_a: Device, staff_a: StaffMember) -> Flag:
    # Asha tapped while suspended, on the Dawa laptop.
    return flagged(pushed(device_a, 1), FlagKind.SUSPENDED_STAFF_ACTIVITY, staff_a, side=side_a)


@pytest.mark.parametrize(("name", "status", "tab"), STEPS)
def test_each_action_writes_its_note_and_moves_the_flag(
    waiting: Flag, baba: StaffMember, name: str, status: str, tab: str
) -> None:
    sent = note("Alikuja kuchukua vitu vyake tu")

    answer = step(baba, waiting, name, sent)

    assert answer.status_code == 200, answer.json()
    page = answer.json()
    assert page["status"] == status
    # The note by the id the phone made, with who wrote it: the page shows it at once, with no second ask.
    assert [(line["id"], line["step"], line["text"], line["by"]) for line in page["notes"]] == [
        (sent["id"], status, "Alikuja kuchukua vitu vyake tu", "Staff A2")
    ]
    assert page == page_of(baba, waiting)
    assert shown(client_for(baba), state=tab) == ids(waiting)


@pytest.mark.parametrize("name", ["explain", *CLOSES])
def test_the_same_send_twice_writes_one_note(waiting: Flag, baba: StaffMember, name: str) -> None:
    # A phone whose answer was lost sends the note again, by the same id: the first answer again, and no second note,
    # which could never be taken away (ADR-0007).
    sent = note()
    first, again = step(baba, waiting, name, sent), step(baba, waiting, name, sent)

    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()
    assert len(again.json()["notes"]) == 1


def test_a_closed_flag_takes_no_more(waiting: Flag, baba: StaffMember) -> None:
    # Meneja closed it while Baba's page still showed it waiting: he is told, and nothing is written (02 §13).
    assert step(baba, waiting, "dismiss", note()).status_code == 200

    for name in ("explain", *CLOSES):
        refused = step(baba, waiting, name, note("Nyingine"))
        assert (refused.status_code, refused.json()["code"]) == (400, "flag.closed"), name
    assert len(page_of(baba, waiting)["notes"]) == 1


def test_the_one_it_names_explains_and_never_closes(
    waiting: Flag, staff_a: StaffMember, baba: StaffMember, give_role: GiveRole
) -> None:
    # Asha is a manager now, and holds the key: the flag still names her (02 §13).
    give_role(staff_a, RoleTemplate.MANAGER, None)

    assert step(staff_a, waiting, "explain", note("Nilikuja kuchukua vitu vyangu")).status_code == 200
    for name in CLOSES:
        refused = step(staff_a, waiting, name, note())
        assert (refused.status_code, refused.json()["code"]) == (400, "flag.own_flag"), name
    assert step(baba, waiting, "resolve", note()).status_code == 200


def test_a_wrong_note_is_refused_beside_its_box(waiting: Flag, baba: StaffMember) -> None:
    for sent, field, code in (
        (note("   "), "text", "flag.note_required"),
        (note("a" * 501), "text", "max_length"),
        ({"id": str(uuid.uuid7())}, "text", "required"),
        ({"text": "Nimezungumza naye"}, "id", "required"),
        (note(id=str(uuid.uuid4())), "id", "id.not_uuid7"),
    ):
        refused = step(baba, waiting, "resolve", sent)
        assert (refused.status_code, refused.json()["fields"]) == (400, {field: [code]}), sent
    assert page_of(baba, waiting)["notes"] == []


def test_a_notes_id_already_taken_says_nothing_of_whose(
    shop_b: Shop, side_b: Side, waiting: Flag, staff_b: StaffMember, baba: StaffMember, device_a: Device, side_a: Side
) -> None:
    # Another shop's note holds the id, or another flag's of this shop: refused, the two alike, with not a word of it.
    with shop_context(shop_b):
        theirs = raise_flag(kind=FlagKind.TOTAL_MISMATCH, subject=side_b, side=side_b, people=[staff_b], by=None)
        explain_flag(theirs, text="Ya duka jingine", by=staff_b, note_id=(of_shop_b := uuid.uuid7()))
    ours = flagged(pushed(device_a, 2), FlagKind.PERMISSION_BREAK, side=side_a)
    sent = note()
    assert step(baba, ours, "explain", sent).status_code == 200

    answers = [step(baba, waiting, "resolve", note(id=taken)) for taken in (str(of_shop_b), sent["id"])]
    for refused in answers:
        assert (refused.status_code, refused.json()["code"], refused.json()["fields"]) == (
            400,
            "invalid",
            {"id": ["id.taken"]},
        )
    # The whole answer, its English message for the logs included: a word of difference would tell the two apart.
    assert answers[0].json() == answers[1].json()
    assert page_of(baba, waiting)["notes"] == []


def test_acting_on_a_flag_needs_the_key_on_its_side(
    shop_a: Shop, foods: Side, waiting: Flag, staff_a2: StaffMember, staff_a: StaffMember, give_role: GiveRole
) -> None:
    # A seller holds flag.review nowhere, and a manager of Vyakula alone holds it on no flag of Dawa's: "not found" to
    # both, before anything sent is read, and nothing written.
    give_role(staff_a2, RoleTemplate.SELLER, foods)
    for _ in range(2):
        for name in ("explain", *CLOSES):
            for sent in (note(), {}):
                refused = step(staff_a2, waiting, name, sent)
                assert (refused.status_code, refused.json()["code"]) == (404, "not_found"), name
        give_role(staff_a2, RoleTemplate.MANAGER, foods)
    with shop_context(shop_a):
        assert not FlagNote.objects.exists()


def test_the_demo_takes_ready_sentences_only(settings: Settings, waiting: Flag, baba: StaffMember) -> None:
    # Every visitor is Meneja there (OPS-13): words one typed would show to every visitor after them, so a note is one
    # of three ready ones, kept as its code, as a day's reason is (Jack, ATT-6: A).
    assert page_of(baba, waiting)["ready_notes"] == []
    settings.DEMO_SEED = True

    assert page_of(baba, waiting)["ready_notes"] == ["asked_them", "checked_laptop", "honest_mistake"]
    refused = step(baba, waiting, "explain", note("Nimezungumza naye"))
    assert (refused.status_code, refused.json()["fields"]) == (400, {"text": ["demo.ready_reasons"]})
    for name, ready in (("explain", "asked_them"), ("resolve", "checked_laptop")):
        assert step(baba, waiting, name, note(ready)).status_code == 200
    assert [line["text"] for line in page_of(baba, waiting)["notes"]] == ["asked_them", "checked_laptop"]
