"""backend/tests/conftest.py — the two filled shops the tenancy sweep sends its visitor between
(backend/tests/test_tenancy_sweep.py).

The sweep calls every office route as a staff member of shop B and looks for any row of shop A in the
answers. It can only find a leak of rows that exist, so both shops get rows of every table a route shows,
made the way the app makes them, through the services. The checks never change; this file grows instead:
a card that adds a route over a new table gives both shops a row of it here, and the sweep fails, saying
so, while shop A has none; and a card that adds a route needing query parameters gives them here too
(sweep_queries). Each shop has a paired device: a row of the office device list (AUTH-5), and the visitor the sweep
sends to every device route (sweep_device_clients, AUTH-2); dated rules, which the bootstrap sends (SYNC-2); the
days each shop is closed, which the closures route lists (ATT-8); a worker's photo with its file, whose id the sweep
sends the photo routes as shop B (CTRL-3); a worker's pay rate, which the pay rates route lists, asked about shop
A's worker (WAGE-1); and a worker paid by the day with their days in the book, whom the month page lists (ATT-5). The
demo seed (DATA-1) could fill the shops later.

The sweep knows shop A's rows by their ids, and by the texts and amounts only shop A holds, so that a leak
with no ids, like a report of names and totals, is found too. So give shop A values of its own: names and
amounts no row of shop B holds (B's side is Pembejeo, not a second Dawa), and none that an answer could hold
by itself, like "name", a word every answer has as a key. Words from a field's fixed choices and zero amounts
never count: they are the same in every shop.

The shops and their staff come from backend/conftest.py. Fake data only: the repo is public (03 §10).
"""

import hashlib
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.control.models import AttachmentKind, AttachmentType
from apps.control.services import expect_attachment, receive_attachment_file
from apps.core.permissions import RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON, CASH_TOLERANCE, LATE_FINE
from apps.core.tenancy import shop_context
from apps.people.device_keys import DEVICE_KEY_COOKIE
from apps.people.models import StaffMember, User
from apps.people.services import Outage, add_staff, confirm_pairing, record_outages, start_pairing
from apps.shops.models import Setting, Shop, Side
from apps.shops.selectors import shop_today
from apps.shops.services import add_closure, add_side
from apps.staffpay.services import set_pay_rate, work_out_days

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]


@pytest.fixture
def sweep_shops(
    sweep_sides: tuple[Shop, Shop],
    sweep_device_keys: tuple[str, str],
    sweep_settings: tuple[Shop, Shop],
    sweep_closures: tuple[Shop, Shop],
    sweep_attachments: tuple[Shop, Shop],
    sweep_pay_rates: tuple[Shop, Shop],
    sweep_attendance: tuple[Shop, Shop],
) -> tuple[Shop, Shop]:
    # Shop A, whose rows must never show, and shop B, the visitor's own, each filled with every table below: their
    # sides, a paired device each, which the office device list shows (AUTH-5), with an offline period the health page
    # shows (SYNC-14), dated rules, which the bootstrap sends (SYNC-2), days closed, which the closures route lists
    # (ATT-8), a photo with its file, which the photo routes are asked about (CTRL-3), a worker's pay rate, which
    # the pay rates route lists (WAGE-1), and a worker's days in the book, which the month page lists (ATT-5).
    return sweep_sides


@pytest.fixture
def sweep_sides(shop_a: Shop, shop_b: Shop, staff_a: StaffMember, staff_b: StaffMember) -> tuple[Shop, Shop]:
    # add_side makes each side with its stock location, its cash drawer and the drawer's link to the side, so four
    # tables at once; the staff members are rows of a fifth. Each write runs inside its own shop, as a service needs
    # (T1).
    with shop_context(shop_a):
        add_side(shop=shop_a, code="D", name="Dawa", by=staff_a)
        add_side(shop=shop_a, code="F", name="Vyakula", by=staff_a)
    with shop_context(shop_b):
        add_side(shop=shop_b, code="P", name="Pembejeo", by=staff_b)
    return shop_a, shop_b


@pytest.fixture
def sweep_settings(sweep_sides: tuple[Shop, Shop]) -> tuple[Shop, Shop]:
    # Each shop's own late fine, and a tolerance for its own first side: rows the bootstrap sends a device (SYNC-2),
    # with amounts only that shop holds. From a day long past, so both stay in force whatever day the tests run.
    # Checked, then saved, as set_setting saves one (SHOP-3), but with no line and on a past day, which the service
    # refuses: the sweep reads the rows, not the log.
    for shop, side_code, fine, tolerance in (
        (sweep_sides[0], "D", "1250.00", "350.00"),
        (sweep_sides[1], "P", "1750.00", "450.00"),
    ):
        with shop_context(shop):
            side = Side.objects.get(code=side_code)
            for key, value, on_side in ((LATE_FINE, fine, None), (CASH_TOLERANCE, tolerance, side)):
                row = Setting(shop=shop, side=on_side, key=key.key, value=value, effective_from=date(2026, 1, 1))
                row.full_clean()
                row.save()
    return sweep_sides


@pytest.fixture
def sweep_closures(sweep_sides: tuple[Shop, Shop], staff_a: StaffMember, staff_b: StaffMember) -> tuple[Shop, Shop]:
    # Each shop closes for three days, ten days from now, under a name only that shop holds: the closures route lists
    # those to come (ATT-8), so they show whatever day the tests run. Added the way the app adds them (add_closure), by
    # each shop's own staff member, whose nickname the route shows beside the closure.
    for shop, staff, name in (
        (sweep_sides[0], staff_a, "Msiba wa Mfano"),
        (sweep_sides[1], staff_b, "Sikukuu ya Jirani"),
    ):
        with shop_context(shop):
            first = shop_today(shop) + timedelta(days=10)
            add_closure(shop, first_day=first, last_day=first + timedelta(days=2), name=name, by=staff)
    return sweep_sides


@pytest.fixture
def sweep_attachments(sweep_sides: tuple[Shop, Shop], staff_a: StaffMember, staff_b: StaffMember) -> tuple[Shop, Shop]:
    # Each shop's worker has a photo, its row written as its record would bring it (expect_attachment) and its file
    # sent after it (receive_attachment_file), as the laptop does (CTRL-3). The sweep asks the photo routes about shop
    # A's as shop B: the laptop's upload and the office's file, which A's own staff opens first. Each photo is bytes
    # only that shop's has, starting as a JPEG does, so its fingerprint is shop A's mark too.
    for shop, staff in ((sweep_sides[0], staff_a), (sweep_sides[1], staff_b)):
        photo = b"\xff\xd8\xff" + f"made-up photo of {staff.display_name}".encode()
        photo_id = uuid.uuid7()
        with shop_context(shop):
            expect_attachment(
                id=photo_id,
                kind=AttachmentKind.STAFF_PHOTO,
                subject=staff,
                content_type=AttachmentType.JPEG,
                size=len(photo),
                sha256=hashlib.sha256(photo).hexdigest(),
                by=staff,
            )
            receive_attachment_file(photo_id, content=photo)
    return sweep_sides


@pytest.fixture
def sweep_pay_rates(sweep_sides: tuple[Shop, Shop], staff_a: StaffMember, staff_b: StaffMember) -> tuple[Shop, Shop]:
    # Each shop's worker has a daily rate from their first day, of an amount and with a note only that shop holds: the
    # pay rates route lists a worker's (WAGE-1), and the sweep asks it about shop A's worker (sweep_queries), as shop B
    # too. Set the way the app sets one (set_pay_rate), by the system, as the demo's seed sets one.
    for shop, staff, amount, note in (
        (sweep_sides[0], staff_a, "13579", "Kiwango cha Mfano"),
        (sweep_sides[1], staff_b, "24680", "Kiwango cha Jirani"),
    ):
        with shop_context(shop):
            set_pay_rate(staff, daily_rate=Decimal(amount), effective_from=staff.started_on, note=note, by=None)
    return sweep_sides


@pytest.fixture
def sweep_attendance(sweep_sides: tuple[Shop, Shop]) -> tuple[Shop, Shop]:
    # Each shop switched attendance on in January and has a worker paid by the day since 40 days ago, under a nickname
    # only that shop holds: the month page lists them (ATT-5), and the sweep asks it for the month of yesterday
    # (sweep_queries), the last day the book keeps. Their days are worked out here, as the page's first visit would,
    # so shop A has days in the book for the sweep to look for. The switch is saved as set_setting saves a rule, but on
    # a day gone by, which the service refuses, as sweep_settings does; the worker and the rate through the services.
    for shop, name, amount in (
        (sweep_sides[0], "Mhudhuriaji Mfano", "11223"),
        (sweep_sides[1], "Mhudhuriaji Jirani", "33221"),
    ):
        with shop_context(shop):
            row = Setting(shop=shop, key=ATTENDANCE_ON.key, value="true", effective_from=date(2026, 1, 1))
            row.full_clean()
            row.save()
            started = shop_today(shop) - timedelta(days=40)
            user = User.objects.create_user(full_name=f"{name} Demo")
            worker = add_staff(shop=shop, user=user, display_name=name, started_on=started, by=None)
            set_pay_rate(worker, daily_rate=Decimal(amount), effective_from=started, by=None)
            work_out_days(shop, started, shop_today(shop) - timedelta(days=1))
    return sweep_sides


@pytest.fixture
def sweep_device_keys(
    sweep_sides: tuple[Shop, Shop], staff_a: StaffMember, staff_b: StaffMember, give_role: GiveRole
) -> tuple[str, str]:
    # One paired device in each sweep shop: a row the office device list shows (AUTH-5), and the key of a browser the
    # sweep sends to every device route (sweep_device_clients, AUTH-2). Paired the way the app pairs one: the device
    # asks (start_pairing), and the shop's owner confirms its code on a side of the shop. Each device's name is its
    # shop's alone, so a route that showed shop A's device to shop B's would be caught by the name too, beside its id.
    # Each device also reported an offline period an hour ago, which the health page shows (SYNC-14): rows of a
    # second table on the device routes, its ids shop A's alone.
    shop_a, shop_b = sweep_sides
    keys = []
    for owner, shop, side_code, name in (
        (staff_a, shop_a, "D", "Laptop ya Mfano"),
        (staff_b, shop_b, "P", "Simu ya Jingine"),
    ):
        give_role(owner, RoleTemplate.OWNER, None)
        asked = start_pairing()
        with shop_context(shop):
            device = confirm_pairing(
                asked.request.code, name=name, home_side=Side.objects.get(code=side_code), by=owner
            )
            went = timezone.now() - timedelta(hours=1)
            record_outages(device, [Outage(id=uuid.uuid7(), started_at=went, ended_at=went + timedelta(minutes=10))])
        keys.append(asked.key)
    return keys[0], keys[1]


@pytest.fixture
def sweep_device_clients(sweep_device_keys: tuple[str, str]) -> tuple[APIClient, APIClient]:
    # The browsers that hold the two devices' keys: the visitors the sweep sends to every device route (AUTH-2).
    clients = []
    for key in sweep_device_keys:
        client = APIClient()
        client.cookies[DEVICE_KEY_COOKIE] = key
        clients.append(client)
    return clients[0], clients[1]


@pytest.fixture
def sweep_queries(shop_a: Shop, staff_a: StaffMember) -> dict[str, dict[str, str]]:
    # The query parameters a GET route can't answer without, by the route's name. They must be ones under which
    # shop A's rows show: a day's report asks for the day the rows above are made on, the test's today, as in
    # {"daily-report-list": {"date": str(timezone.localdate())}}, never a fixed date, which would show nothing to
    # either shop. Without them such a route answers 400; with ones that show nothing, even shop A's own staff
    # sees nothing; either way the sweep fails and points here. The pay rates route names its worker (WAGE-1): shop
    # A's, whose rate sweep_pay_rates sets, so shop B is asked about another shop's worker by their real id. The month
    # page names its month (ATT-5): yesterday's, as the book keeps no day before it is over, so on the 1st this
    # month would list nobody.
    yesterday = shop_today(shop_a) - timedelta(days=1)
    return {
        "pay-rate-list": {"staff": str(staff_a.pk)},
        "attendance-month-list": {"month": yesterday.strftime("%Y-%m")},
    }
