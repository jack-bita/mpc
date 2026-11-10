"""apps/sync/tests/test_pull.py — a device learns what changed in its shop after the last change it read (SYNC-3;
03 §6.4).

The shop's change log is a numbered list of lines, each naming a record that changed. A device remembers the last number
it read, its cursor, and asks for what came after:

    the change log                      a Dawa laptop at 41 asks "after 41?"
    42  staff  Juma suspended    ──►    42 staff  upsert   Juma's row as it is now: suspended
    43  staff  Asha left         ──►    43 staff  archive  no row: take her off the PIN screen
                                        cursor 43: next time it asks "after 43?"

A line holds no data, so each change carries its record as it is now, read through the registry (apps/sync/registry.py)
with the bootstrap's own fields. A record no longer among its table's rows has left the device's lists, so it goes as
`archive`, whatever its line said. Up to 1,000 lines a page; a device asks again at once while a page says more wait.

These tests read the answer as pull.page builds it; the route that sends it, with the device's key, is
test_pull_route.py's. The changes come from the services themselves, which write their own lines (SYNC-15). Setting up
the fixtures wrote lines too, so a test reads from a mark taken when it starts (backend/tests/change_log.py). Fake data
only: the repo is public (03 §10).
"""

import json
from datetime import datetime
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from pytest_django import Settings
from rest_framework.renderers import JSONRenderer

from apps.core.changes import record_change, recording_changes
from apps.core.tenancy import ShopMismatch, shop_context, system_context
from apps.people.models import StaffMember, User
from apps.people.selectors import shop_today
from apps.people.services import add_staff, change_person, mark_left, suspend
from apps.shops.models import Shop, Side, StockLocation
from apps.shops.services import add_side, rename_side
from apps.sync import pull
from apps.sync.registry import REGISTRY
from tests.change_log import last_line

pytestmark = pytest.mark.django_db


def pulled(shop: Shop, cursor: int) -> dict[str, Any]:
    # One page of the pull for a device of `shop` at `cursor`, as JSON, which is all a device ever sees: ids and times
    # are text there. Read inside the shop, as the device's visit opens it (DeviceView).
    with shop_context(shop):
        answer = pull.page(shop, cursor)
    page: dict[str, Any] = json.loads(JSONRenderer().render(answer))
    return page


def each_change(page: dict[str, Any]) -> list[tuple[int, str, str, str]]:
    # A page's changes in short: number, table, record, op.
    return [(change["seq"], change["entity"], change["id"], change["op"]) for change in page["changes"]]


def sent_by_the_bootstrap(code: str, shop: Shop, record_id: str) -> dict[str, Any]:
    # One record as the bootstrap sends it: the registry's rows, through its fields, as JSON.
    entry = REGISTRY[code]
    with shop_context(shop):
        rows = json.loads(JSONRenderer().render(entry.serializer(entry.rows(shop), many=True).data))
    (row,) = [row for row in rows if row["id"] == record_id]
    found: dict[str, Any] = row
    return found


def hire(shop: Shop, full_name: str, nickname: str) -> StaffMember:
    # A person with a job at the shop, made the way the app makes one (PPL-2).
    user = User.objects.create_user(full_name=full_name)
    with shop_context(shop):
        return add_staff(shop=shop, user=user, display_name=nickname, by=None)


@pytest.fixture
def dawa(shop_a: Shop) -> Side:
    # A side made the way the app makes one, with its stock location and its cash drawer (SHOP-2): two lines, the side
    # and its drawer.
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="D", name="Dawa", by=None)


def test_pull_returns_changes_after_cursor(shop_a: Shop, dawa: Side) -> None:
    # The owner renames Dawa, then suspends Juma. A laptop that read up to the mark gets those two, in their order, each
    # with its record as it is now, and the number to ask from next; nothing at or before the mark.
    juma = hire(shop_a, "Juma Mfano", "Juma")
    start = last_line(shop_a)
    with shop_context(shop_a):
        rename_side(dawa, version=dawa.version, name="Dawa Kuu", by=None)
        suspend(juma, by=None, reason="Likizo ya adhabu")
    page = pulled(shop_a, start)
    assert each_change(page) == [
        (start + 1, "side", str(dawa.pk), "upsert"),
        (start + 2, "staff", str(juma.pk), "upsert"),
    ]
    side, person = page["changes"]
    assert side["data"]["name"] == "Dawa Kuu"
    assert person["data"]["status"] == "suspended"
    assert page["cursor"] == start + 2


def test_pulling_again_gives_every_change_once_in_order(shop_a: Shop, dawa: Side) -> None:
    # Done when: pulling repeatedly gives every change once, in order. A new laptop starts at 0, as a shop's first
    # bootstrap could, and asks from the cursor each page hands it: it reads every number the log holds, once each, in
    # order. Asked again with nothing new, it gets nothing, and stays where it is; a new change comes alone.
    hire(shop_a, "Juma Mfano", "Juma")
    with shop_context(shop_a):
        rename_side(dawa, version=dawa.version, name="Dawa Kuu", by=None)
    read: list[int] = []
    cursor = 0
    while True:
        page = pulled(shop_a, cursor)
        read += [change["seq"] for change in page["changes"]]
        if not page["changes"]:
            break
        cursor = page["cursor"]
    assert read == list(range(1, last_line(shop_a) + 1))
    # The page that ended the loop came empty, and handed back the cursor it was asked from.
    assert page["cursor"] == cursor
    with shop_context(shop_a):
        add_side(shop=shop_a, code="F", name="Vyakula", by=None)
    assert [change["entity"] for change in pulled(shop_a, cursor)["changes"]] == ["side", "payment_account"]


def test_pull_pages_of_1000(shop_a: Shop) -> None:
    # A laptop away for a busy week finds thousands of lines waiting: it gets them 1,000 a page, so each answer stays a
    # size a slow line can carry and the device can save in one go. 1,001 changes: a full page, which says more wait, so
    # the device asks again at once; then the one left, which says none do; then nothing.
    start = last_line(shop_a)
    # 1,001 lines in one save, so the test stays quick: a save names each record once, so 1,001 records, sides made up
    # for the test and never saved. No device holds them, so the pages send them as archive; what counts here is how
    # many lines a page holds.
    with shop_context(shop_a), recording_changes(shop_a):
        for _ in range(1001):
            record_change(Side(shop=shop_a))
    first = pulled(shop_a, start)
    assert [change["seq"] for change in first["changes"]] == list(range(start + 1, start + 1001))
    assert (first["cursor"], first["has_more"]) == (start + 1000, True)
    second = pulled(shop_a, first["cursor"])
    assert [change["seq"] for change in second["changes"]] == [start + 1001]
    assert (second["cursor"], second["has_more"]) == (start + 1001, False)
    assert pulled(shop_a, second["cursor"])["changes"] == []


def test_a_page_says_more_wait_though_it_passed_lines_over(shop_a: Shop) -> None:
    # A page leaves out the lines of a table no device keeps (test_a_line_of_a_table_devices_dont_keep_is_passed_over),
    # so it can hold fewer than 1,000 changes while more wait: a device that asked again only after a page of 1,000
    # would stop there, and wait for its next sync, 30 seconds on, for the rest. So a page says itself whether more
    # wait. A stock location's line first, then 1,000 more, in one save, as in test_pull_pages_of_1000.
    start = last_line(shop_a)
    with shop_context(shop_a), recording_changes(shop_a):
        record_change(StockLocation(shop=shop_a))
        for _ in range(1000):
            record_change(Side(shop=shop_a))
    first = pulled(shop_a, start)
    assert len(first["changes"]) == 999
    assert (first["cursor"], first["has_more"]) == (start + 1000, True)
    second = pulled(shop_a, first["cursor"])
    assert [change["seq"] for change in second["changes"]] == [start + 1001]
    assert second["has_more"] is False


def test_pull_sends_archive_ops(shop_a: Shop, dawa: Side) -> None:
    # Done when: archived records arrive as archive. Asha leaves the shop: her line says archive, and it carries no row,
    # as she is no longer sent (staff_rows): every laptop takes her off its PIN screen. Her earlier change, a
    # suspension, says upsert in the log, but she has left by the time a laptop asks, so it goes as archive too: a
    # laptop given her old row there would put her back until the next line.
    asha = hire(shop_a, "Asha Mfano", "Asha")
    start = last_line(shop_a)
    with shop_context(shop_a):
        suspend(asha, by=None, reason="Likizo ya adhabu")
        mark_left(asha, left_on=shop_today(shop_a), by=None, reason="Amehamia mji mwingine")
    page = pulled(shop_a, start)
    assert each_change(page) == [
        (start + 1, "staff", str(asha.pk), "archive"),
        (start + 2, "staff", str(asha.pk), "archive"),
    ]
    assert [change["data"] for change in page["changes"]] == [None, None]


def test_a_person_switched_on_again_comes_back(shop_a: Shop, dawa: Side) -> None:
    # The superuser switches Neema off in the admin (an archive line), then on again (an upsert). A laptop that asks
    # after both gets her row at each, as she is now, back on the PIN screen: the record decides, not its line's op.
    neema = hire(shop_a, "Neema Mfano", "Neema")
    start = last_line(shop_a)
    neema.user.is_active = False
    change_person(neema.user, changed=["is_active"])
    neema.user.is_active = True
    change_person(neema.user, changed=["is_active"])
    page = pulled(shop_a, start)
    assert each_change(page) == [
        (start + 1, "staff", str(neema.pk), "upsert"),
        (start + 2, "staff", str(neema.pk), "upsert"),
    ]
    assert [change["data"]["display_name"] for change in page["changes"]] == ["Neema", "Neema"]


def test_each_change_carries_its_record_as_the_bootstrap_sends_it(shop_a: Shop, dawa: Side) -> None:
    # A pull and a bootstrap send a record through the same fields (the registry's), so a laptop that bootstrapped and
    # one that pulled hold the same row. Dawa renamed twice: both lines carry the record as it is now, the last name.
    juma = hire(shop_a, "Juma Mfano", "Juma")
    start = last_line(shop_a)
    with shop_context(shop_a):
        dawa = rename_side(dawa, version=dawa.version, name="Dawa Kuu", by=None)
        rename_side(dawa, version=dawa.version, name="Dawa ya Mifugo", by=None)
        suspend(juma, by=None, reason="Likizo ya adhabu")
    first, second, person = pulled(shop_a, start)["changes"]
    assert first["data"] == second["data"] == sent_by_the_bootstrap("side", shop_a, str(dawa.pk))
    assert first["data"]["name"] == "Dawa ya Mifugo"
    assert person["data"] == sent_by_the_bootstrap("staff", shop_a, str(juma.pk))


def test_a_line_of_a_table_devices_dont_keep_is_passed_over(shop_a: Shop, dawa: Side) -> None:
    # A line may name a table no device keeps a copy of: one a later card records before it joins the registry. The
    # pull leaves it out, as there is nothing to send, but counts it: the cursor passes it, so a laptop never stops on
    # it, nor asks for it again. Dawa's stock location stays on the server (the registry has no entry for it).
    start = last_line(shop_a)
    with shop_context(shop_a):
        location = StockLocation.objects.get(side=dawa)
        with recording_changes(shop_a):
            record_change(location)
        rename_side(dawa, version=dawa.version, name="Dawa Kuu", by=None)
    page = pulled(shop_a, start)
    assert each_change(page) == [(start + 2, "side", str(dawa.pk), "upsert")]
    assert page["cursor"] == start + 2
    # A page of such lines alone sends nothing, and still moves the cursor past them.
    with shop_context(shop_a), recording_changes(shop_a):
        record_change(location)
    page = pulled(shop_a, start + 2)
    assert (page["changes"], page["cursor"]) == ([], start + 3)


def test_pull_keeps_to_its_own_shop(shop_a: Shop, dawa: Side, shop_b: Shop, side_b: Side) -> None:
    # Each shop numbers its own changes, and a laptop of shop A gets A's alone: never a line of shop B, nor B's rows,
    # even with every shop open, as a system job has them (03 §5.11). Shop B has more lines than A, so a pull that
    # read every shop's log would show them.
    for _ in range(3):
        with shop_context(shop_b), recording_changes(shop_b):
            record_change(side_b)
    assert last_line(shop_b) > last_line(shop_a)
    own = [(str(dawa.pk), "side"), (str(_drawer_of(dawa)), "payment_account")]
    assert [(change["id"], change["entity"]) for change in pulled(shop_a, 0)["changes"]] == own
    with system_context():
        answer = json.loads(JSONRenderer().render(pull.page(shop_a, 0)))
    assert [(change["id"], change["entity"]) for change in answer["changes"]] == own


def _drawer_of(side: Side) -> Any:
    # The id of a side's cash drawer, the second line add_side writes.
    with shop_context(side.shop_id):
        return REGISTRY["payment_account"].rows(side.shop).get(sides=side).pk


def test_pull_is_read_only_inside_its_own_shop(shop_a: Shop, shop_b: Shop) -> None:
    # T1: shop B open, shop A asked for. The guard would show B's lines and the shop filter none, so a laptop would be
    # told nothing changed, for good. A bug in the calling code, refused loudly instead.
    with shop_context(shop_b), pytest.raises(ShopMismatch):
        pull.page(shop_a, 0)


def reads_of_a_page(shop: Shop, cursor: int) -> int:
    # How many queries one page costs the database, inside the device's shop, as its visit opens it.
    with shop_context(shop), CaptureQueriesContext(connection) as seen:
        pull.page(shop, cursor)
    return len(seen)


def test_a_page_reads_the_log_once_and_each_table_once(shop_a: Shop, dawa: Side) -> None:
    # A page holds up to 1,000 lines: it must cost the same few reads however many it holds, or a laptop back from a
    # busy week would cost the database thousands. One read of the log, then one of each table the page names, for all
    # its records at once. The one exception, as in the bootstrap: each person's keys, two reads each, by the one
    # function the office routes use (held_permissions).
    hire(shop_a, "Juma Mfano", "Juma")
    before = reads_of_a_page(shop_a, 0)
    # Two more sides, each with its drawer: four more lines, not one more read.
    with shop_context(shop_a):
        for code, name in (("F", "Vyakula"), ("M", "Mbegu")):
            add_side(shop=shop_a, code=code, name=name, by=None)
    assert reads_of_a_page(shop_a, 0) == before
    # Two more people: two reads each, for their keys.
    hire(shop_a, "Asha Mfano", "Asha")
    hire(shop_a, "Neema Mfano", "Neema")
    assert reads_of_a_page(shop_a, 0) == before + 2 * 2


def test_every_page_carries_the_server_time_and_the_oldest_app_allowed(
    shop_a: Shop, dawa: Side, settings: Settings
) -> None:
    # Done when: every page carries the server time, an empty one too: a laptop works out how far its own clock is off
    # from it at every sync (03 §6.6). In UTC, as every time the API sends. And the oldest app version that may still
    # sync (03 §6.8): none yet, so any app may; SYNC-13 gives it a form a device can compare with its own version.
    before = timezone.now()
    page = pulled(shop_a, last_line(shop_a))
    after = timezone.now()
    assert list(page) == ["changes", "cursor", "has_more", "server_time", "min_app_version"]
    assert (page["changes"], page["has_more"]) == ([], False)
    assert page["server_time"].endswith("Z")
    assert before <= datetime.fromisoformat(page["server_time"]) <= after
    assert page["min_app_version"] is None
    settings.MIN_APP_VERSION = "0.2.0"
    assert pulled(shop_a, 0)["min_app_version"] == "0.2.0"
