"""apps/sync/tests/test_clock_photo.py — a clock-in's photo, or why it has none (ATT-3; 02 §12, 03 §5.13).

    a tap with its photo's label  → the line, and the photo's row waiting for its file    no_photo ""
    a tap with no photo           → the line, with why                                    no_camera, blocked, failed
    a tap from the old app        → the line, as before ATT-3                             old_app
    on the demo                   → the line, and no photo's row, whatever came           demo
    a label that breaks a rule    → invalid, under the photo's own code, nothing kept

Through the push, as the route runs it (test_clock_in.py's way), so each test meets the list of types, the push's own
checks and the saving code (apps/staffpay/documents.py). The photo's file never comes here: its upload is CTRL-3's to
test (test_attachment_route.py). Fake data only: the label's numbers are made up, never a real photo's.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.db.models import Model
from pytest_django import Settings

from apps.control.models import Attachment, AttachmentKind
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember
from apps.shops.models import Shop, Side
from apps.staffpay.models import AttendanceEvent, NoPhoto
from apps.sync.push import Answer, Sent, push

pytestmark = pytest.mark.django_db

ARUSHA = ZoneInfo("Africa/Dar_es_Salaam")
TAPPED = dt.datetime(2026, 11, 19, 7, 55, tzinfo=ARUSHA)


def _label(**changes: Any) -> dict[str, Any]:
    # A photo's label as the laptop writes it (labelPhoto, frontend/src/offline/attachments.ts): a new id, the kind, its
    # type by its first bytes, its size in bytes and its SHA-256 in lower-case hex. Made-up numbers.
    return {
        "id": str(uuid.uuid7()),
        "kind": "clock_photo",
        "content_type": "image/jpeg",
        "size": 150_000,
        "sha256": "ab" * 32,
    } | changes


def _tap(maker: StaffMember, *, device_seq: int = 1, schema_version: int = 2, **photo: Any) -> Sent:
    # Asha taps Ingia at 07:55, as the laptop sends it: version 2 names its photo (`photo=_label()`) or why it has none
    # (`no_photo="no_camera"`); version 1, the old app's, names neither.
    return Sent(
        id=uuid.uuid7(),
        type="clock",
        schema_version=schema_version,
        device_seq=device_seq,
        client_time=TAPPED,
        created_by=maker.pk,
        payload={"kind": "in", "last_server_time": (TAPPED - dt.timedelta(hours=1)).isoformat()} | photo,
    )


def _push(device: Device, documents: Sequence[Sent]) -> list[Answer]:
    # Sent at once, inside the laptop's shop, which its key opened.
    with shop_context(device.shop_id):
        return push(
            device,
            documents,
            received_at=TAPPED + dt.timedelta(seconds=2),
            sent_at=TAPPED + dt.timedelta(seconds=1),
            unsent_count=0,
            app_version="2026.11.2",
            outages=[],
        )


def _events(shop: Model) -> list[AttendanceEvent]:
    with shop_context(shop):
        return list(AttendanceEvent.objects.order_by("device_seq"))


def _photos(shop: Model) -> list[Attachment]:
    with shop_context(shop):
        return list(Attachment.objects.order_by("id"))


def test_a_tap_keeps_its_photos_row(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Asha's tap names its photo: her line is kept with no reason for none, and the photo's row waits beside it for the
    # file, which the laptop sends after the push (CTRL-6). The row is the label the laptop wrote, pinned to her line.
    label = _label()
    [answer] = _push(device_a, [_tap(staff_a, photo=label)])
    assert answer.status == "accepted"
    [event] = _events(shop_a)
    assert event.no_photo == ""
    [photo] = _photos(shop_a)
    assert (photo.id, photo.kind, photo.content_type, photo.size, photo.sha256) == (
        uuid.UUID(label["id"]),
        AttachmentKind.CLOCK_PHOTO,
        "image/jpeg",
        150_000,
        "ab" * 32,
    )
    # Pinned to her line, taken by her, on that laptop, and waiting: no file yet.
    assert (photo.subject_type, photo.subject_id, photo.created_by_id, photo.device_id) == (
        "attendance_event",
        event.pk,
        staff_a.pk,
        device_a.pk,
    )
    assert photo.received_at is None


@pytest.mark.parametrize("reason", ["no_camera", "blocked", "failed"])
def test_a_tap_with_no_photo_keeps_why(shop_a: Model, device_a: Device, staff_a: StaffMember, reason: str) -> None:
    # No camera, a camera the browser was told to block, or one that failed: the tap is kept all the same, as nobody
    # loses a day's pay to a camera (Jack: A), and the line says why it has no photo, for a manager to see (ATT-5).
    [answer] = _push(device_a, [_tap(staff_a, no_photo=reason)])
    assert answer.status == "accepted"
    [event] = _events(shop_a)
    assert event.no_photo == reason
    assert _photos(shop_a) == []


def test_a_tap_from_the_old_app_is_kept_as_old_app(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Asha tapped on a laptop still on the app before ATT-3, version 1, which names no photo. Kept, as before, the
    # server taking the shape before the newest (03 §6.8); its reason says the app had no camera yet.
    [answer] = _push(device_a, [_tap(staff_a, schema_version=1)])
    assert answer.status == "accepted"
    [event] = _events(shop_a)
    assert event.no_photo == NoPhoto.OLD_APP
    assert _photos(shop_a) == []


def test_on_the_demo_no_photo_is_kept(
    shop_a: Model, device_a: Device, staff_a: StaffMember, settings: Settings
) -> None:
    # On the demo every visitor shares Meneja's login, which opens clock-in photos, so a visitor's face never leaves
    # their laptop (Jack: A). The laptop sends none there; and if one came all the same, the server keeps no row for it,
    # the second lock, and the line says `demo`.
    settings.DEMO_SEED = True
    answers = _push(device_a, [_tap(staff_a, photo=_label()), _tap(staff_a, device_seq=2, no_photo="demo")])
    assert [answer.status for answer in answers] == ["accepted", "accepted"]
    assert [event.no_photo for event in _events(shop_a)] == [NoPhoto.DEMO, NoPhoto.DEMO]
    assert _photos(shop_a) == []


@pytest.mark.parametrize(
    ("photo", "fields"),
    [
        # Neither: a version 2 tap says one or the other.
        ({}, {"no_photo": ["required"]}),
        # Both: a photo has no reason for none.
        ({"photo": _label(), "no_photo": "blocked"}, {"no_photo": ["invalid"]}),
        # Old app is the server's word for version 1, never a laptop's.
        ({"no_photo": "old_app"}, {"no_photo": ["invalid_choice"]}),
        # A clock-in's photo is a clock photo: a worker's photo would be opened with another key.
        ({"photo": _label(kind="staff_photo")}, {"photo.kind": ["invalid_choice"]}),
    ],
    ids=["neither", "both", "old_app_from_a_laptop", "another_kind"],
)
def test_a_tap_names_its_photo_or_why_it_has_none(
    shop_a: Model, device_a: Device, staff_a: StaffMember, photo: dict[str, Any], fields: dict[str, list[str]]
) -> None:
    # The laptop's code wrote the tap wrong: set aside, with the field that is wrong, and nothing kept.
    [answer] = _push(device_a, [_tap(staff_a, **photo)])
    assert (answer.status, answer.code, answer.fields) == ("invalid", "invalid", fields)
    assert _events(shop_a) == []
    assert _photos(shop_a) == []


@pytest.mark.parametrize(
    ("label", "code"),
    [
        ({"content_type": "image/png"}, "attachment.not_an_image"),
        ({"size": 1_048_577}, "attachment.too_big"),
        ({"size": 0}, "attachment.empty"),
        ({"sha256": "AB" * 32}, "attachment.sha256_invalid"),
    ],
    ids=["png", "over_1_mb", "empty", "sha256_in_capitals"],
)
def test_a_label_that_breaks_a_rule_refuses_the_whole_tap(
    shop_a: Model, device_a: Device, staff_a: StaffMember, label: dict[str, Any], code: str
) -> None:
    # The photo's row refuses its label (CTRL-3's rules): the tap is invalid under the photo's own code, so the
    # counter's warning names it in words (needs-attention.tsx), and neither the line nor the row is kept: a line whose
    # photo can never come would wait on the server for good.
    [answer] = _push(device_a, [_tap(staff_a, photo=_label(**label))])
    assert (answer.status, answer.code) == ("invalid", code)
    assert _events(shop_a) == []
    assert _photos(shop_a) == []


def test_a_photo_id_already_taken_is_id_taken(shop_a: Model, device_a: Device, staff_a: StaffMember) -> None:
    # Two taps name one photo's id: the laptop's ids clash, which the push answers as any id taken (03 §5.4). The first
    # is kept with its photo; the second is set aside, its line not kept.
    label = _label()
    answers = _push(device_a, [_tap(staff_a, photo=label), _tap(staff_a, device_seq=2, photo=label)])
    assert [(answer.status, answer.code) for answer in answers] == [("accepted", ""), ("invalid", "id.taken")]
    assert len(_events(shop_a)) == 1
    assert len(_photos(shop_a)) == 1


@pytest.fixture
def device_b(shop_b: Shop, side_b: Side) -> Device:
    # A laptop of the second shop. Only the row, as device_a is (backend/conftest.py).
    with shop_context(shop_b):
        return Device.objects.create(shop=shop_b, home_side=side_b, name="Laptop B", code=1, key_hash="b" * 64)


def test_a_photo_id_another_shop_holds_is_id_taken(
    shop_a: Model, shop_b: Shop, device_a: Device, device_b: Device, staff_a: StaffMember, staff_b: StaffMember
) -> None:
    # Shop B's clock-in photo has this id already. Shop A's laptop names the same id for Asha's photo: the shop guard
    # hides B's row from the row's own checks, so the INSERT clashes on the table's key, and the push answers as for any
    # id another shop holds, `id.taken`, telling nothing of B's photo (03 §5.4, the sync rule; ATT-3's review). Asha's
    # line goes with it, and B's photo stays as it was.
    label = _label()
    [theirs] = _push(device_b, [_tap(staff_b, photo=label)])
    assert theirs.status == "accepted"

    [answer] = _push(device_a, [_tap(staff_a, photo=label)])

    assert (answer.status, answer.code, answer.fields) == ("invalid", "id.taken", {})
    assert _events(shop_a) == []
    assert _photos(shop_a) == []
    [kept] = _photos(shop_b)
    assert (kept.id, kept.shop_id, kept.created_by_id) == (uuid.UUID(label["id"]), shop_b.pk, staff_b.pk)
