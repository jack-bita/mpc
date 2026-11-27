"""apps/staffpay/tests/test_fix_taps_route.py — the routes that fix a worker's taps, /api/v1/staffpay/attendance-taps/
(ATT-13, 03 §5.10).

    POST attendance-taps/             {"id": …, "staff": …, "kind": "out", "date": "2026-11-16", "time": "18:45",
                                       "reason": "Alisahau kubonyeza Toka"}
    POST attendance-taps/{id}/void/   {"reason": "Alibonyeza kwa makosa"}

Who may fix what, and how, is add_tap's and void_tap's, tested in test_fix_taps.py; who may call the routes is pinned in
backend/tests/test_route_permissions.py, beside every other route's. Here, the requests and the answers as the two
sheets send and read them, a tap or a worker the routes don't show, and the refusals as the sheets show them. The client
from backend/conftest.py holds every key: shop A's owner, Staff A. Fake data only: the repo is public.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.staffpay.models import AttendanceEvent, ClockKind, NoPhoto, TimeCheck
from apps.staffpay.tests.days import ARUSHA, MONDAY, SUNDAY, job, kept_day, switch_on

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

TAPS = "/api/v1/staffpay/attendance-taps/"


@pytest.fixture(autouse=True)
def the_shops_day(shop_a: Shop, device_a: Device) -> None:
    # Shop A switched attendance on in January, with its fines, and keeps its laptop, Laptop ya Dawa, where Juma's own
    # taps are made (days.py).
    switch_on(shop_a)


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    return job(shop_a, "Juma")


def void_url(tap_id: uuid.UUID | str) -> str:
    return f"{TAPS}{tap_id}/void/"


def client_for(staff: StaffMember) -> APIClient:
    # Logged in as this person, at their shop, as the office screens call (backend/tests/test_route_permissions.py's).
    client = APIClient()
    client.force_authenticate(user=staff.user, token=staff)  # type: ignore[arg-type]
    return client


def add_sheet(whose: StaffMember, **changes: Any) -> dict[str, Any]:
    # What the add sheet sends: the tap's id, made on the phone (ADR-0007), whose tap, Ingia or Toka, the day, the
    # minute typed on the shop's clock, and why.
    sent = {
        "id": str(uuid.uuid7()),
        "staff": str(whose.pk),
        "kind": "out",
        "date": MONDAY.isoformat(),
        "time": "18:45",
        "reason": "Alisahau kubonyeza Toka",
    }
    return sent | changes


def jumas_ten_oclock_toka(juma: StaffMember) -> AttendanceEvent:
    # Juma's Monday on the shop's laptop: in at 07:20, and Toka at 10:00 by mistake. The Toka.
    kept_day(juma, (ClockKind.IN, 7, 20), (ClockKind.OUT, 10, 0))
    with shop_context(juma.shop_id):
        return AttendanceEvent.objects.get(staff=juma, kind=ClockKind.OUT)


def an_office_tap_of(staff: StaffMember) -> AttendanceEvent:
    # A tap of another shop's, entered in its office, written past its service: shop A's routes never reach that
    # shop's book, as the guard finds no such tap for shop A, so its row alone is all these tests need.
    with shop_context(staff.shop_id):
        return AttendanceEvent.objects.create(
            shop_id=staff.shop_id,
            received_at=timezone.now(),
            created_by=staff,
            staff=staff,
            kind=ClockKind.IN,
            trusted_time=dt.datetime(2026, 11, 16, 7, 20, tzinfo=ARUSHA),
            time_check=TimeCheck.ENTERED,
            no_photo=NoPhoto.ENTERED,
            entry_reason="Alisahau kubonyeza Ingia",
        )


# Adding a tap.


def test_a_tap_added_as_the_sheet_sends_it(staff_client_a: APIClient, juma: StaffMember) -> None:
    # Staff A, the owner, adds Juma's forgotten Toka of 18:45: the answer is the tap as the day shows it, with no
    # laptop, who added it, when and why. Sent again with the same id, as a phone whose answer was lost does, the same
    # tap comes back, and only one is kept (CreateOnceMixin).
    sent = add_sheet(juma)
    reply = staff_client_a.post(TAPS, sent, format="json")
    assert reply.status_code == 201
    answer = reply.json()
    entered = answer.pop("entered")
    assert answer == {
        "id": sent["id"],
        "date": "2026-11-16",
        "kind": "out",
        "time": "18:45",
        "laptop_time": None,
        "laptop": None,
        "photo": None,
        "no_photo": "entered",
        "doubt": None,
        "voided": None,
        # It came before its day's pay was approved, as none is (WAGE-10).
        "after_approval": False,
    }
    assert (entered["by"], entered["reason"]) == ("Staff A", "Alisahau kubonyeza Toka")
    again = staff_client_a.post(TAPS, sent, format="json")
    assert again.status_code == 201
    assert again.json()["id"] == sent["id"]
    with shop_context(juma.shop_id):
        assert AttendanceEvent.objects.filter(staff=juma).count() == 1


def test_adding_refusals_come_beside_their_boxes(shop_a: Shop, staff_client_a: APIClient, juma: StaffMember) -> None:
    # A minute still to come and a reason of spaces: both refused at once, each beside its box, with the codes the
    # sheet says in words (ADR-0040). A Sunday: refused as a whole, as the sheet has no box for the day.
    with shop_context(shop_a):
        later = shop_today(shop_a) + dt.timedelta(days=1)
    if later.weekday() == SUNDAY.weekday():
        later += dt.timedelta(days=1)
    reply = staff_client_a.post(TAPS, add_sheet(juma, date=later.isoformat(), reason="  "), format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"time": ["tap.in_future"], "reason": ["tap.reason_missing"]}
    sunday = staff_client_a.post(TAPS, add_sheet(juma, date=SUNDAY.isoformat()), format="json")
    assert sunday.status_code == 400
    assert sunday.json()["code"] == "tap.not_working_day"


def test_an_add_the_sheet_never_sends_is_refused(staff_client_a: APIClient, juma: StaffMember) -> None:
    # A kind that is neither Ingia nor Toka, a time with seconds, as the sheet sends a minute, a reason past 200
    # characters, and an id that is no UUIDv7: refused by the serializer, each beside its box.
    reply = staff_client_a.post(
        TAPS,
        add_sheet(juma, id=str(uuid.uuid4()), kind="nap", time="18:45:10", reason="x" * 201),
        format="json",
    )
    assert reply.status_code == 400
    assert set(reply.json()["fields"]) == {"id", "kind", "time", "reason"}
    assert reply.json()["fields"]["kind"] == ["invalid_choice"]
    assert reply.json()["fields"]["reason"] == ["max_length"]


def test_another_shops_worker_is_not_found(staff_client_a: APIClient, shop_b: Shop) -> None:
    # Bahati works at shop B: a tap added for her from shop A is refused exactly as for an id no shop has, so the answer
    # never tells that she exists (03 §5.4), and nothing is written.
    bahati = job(shop_b, "Bahati")
    theirs = staff_client_a.post(TAPS, add_sheet(bahati), format="json")
    nobodys = staff_client_a.post(TAPS, add_sheet(bahati, staff=str(uuid.uuid7())), format="json")
    assert theirs.status_code == 400
    assert theirs.json()["fields"] == nobodys.json()["fields"] == {"staff": ["does_not_exist"]}
    with shop_context(shop_b):
        assert not AttendanceEvent.objects.exists()


def test_a_seller_sending_a_taps_id_gets_nothing_back(
    shop_a: Shop, side_a: Side, give_role: GiveRole, juma: StaffMember
) -> None:
    # Asha sells on Dawa, and her laptop knows the ids of the taps made on it: sending Juma's Toka's id as a new tap's
    # must hand nothing back. A create sent again answers the tap it made before (CreateOnceMixin), so the route asks
    # the key before anything is read, a repeat included, as the pay rates' route does (WAGE-1's review).
    asha = job(shop_a, "Asha")
    give_role(asha, RoleTemplate.SELLER, side_a)
    toka = jumas_ten_oclock_toka(juma)
    reply = client_for(asha).post(TAPS, add_sheet(juma, id=str(toka.pk)), format="json")
    assert reply.status_code == 403
    assert reply.json()["code"] == "permission_denied"
    assert str(toka.pk) not in reply.content.decode()


# Crossing out a tap.


def test_a_tap_crossed_out_as_the_sheet_sends_it(staff_client_a: APIClient, juma: StaffMember) -> None:
    # Staff A crosses out Juma's 10:00 Toka: the answer is the tap as the day shows it, its laptop and time as before,
    # and who crossed it out, when and why. Sent again, as a phone whose answer was lost does, the same void comes back,
    # never stamped twice.
    toka = jumas_ten_oclock_toka(juma)
    reply = staff_client_a.post(void_url(toka.pk), {"reason": "Alibonyeza kwa makosa"}, format="json")
    assert reply.status_code == 200
    answer = reply.json()
    assert (answer["id"], answer["kind"], answer["time"], answer["laptop"]) == (
        str(toka.pk),
        "out",
        "10:00",
        "Laptop ya Dawa",
    )
    assert (answer["voided"]["by"], answer["voided"]["reason"], answer["entered"]) == (
        "Staff A",
        "Alibonyeza kwa makosa",
        None,
    )
    again = staff_client_a.post(void_url(toka.pk), {"reason": "Alibonyeza kwa makosa"}, format="json")
    assert again.status_code == 200
    assert again.json()["voided"] == answer["voided"]


def test_crossing_out_with_no_reason_is_refused_beside_its_box(staff_client_a: APIClient, juma: StaffMember) -> None:
    toka = jumas_ten_oclock_toka(juma)
    reply = staff_client_a.post(void_url(toka.pk), {"reason": " "}, format="json")
    assert reply.status_code == 400
    assert reply.json()["fields"] == {"reason": ["tap.reason_missing"]}
    too_long = staff_client_a.post(void_url(toka.pk), {"reason": "x" * 201}, format="json")
    assert too_long.json()["fields"] == {"reason": ["max_length"]}


def test_another_shops_tap_is_not_found_whatever_is_sent(staff_client_a: APIClient, shop_b: Shop) -> None:
    # Bahati's tap is shop B's. Crossed out from shop A, it is "not found", exactly as a tap no shop has, with a reason
    # or with an empty request, as the tenancy sweep sends one: the route looks for the tap before it reads what was
    # sent, so the guard is what answers (as ATT-6's review asked of deciding a day). Nothing is written.
    tap = an_office_tap_of(job(shop_b, "Bahati"))
    for sent in ({"reason": "Alibonyeza kwa makosa"}, {}):
        theirs = staff_client_a.post(void_url(tap.pk), sent, format="json")
        nobodys = staff_client_a.post(void_url(uuid.uuid7()), sent, format="json")
        assert theirs.status_code == 404
        assert theirs.json() == nobodys.json()
    with shop_context(shop_b):
        assert AttendanceEvent.objects.get(pk=tap.pk).voided_at is None


# Who may.


def test_ones_own_taps_are_refused(shop_a: Shop, give_role: GiveRole, juma: StaffMember) -> None:
    # Meneja, a manager, holds the key, but his own taps are the owner's to fix (as ATT-6's own day); Juma's he fixes.
    meneja = job(shop_a, "Meneja")
    give_role(meneja, RoleTemplate.MANAGER, None)
    own = client_for(meneja).post(TAPS, add_sheet(meneja), format="json")
    assert own.status_code == 400
    assert own.json()["code"] == "tap.own"
    assert client_for(meneja).post(TAPS, add_sheet(juma), format="json").status_code == 201
