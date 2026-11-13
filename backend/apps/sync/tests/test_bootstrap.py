"""apps/sync/tests/test_bootstrap.py — a new device gets the whole shop in one answer (SYNC-2; 03 §6.4).

    the cookie holds              GET /api/sync/v1/bootstrap/
    nothing, or a made-up key     401 not_authenticated
    a blocked device's key        401 device.blocked
    a paired device's key         200: its shop's sides, accounts, people and rules (the registry's tables), each
                                  rule's default, the cursor: the last change number the copy holds, and the
                                  laptop's own last number, which its count carries on from

The cursor is read before the rows. A change that commits between the two reads is then in the rows, and the device
pulls it again later, which does no harm. Read after them, it could be counted in the cursor yet missing from the rows,
and the device would never get it (SYNC-1's review). Compressed for a client that asks. Shop B's device seeing nothing
of shop A's is the tenancy sweep's check (test_no_device_route_leaks_across_shops); nothing secret leaving is
test_bootstrap_secrets.py's. Fake data only: the repo is public (03 §10).
"""

import gzip
import json
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.core import settings_registry
from apps.core.changes import record_change, recording_changes
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, StaffMember, User
from apps.people.selectors import shop_today
from apps.people.services import add_staff, block, confirm_pairing, start_pairing
from apps.shops.models import Setting, Shop, Side
from apps.shops.services import add_side, rename_side
from apps.sync import bootstrap
from apps.sync.api.serializers import BootstrapAnswer
from apps.sync.registry import REGISTRY
from apps.sync.selectors import last_change_number
from tests.change_log import last_line
from tests.concurrency import in_another_transaction

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

# The route and the cookie's name, written out here rather than imported: they are a promise to the app and to the
# browser, and a test that read them from the code would follow the code wherever it went.
BOOTSTRAP = "/api/sync/v1/bootstrap/"
KEY_COOKIE = "device_key"


def a_browser(key: str) -> APIClient:
    # A browser that holds this device's key in its cookie, as the device's does.
    client = APIClient()
    client.cookies[KEY_COOKIE] = key
    return client


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="D", name="Dawa", by=None)


@pytest.fixture
def manager(staff_a2: StaffMember, give_role: GiveRole) -> StaffMember:
    # The manager who confirms the new laptop, on every side.
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def paired(manager: StaffMember, dawa: Side) -> tuple[Device, str]:
    # A new Dawa laptop, paired the way the app pairs one: it asks and keeps its key, and the manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        device = confirm_pairing(asked.request.code, name="Laptop ya Dawa", home_side=dawa, by=manager)
    return device, asked.key


def test_bootstrap_has_reference_data(
    shop_a: Shop, dawa: Side, manager: StaffMember, paired: tuple[Device, str]
) -> None:
    # Done when: a new device gets everything its counter needs in one response. Every table in the registry, by its
    # code, in the registry's order; what each holds is test_registry.py's. Today's late fine is set; the other rules
    # work at their defaults, which come beside the rows, as a new shop has no rows at all.
    with shop_context(shop_a):
        fine = Setting.objects.create(
            shop=shop_a, key="attendance.late_fine", value="1500.00", effective_from=shop_today(shop_a)
        )
    _device, key = paired
    response = a_browser(key).get(BOOTSTRAP)
    assert response.status_code == 200
    answer = response.json()
    assert list(answer) == [
        "shop",
        "cursor",
        "last_device_seq",
        "side",
        "payment_account",
        "staff",
        "setting",
        "setting_keys",
    ]
    assert [side["id"] for side in answer["side"]] == [str(dawa.pk)]
    assert [account["name"] for account in answer["payment_account"]] == ["Dawa"]  # the side's drawer
    assert [person["id"] for person in answer["staff"]] == [str(manager.pk)]
    assert [rule["id"] for rule in answer["setting"]] == [str(fine.pk)]
    # Every rule in the list in core, with its kind, its scope and its default as the kind writes it.
    assert len(answer["setting_keys"]) == len(settings_registry.KEYS)
    assert {"key": "attendance.late_fine", "kind": "money", "scope": "shop", "default": "1000.00"} in answer[
        "setting_keys"
    ]
    assert {"key": "cash.tolerance", "kind": "money", "scope": "side", "default": "0.00"} in answer["setting_keys"]


def test_bootstrap_cursor_is_the_shops_last_change(
    shop_a: Shop, dawa: Side, manager: StaffMember, paired: tuple[Device, str], shop_b: Shop, side_b: Side
) -> None:
    # The copy is the shop as of its last change: the device's first pull asks for what came after it (SYNC-3).
    _device, key = paired
    # The shop's last line so far: setting it up wrote lines too, its side and drawer and its people (SYNC-15). A shop
    # with none answers 0, which a pull reads as "from the start" (test_a_shop_with_no_change_is_at_zero).
    start = a_browser(key).get(BOOTSTRAP).json()["cursor"]
    assert start == last_line(shop_a)
    with shop_context(shop_a), recording_changes(shop_a):
        record_change(dawa)
        record_change(manager)
    # Shop B's own changes, three of them, never move shop A's cursor: each shop numbers its own.
    for _ in range(3):
        with shop_context(shop_b), recording_changes(shop_b):
            record_change(side_b)
    assert a_browser(key).get(BOOTSTRAP).json()["cursor"] == start + 2


def test_bootstrap_names_its_shop(shop_a: Shop, paired: tuple[Device, str]) -> None:
    # A laptop keeps one database per shop, named by the shop it believes it belongs to. If it was paired to another
    # shop between that belief and this call, the answer is the other shop's: the id lets it see so, and fill nothing
    # (SYNC-13, bootstrap.ts).
    _device, key = paired
    assert a_browser(key).get(BOOTSTRAP).json()["shop"] == str(shop_a.id)


def test_bootstrap_names_the_laptops_last_number(shop_a: Shop, paired: tuple[Device, str]) -> None:
    # A laptop numbers its records 1, 2, 3 and must never start again from 1 (SYNC-5): a sale's number taken twice would
    # be refused at every retry. A browser that frees its storage wipes the laptop's database, and its count with it,
    # but keeps the key's cookie, so the server's number is the one that survives: the bootstrap that fills the laptop
    # again says where its count stood (SYNC-8). A laptop just paired has counted nothing, so its first record is #1.
    device, key = paired
    assert a_browser(key).get(BOOTSTRAP).json()["last_device_seq"] == 0
    with shop_context(shop_a):
        Device.objects.filter(pk=device.pk).update(last_device_seq=57)
    assert a_browser(key).get(BOOTSTRAP).json()["last_device_seq"] == 57


@pytest.mark.django_db(transaction=True)
def test_bootstrap_cursor_consistent(
    shop_a: Shop, dawa: Side, paired: tuple[Device, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Done when: the snapshot and its cursor come from one consistent read. The owner renames Dawa on the office laptop
    # at the very moment the new laptop asks: the rename commits just before the bootstrap reads its cursor. Whatever
    # the cursor counts, the rows must hold: here, the new name. Had the rows been read first, they would hold the old
    # name while the cursor counts the rename, and the laptop, pulling only what comes after it, would keep "Dawa".
    # Two connections, as two laptops are; `transaction=True`, so the rename really commits
    # (backend/tests/concurrency.py). Shown red by reading the cursor after the rows.

    start = last_line(shop_a)

    def rename_then_read(shop: Shop) -> int:
        def owner_renames() -> None:
            # The office's save: the rename, and its line in the log, which rename_side writes itself (SYNC-15).
            with shop_context(shop_a):
                rename_side(dawa, version=dawa.version, name="Dawa Kuu", by=None)

        office, ended = in_another_transaction(owner_renames)
        office.join(timeout=5)
        assert ended == [None]
        return last_change_number(shop)  # the real read, once the rename has committed

    monkeypatch.setattr(bootstrap, "last_change_number", rename_then_read)
    _device, key = paired
    answer = a_browser(key).get(BOOTSTRAP).json()
    assert answer["cursor"] == start + 1
    assert [side["name"] for side in answer["side"]] == ["Dawa Kuu"]


def test_bootstrap_is_compressed(paired: tuple[Device, str]) -> None:
    # Still about 1 MB compressed once products and customers travel (03 §6.4), over a shop's slow line: gzip, for a
    # client that says it reads it, as every browser does. The same JSON once unpacked.
    _device, key = paired
    browser = a_browser(key)
    plain = browser.get(BOOTSTRAP)
    packed = browser.get(BOOTSTRAP, HTTP_ACCEPT_ENCODING="gzip")
    assert "Content-Encoding" not in plain.headers
    assert packed.headers["Content-Encoding"] == "gzip"
    # A cache in between must keep the two apart.
    assert "Accept-Encoding" in packed.headers["Vary"]
    unpacked: dict[str, Any] = json.loads(gzip.decompress(packed.content))
    assert unpacked == plain.json()
    assert len(packed.content) < len(plain.content)


def test_bootstrap_is_never_cached(paired: tuple[Device, str]) -> None:
    # The shop's whole staff list and everyone's keys: no browser cache, nor any proxy on the way, may keep a copy for
    # the next person, and a reset device must get today's lists, never yesterday's from a cache.
    _device, key = paired
    cache_control = a_browser(key).get(BOOTSTRAP).headers["Cache-Control"]
    assert {"no-store", "no-cache", "private"} <= {part.strip() for part in cache_control.split(",")}


def test_bootstrap_needs_a_paired_device(manager: StaffMember, paired: tuple[Device, str], shop_a: Shop) -> None:
    # The shop's whole list of people and rules, so a device's key alone opens it: no key, a made-up one, or a person's
    # session gets nothing (DeviceView). A blocked laptop, a stolen one, say, gets nothing either, and learns why.
    assert APIClient().get(BOOTSTRAP).json()["code"] == "not_authenticated"
    made_up = a_browser("a" * 43).get(BOOTSTRAP)
    assert (made_up.status_code, made_up.json()["code"]) == (401, "not_authenticated")
    # The manager's own phone, logged in as a person, with every key on every side but no device's key: a seller's phone
    # logged in the same way would otherwise carry the shop's whole staff list and everyone's keys away.
    phone = APIClient()
    phone.force_login(manager.user)
    from_a_phone = phone.get(BOOTSTRAP)
    assert (from_a_phone.status_code, from_a_phone.json()["code"]) == (401, "not_authenticated")
    device, key = paired
    with shop_context(shop_a):
        block(device, by=manager, reason="Laptop imeibiwa")
    blocked = a_browser(key).get(BOOTSTRAP)
    assert (blocked.status_code, blocked.json()["code"]) == (401, "device.blocked")


def reads_of_a_snapshot(device: Device) -> int:
    # How many queries one bootstrap answer costs the database, inside the device's shop, as its visit opens it. The
    # device is read as its key's login reads it, with its shop (apps/people/api/authentication.py), so the shop's own
    # read isn't counted on the first answer alone.
    with shop_context(device.shop_id):
        visiting = Device.objects.select_related("shop").get(pk=device.pk)
        with CaptureQueriesContext(connection) as seen:
            bootstrap.snapshot(visiting)
    return len(seen)


def test_bootstrap_reads_each_list_once_and_two_per_person(
    shop_a: Shop, dawa: Side, manager: StaffMember, paired: tuple[Device, str]
) -> None:
    # The copy grows to thousands of rows once products and customers travel (03 §6.4): a list must cost the same few
    # reads however many rows it holds, or 2,000 customers would cost 2,000 more. The one exception, by choice: each
    # person's keys, two reads each, by the one function the office routes use (held_permissions), as a shop has a
    # handful of people.
    with shop_context(shop_a):
        Setting.objects.create(
            shop=shop_a, key="attendance.late_fine", value="1500.00", effective_from=shop_today(shop_a)
        )
    device, _key = paired
    before = reads_of_a_snapshot(device)
    # Two more sides, each with its drawer and the drawer's link, and two more rules: not one more read.
    with shop_context(shop_a):
        for code, name in (("F", "Vyakula"), ("M", "Mbegu")):
            add_side(shop=shop_a, code=code, name=name, by=None)
        for key, value in (("cash.tolerance", "500.00"), ("session.idle_minutes", "20")):
            Setting.objects.create(shop=shop_a, key=key, value=value, effective_from=shop_today(shop_a))
    assert reads_of_a_snapshot(device) == before
    # Two more people: two reads each, for their keys.
    for full_name, nickname in (("Asha Mfano", "Asha"), ("Juma Mfano", "Juma")):
        user = User.objects.create_user(full_name=full_name)
        with shop_context(shop_a):
            add_staff(shop=shop_a, user=user, display_name=nickname, by=None)
    assert reads_of_a_snapshot(device) == before + 2 * 2


def test_answer_shape_names_every_registry_table() -> None:
    # The answer's documented shape (the API schema, and the app's types made from it) names each registry table with
    # the registry's own fields, so a table a later card adds can't reach devices undocumented, or the other way round.
    fields = BootstrapAnswer().fields
    assert list(fields) == ["shop", "cursor", "last_device_seq", *REGISTRY, "setting_keys"]
    for code, entry in REGISTRY.items():
        assert type(fields[code].child) is entry.serializer  # type: ignore[attr-defined]


def test_setting_keys_hold_every_rule_in_core() -> None:
    # A rule added to the list in core reaches the bootstrap by itself, with its default as its kind writes it.
    keys = bootstrap.setting_keys()
    assert [key["key"] for key in keys] == [key.key for key in settings_registry.KEYS]
    assert keys[0] == {"key": "attendance.on_time_until", "kind": "time", "scope": "shop", "default": "07:35"}
