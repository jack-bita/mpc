"""apps/demo/services.py — the demo seed: wipes a demo-only database, then makes the demo shop again (DATA-1); and
the one-tap demo, which makes a visitor's browser a device of that shop (OPS-3).

It owns the demo shop as visitors meet it (Jack, 8 Nov 2026): Duka la Mfano, a demo shop with the sides Dawa and
Vyakula; Meneja, its manager on both sides, who logs in with a password; Asha, a seller on Dawa, and Baraka, a seller
on Vyakula, who log in with a PIN. Meneja also holds settings.manage on the whole shop, one of the owner's own keys,
so a visitor can try Badilisha on Mipangilio ya duka (Jack, SHOP-5, 15 Nov 2026): a manager alone may not change the
shop's rules, and the demo has no owner. A visitor's new value starts tomorrow or later, with no note, so the seed
makes the shop again before it comes (set_setting: demo.rules_from_tomorrow, demo.no_note, Jack, SHOP-5's second
review); and the sides stay as the seed made them, as the same key also switches, renames and adds them
(demo.sides_fixed). Meneja holds staff.manage on the whole shop too, so a visitor can try Wafanyakazi (Jack, PPL-4: A):
add a worker, then suspend him or mark him left; the people the seed made stay as made (demo.people_fixed,
apps/people/services.py), so no visitor takes Asha or Baraka off another visitor's PIN tiles. The shop starts with
attendance switched on and two made-up fines (DEMO_RULES, ATT-2), closed on the next three public holidays
(PUBLIC_HOLIDAYS, ATT-8), and each of its people paid a made-up daily rate from their first day (DemoPerson.daily_rate,
WAGE-1), which a visitor sees on Meneja's Wafanyakazi and can't change, as the seed's people stay as made.

And the days before today, from the 1st of last month (DATA-8, DATA-2): the demo is made again every morning, and the
book keeps only days that are over (ATT-10), so Mahudhurio ya mwezi (ATT-5) would list nobody; and a month's pay is
approved once the month is over (WAGE-3), so a visitor finds one to approve on any day only if the demo holds a whole
month gone by. So the shop's rules, its people's first days and their rates start on the 1st of the month before
today's (_history_starts): on 28 November, 1 October, the whole of October and November up to yesterday. The demo's
laptop, Laptop ya Dawa, sends those days' Ingia and Toka through the push, as a laptop back online does: most days on
time, and the newest few, counted back from yesterday, late with their fine, a half day, an absent day, and days to
decide (DemoPerson.odd_days). The minutes come from a fixed random seed, so every reset makes the same taps.

And last month's own days (DATA-2), so the month a visitor approves is like a real one, and its payslips show every kind
of line (Jack: A, 28 Nov 2026): counted forward from the month's 1st, Meneja late once, Asha late once and a half day,
Baraka absent once and late after 08:00, and an advance of Asha's (DemoPerson.last_month_days, LAST_MONTH_ADVANCES).
None waits for a decision, so last month is approved at once, but on a month's first working days, when the newest days
to decide, counted back from yesterday, fall in it too: the visitor decides them first, as an owner would.

And three flags for Meneja's Tofauti (CTRL-4), made by the same laptop's pushes: one of its taps is sent last, after the
later ones, so its missing number is flagged and then closed by the system, as a late record's is; and after the last
tap it sends a record the server doesn't know, one number too far, so a missing number and a refused record both wait.
None is about a tap's time or its worker, so none sends a day to review.

And the meal money of those days (WAGE-7), typed by Meneja, who holds its key, meals.record, so a visitor sees on Hela
ya chakula how each day's is split, and can type today's: 3,000 on each working day but one, forgotten, which the page
calls Haijaandikwa. What a visitor types takes no note, and crossing out one takes the ready reason, as typed words
would show to every visitor after them (record_meal_money, void_meal_money).

And three advances of those days (WAGE-8, DATA-2), typed by Meneja, who holds their key, money.advance, as every
manager does: two of the newest days, Asha's and Baraka's, and one of last month's, Asha's, which Advansi lists and
their pay takes off, and any of which a visitor can cross out, with the ready reason, as for the meal money
(record_advance, void_advance).

And Meneja holds pay.approve (WAGE-3), the owner's own key to Idhinisha: a visitor adds a worker with a daily pay, marks
them left once a day of theirs is over, and approves their pay alone, on their own page; or approves last month for
everyone, which the demo always holds whole (DATA-2). The seed approves nothing itself, as a closed month takes no
change and a visitor should find each of them open; what a visitor approves stays closed until the next reset.

`manage.py seed_demo` (management/commands/seed_demo.py) runs it, on every start of the demo (backend/start-demo.sh)
and of the browser tests' container, which starts the same way (compose.e2e.yml):
the tests log in as these people, with the logins written again in frontend/e2e/pair-and-pin-login.spec.ts. Change
both together.

Why it wipes the whole database instead of taking out the demo shop's rows: the ledgers refuse every DELETE
(ADR-0021, apps/core/operations.py), and every link PROTECTs what it points at (rule 7), so a shop's rows can't be
taken out one by one. Django's `flush` empties every table of the apps' models at once (TRUNCATE), which the ledgers'
triggers don't watch; the cache tables (the pairing limits' counts) and Django's list of the migrations stay. That is
safe only on a database that holds nothing but demo data, so the seed refuses, before it writes anything, in two cases:
  1. without the sign: DEMO_SEED=yes in the environment (config/settings/base.py). Only places that hold demo data
     set it, and the real server never does, so even a brand-new real server, with no shop yet, refuses (Jack,
     8 Nov 2026);
  2. with any shop that isn't a demo one: a live shop's data is real, and a practice shop copies a live one
     (ADR-0014, ADR-0029).

Once a day, not on every start (DATA-1's plan, 8 Nov 2026): the free demo sleeps after 15 minutes with no visitor,
and every wake-up runs its start again. A visitor back from a break should find the PIN screen with their work still
there (the idle lock, UI-4), so a start keeps a demo shop made today, in the shop's own time, and makes it again only
when it was made on an earlier day, or lacks a rule, a closure, a person's extra key or rate, the taps, the meal money
or the advances of the days before today, or the flags this seed sets, as a demo an older seed made that morning does on
a deploy's day (ATT-2, ATT-8, #275, WAGE-1, DATA-8, WAGE-7, WAGE-8, CTRL-4). `fresh=True` makes it again whatever its
day.

Made through the services, as a real shop is set up (set_up_shop, add_staff, assign_role, set_pin), never by writing
rows: the demo can't hold anything a real shop couldn't, and a service that changes its rules changes the demo too.

It also owns the one-tap demo (OPS-3, BP15): a recruiter has no manager to confirm a pairing code, so *Jaribu demo*
makes the visitor's browser a device of the demo shop at once (register_demo_device), and hands it the sellers' PINs
from PEOPLE below, the one list the seed sets them from, for the PIN screen to show under their tiles; and the
manager's login, for his tile, which opens the password login with both boxes filled (OPS-13). It is open only
where the seed itself may run, and the seed has made the demo shop (demo_shop_if_open): the same sign and the same
"no shop but a demo one" that keep the wipe shut keep this shut on the real server.

Fake data only (rule 10): the names are made up, and the password and the PINs are public on purpose, because
visitors need them. Nobody here is staff in Django's sense (`is_staff`), so no seeded login opens the admin, whose
login page has no rate limit yet (04 DATA-1, v1.8).
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import OperationalError, connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.changes import recording_changes
from apps.core.permissions import Permission, RoleTemplate
from apps.core.settings_registry import ATTENDANCE_ON, LATE_FINE, SECOND_FINE, SettingKey
from apps.core.tenancy import shop_context
from apps.people.models import Device, PermissionGrant, Role, StaffMember, User
from apps.people.services import (
    add_staff,
    assign_role,
    confirm_pairing,
    grant_permission,
    set_pin,
    set_up_shop,
    start_pairing,
)
from apps.shops.models import Closure, Setting, Shop, ShopKind, Side, SideBand
from apps.shops.selectors import shop_today
from apps.shops.services import NewSide, add_closure, set_setting, switch_side
from apps.staffpay.models import Advance, AttendanceEvent, ClockKind, MealMoney, NoPhoto, PayRate
from apps.staffpay.services import SUNDAY, record_advance, record_meal_money, set_pay_rate
from apps.sync.api.serializers import MOST_DOCUMENTS
from apps.sync.models import PushedDocument, PushedStatus
from apps.sync.push import Answer, Sent, push

SHOP_NAME = "Duka la Mfano"
SHOP_CODE = "DEMO"
# The two sides MPC has, in the words the app already uses for them (Jack, 8 Nov 2026). Vyakula's band is striped, like
# the Foods bags, and Dawa keeps the blue one (SHOP-4, UI-8).
SIDES = (NewSide("D", "Dawa"), NewSide("F", "Vyakula", band=SideBand.STRIPED))


@dataclass(frozen=True)
class OddDay:
    # A day of a demo person's that isn't an ordinary one (DATA-8). `back`: its place among the working days before
    # today, 1 the latest (_working_days_back), so it never falls on a Sunday, wherever today falls. `came` and `left`:
    # the minutes of their Ingia and Toka by the shop's clock, None for no tap.
    back: int
    came: time | None
    left: time | None


@dataclass(frozen=True)
class LastMonthDay:
    # A day of last month's that isn't an ordinary one (DATA-2), so the month a visitor approves has every kind of line
    # on its payslips (Jack: A). `place`: its place among last month's working days, 1 its first (_last_months_days),
    # so it never falls on a Sunday; nor on an OddDay, which counts back from yesterday, as a month has at least 24
    # working days and the newest reach 13 back (test_seed_demo_odd_days_never_meet). `came` and `left`: as an OddDay's.
    place: int
    came: time | None
    left: time | None


# The manager's login. example.com is a domain kept for examples, so no real mailbox is ever sent a reset. The
# password is public: it opens only the demo's fake shop, which is made again every day.
MANAGER_EMAIL = "meneja@example.com"
MANAGER_PASSWORD = "jaribu-demo"


# PostgreSQL's code for "deadlock detected": two transactions each waiting for the other, one of which it ends.
DEADLOCK = "40P01"


@dataclass(frozen=True)
class DemoPerson:
    # One person of the demo shop, as the seed makes them. `side`: the letter of the side their role is on, None for
    # every side, as a shop's manager is. `pin`: four digits the PIN rules allow (apps/people/pins.py), or None for
    # a person who logs in only with their password. `keys`: extra keys beyond the role's, each on the whole shop,
    # given as an owner gives one (grant_permission). `daily_rate`: their made-up pay for a day, in whole shillings,
    # from their first day (set_pay_rate, WAGE-1), or None for one paid no day, as a shop's owner is. `odd_days`: the
    # newest days before today that aren't ordinary (DATA-8); `last_month_days`: last month's that aren't (DATA-2);
    # every other working day, they came on time.
    full_name: str
    display_name: str
    role: RoleTemplate
    side: str | None
    pin: str | None = None
    email: str | None = None
    password: str | None = None
    keys: tuple[Permission, ...] = ()
    daily_rate: str | None = None
    odd_days: tuple[OddDay, ...] = ()
    last_month_days: tuple[LastMonthDay, ...] = ()


PEOPLE = (
    # The manager on every side: device.manage among the role's keys lets them confirm a new laptop on either side
    # (confirm_pairing). A password and no PIN: the manager works from their own phone, as at a real shop.
    # And four of an owner's own keys (see the top of this file): the shop's rules, the one key a visitor needs to try
    # Mipangilio ya duka, which also changes the sides, kept as the seed made them on the demo
    # (_check_sides_fixed_on_demo, apps/shops/services.py); and its workers, to try Wafanyakazi (PPL-4), whose
    # services keep the seed's people as made on the demo (demo.people_fixed, apps/people/services.py), as a visitor
    # who suspended Asha, or took Meneja's role away, would stop every visitor after them (OPS-3's note). And the meal
    # money's, the owner's own too, to try Hela ya chakula (WAGE-7); and the approval's, to try Idhinisha (WAGE-3). Not
    # the Owner's whole role, whose keys reach further than a visitor needs.
    DemoPerson(
        "Meneja Mfano",
        "Meneja",
        RoleTemplate.MANAGER,
        side=None,
        email=MANAGER_EMAIL,
        password=MANAGER_PASSWORD,
        keys=(
            Permission.SETTINGS_MANAGE,
            Permission.STAFF_MANAGE,
            Permission.MEALS_RECORD,
            Permission.PAY_APPROVE,
        ),
        # Made-up amounts, as everything here is (rule 10): a manager paid a little more than a seller.
        daily_rate="15000",
        # He clocks in too, on the shop's laptop with his password (OPS-13): he has a daily rate, so the month page
        # lists him (ATT-5), and with no taps every day of his would be absent. Late once, the first fine.
        odd_days=(OddDay(8, came=time(7, 42), left=time(18, 50)),),
        # And once in last month, on its 2nd working day, the first fine too (DATA-2).
        last_month_days=(LastMonthDay(2, came=time(7, 45), left=time(18, 50)),),
    ),
    # A seller on each side, with a PIN only: they log in at the shop's laptop, as a seller does.
    DemoPerson(
        "Asha Mfano",
        "Asha",
        RoleTemplate.SELLER,
        side="D",
        pin="2580",
        daily_rate="10000",
        # The days the month page shows a visitor (ATT-5), against the demo's rules (DEMO_RULES, and the attendance
        # day's own times: on time to 07:35, the second fine from 08:00, closing 18:40): a day to decide, her latest,
        # an Ingia with no Toka (no_out); another, her third latest, out at 15:00, before closing (left_early), so a
        # visitor who decides one still finds days to decide, each with a reason of its own (Jack: A, ATT-6's
        # review); late, the first fine; late after 08:00, the second; and the morning's half day, out between 13:00
        # and 13:30.
        odd_days=(
            OddDay(1, came=time(7, 25), left=None),
            OddDay(3, came=time(7, 20), left=time(15, 0)),
            OddDay(4, came=time(7, 50), left=time(18, 50)),
            OddDay(9, came=time(8, 10), left=time(18, 45)),
            OddDay(13, came=time(7, 20), left=time(13, 10)),
        ),
        # Last month (DATA-2): late on its 3rd working day, the first fine; and the morning's half day on its 6th, out
        # at 13:15, no fine, as she came on time.
        last_month_days=(
            LastMonthDay(3, came=time(7, 50), left=time(18, 50)),
            LastMonthDay(6, came=time(7, 20), left=time(13, 15)),
        ),
    ),
    # Late once, and absent once: no tap at all, so the book answers absent (ATT-4). And a day to decide, his second
    # latest: in at 09:10, after 08:30, the owner's dharura (came_late, ATT-6's review).
    DemoPerson(
        "Baraka Mfano",
        "Baraka",
        RoleTemplate.SELLER,
        side="F",
        pin="1470",
        daily_rate="10000",
        odd_days=(
            OddDay(2, came=time(9, 10), left=time(18, 45)),
            OddDay(6, came=time(7, 45), left=time(18, 55)),
            OddDay(11, came=None, left=None),
        ),
        # Last month (DATA-2): absent on its 4th working day, no tap; and late after 08:00 on its 7th, in at 08:05,
        # before 08:30, so the second fine and no day to decide.
        last_month_days=(
            LastMonthDay(4, came=None, left=None),
            LastMonthDay(7, came=time(8, 5), left=time(18, 45)),
        ),
    ),
)

# The meal money of each working day before today (WAGE-7), a made-up 3,000: 1,000 each when all three came. But one
# day, its place among them as an OddDay's `back`, an ordinary day, has none: forgotten, Haijaandikwa.
MEALS_A_DAY = Decimal("3000")
FORGOTTEN_MEALS_BACK = 5

# The money given before payday (WAGE-8), made up: to whom, on which of the working days before today, as an OddDay's
# `back`, and how much. Baraka's of the latest, so this month's Advansi has a line from its second working day on.
ADVANCES = (
    ("Asha", 8, Decimal("20000")),
    ("Baraka", 1, Decimal("30000")),
)
# And last month's own (DATA-2): Asha's, on its 5th working day, as a LastMonthDay's `place`, so its payslip takes one
# off. Made up, as every amount here is.
LAST_MONTH_ADVANCES = (("Asha", 5, Decimal("15000")),)

# The demo's own laptop (DATA-8), which sends the taps of the days before today: on Dawa, as a shop's laptop sits on a
# side. Anyone working at the shop may clock in on it (Jack, ATT-1), Baraka of Vyakula too.
DEMO_LAPTOP_NAME = "Laptop ya Dawa"
DEMO_LAPTOP_SIDE = "D"
# The type of the record the demo's laptop sends and the server refuses (CTRL-4): a name no card's documents will take,
# which is checked as it is sent (_send_a_refused_record).
DEMO_UNKNOWN_TYPE = "demo_unknown"

# The seed of the random minutes of an ordinary day: a fixed one, so every reset makes the same taps (DATA-1's first
# box, the same shop every time). Any number does; changing it changes every minute.
TAPS_SEED = 8

# An ordinary day's taps: Ingia from 07:10, within ON_TAPS minutes, so by 07:34, before on time ends (07:35); Toka from
# 18:40, closing, within OFF_TAPS, so by 19:05.
ON_TIME_FROM = time(7, 10)
ON_TAPS = 24
CLOSING_FROM = time(18, 40)
OFF_TAPS = 25

# When the demo's laptop last heard from the server (`last_server_time`, ATT-1's sign 2): 06:50 on the first of the
# demo's days, before any tap, as a laptop offline since that morning, which sends them all as it comes back.
LAST_HEARD = time(6, 50)

# The side a one-tap demo device serves (OPS-3): Dawa, where Asha sells. Any seller can still log in on it.
DEMO_DEVICE_SIDE = "D"

# The demo's own rules (ATT-2), set by the system from the demo's first day, the 1st of last month, as its laptop's
# taps start there (_history_starts, DATA-2). Attendance switched on, as an owner switches
# a real shop's on at its go-live (ADR-0033): the demo shows a shop at work, so its laptops keep Mahudhurio. And two
# made-up fines: a shop's fines start at nothing, as this public repo names no real amount (rule 10, Jack, 16 Nov
# 2026), and a visitor should still see a late day's fine. Not the owner's amounts: those he types on the real server.
DEMO_RULES: tuple[tuple[SettingKey[Any], str], ...] = (
    (ATTENDANCE_ON, "true"),
    (LATE_FINE, "500"),
    (SECOND_FINE, "1500"),
)


@dataclass(frozen=True)
class PublicHoliday:
    # One of Tanzania's public holidays that falls on the same date every year (ATT-8): Siku ya Uhuru, 9 December.
    # `days`: how many days it closes the shop, from that date on.
    name: str
    month: int
    day: int
    days: int = 1


# The demo's closures come from these (ATT-8): public facts, not a shop's own data. Only those with a fixed date: Eid
# and Easter move each year, and a real owner types their dates himself. Krismasi and the day after it as one closure of
# two days, as a shop closes for both. Each name in Swahili, as an owner would type it: a closure's name is the shop's
# own words, which the screens show as they are.
PUBLIC_HOLIDAYS = (
    PublicHoliday("Mwaka Mpya", 1, 1),
    PublicHoliday("Mapinduzi ya Zanzibar", 1, 12),
    PublicHoliday("Siku ya Karume", 4, 7),
    PublicHoliday("Siku ya Muungano", 4, 26),
    PublicHoliday("Siku ya Wafanyakazi", 5, 1),
    PublicHoliday("Saba Saba", 7, 7),
    PublicHoliday("Nane Nane", 8, 8),
    PublicHoliday("Siku ya Nyerere", 10, 14),
    PublicHoliday("Siku ya Uhuru", 12, 9),
    PublicHoliday("Krismasi", 12, 25, days=2),
)

# How many of them the demo closes on: enough for the page to show a list, few enough for a visitor to read it at once.
DEMO_CLOSURES = 3


def coming_public_holidays(today: date) -> list[tuple[date, date, str]]:
    """The next DEMO_CLOSURES public holidays from `today` on, today's own among them, each as (first day, last day,
    name), soonest first. One that began before today is left out, as a closure can't start in the past
    (closure.date_past): on 26 December, Krismasi has begun."""
    spans = []
    # This year's and next year's: on 26 December none of this year's is left, and next year has more than three.
    for year in (today.year, today.year + 1):
        for holiday in PUBLIC_HOLIDAYS:
            first = date(year, holiday.month, holiday.day)
            if first >= today:
                spans.append((first, first + timedelta(days=holiday.days - 1), holiday.name))
    return sorted(spans)[:DEMO_CLOSURES]


class Seeded(StrEnum):
    # What a run did, for the command's output line.
    MADE = "made"
    KEPT = "kept"


def seed_demo(*, fresh: bool = False) -> Seeded:
    """Make the demo shop again on a database that holds only demo data, or keep today's (see above). `fresh`: make it
    again even if it was made today. Refuses with a ValidationError, before anything is written, without the sign or
    with a shop that isn't a demo."""
    # The look, then the wipe. A shop someone made in the split second between them would be wiped too. Left open on
    # purpose (Jack, 8 Nov 2026): nothing on the demo can make a shop (no admin account, no route that makes one), and
    # the real server never has the sign, so the look already rules it out; closing it would take a table lock written
    # in SQL by hand, for a case that can't occur.
    _check_may_seed()
    if (
        not fresh
        and (shop := _made_today()) is not None
        and _holds_its_rules(shop)
        and _holds_its_closures(shop)
        and _holds_its_keys(shop)
        and _holds_its_rates(shop)
        and _holds_its_taps(shop)
        and _holds_its_meals(shop)
        and _holds_its_advances(shop)
        and _holds_its_flags(shop)
    ):
        return Seeded.KEPT
    try:
        _wipe_and_make()
    except OperationalError as clash:
        # A deploy on Render starts the new demo while the old one still serves, on the same database. The wipe needs
        # every table to itself; a visitor's request on the old one that holds one table and waits for another can
        # meet it halfway, each waiting for the other, and PostgreSQL ends one of the two (a deadlock). If it ended the
        # seed, its transaction was taken back whole, so one more try finds the request gone. Once only: a second clash,
        # or any other database error, stops the start, which the deploy's smoke test then shows red.
        if getattr(clash.__cause__, "sqlstate", None) != DEADLOCK:
            raise
        ContentType.objects.clear_cache()
        _wipe_and_make()
    return Seeded.MADE


def _wipe_and_make() -> None:
    # One transaction around the wipe and the new shop: if any step of the shop is refused, the wipe is taken back
    # too, so a failed start leaves yesterday's demo as it was, never an empty one.
    with transaction.atomic():
        # Django's links between rows are checked when a transaction commits, not as each row is written (PostgreSQL's
        # deferred checks). Rows written earlier in this same transaction leave those checks waiting, and PostgreSQL
        # won't empty a table while checks on it wait ("pending trigger events"). The demo's start never writes first,
        # but a caller that seeds twice in one transaction does, as a test does. Running the waiting checks now clears
        # them, and a broken link would still fail loudly here.
        connection.check_constraints()
        # interactive=False: no "are you sure?" prompt, which nobody is there to answer on the demo's start.
        # verbosity=0: flush says nothing; the command prints its own line. After emptying the tables, flush makes
        # Django's own rows again (its content types and permissions), as `migrate` makes them.
        call_command("flush", interactive=False, verbosity=0)
        # Django keeps each content type's id in memory. flush made them again with new ids, so the old ones are
        # forgotten, or this process could hand out an id that no longer exists.
        ContentType.objects.clear_cache()
        _make_the_shop()


def _check_may_seed() -> None:
    # The two refusals, both before anything is written. Codes, as every refusal has (ADR-0040): the command prints
    # the sentence, a test reads the code.
    if not settings.DEMO_SEED:
        raise ValidationError(
            "Refused: DEMO_SEED=yes is not set. The demo seed wipes the database, "
            "so it runs only where demo data lives.",
            code="demo.no_sign",
        )
    # Shop has no tenancy guard (it is the shop itself, rule 1), so this looks across every shop, as it must.
    if Shop.objects.exclude(kind=ShopKind.DEMO).exists():
        raise ValidationError(
            "Refused: the database holds a shop that isn't a demo. The demo seed never wipes a real shop's data.",
            code="demo.other_shop",
        )


def _made_today() -> Shop | None:
    # The demo shop, when it exists and was made today, in the shop's own time zone: the night in Arusha, not in UTC,
    # decides when a new day starts (02 §1). None otherwise.
    shop = Shop.objects.filter(kind=ShopKind.DEMO, code=SHOP_CODE).first()
    if shop is None:
        return None
    made_on = timezone.localtime(shop.created_at, ZoneInfo(shop.timezone)).date()
    return shop if made_on == shop_today(shop) else None


def _holds_its_rules(shop: Shop) -> bool:
    # Whether today's demo holds every rule this seed sets (DEMO_RULES), as the system set them. A deploy starts the
    # new code on a demo the old code made that morning: without this, a seed that sets a new rule would keep that
    # demo all day, as ATT-2's first deploy would have, with attendance off and no fine until the next morning. A
    # visitor's own rows don't count, but never hide the seed's either: rows are only ever added (ADR-0013).
    with shop_context(shop):
        set_by_the_system = set(
            Setting.objects.filter(shop=shop, created_by__isnull=True).values_list("key", flat=True)
        )
    return {rule.key for rule, _value in DEMO_RULES} <= set_by_the_system


def _holds_its_keys(shop: Shop) -> bool:
    # Whether today's demo gives each of the seed's people every extra key this seed gives them (DemoPerson.keys), on
    # the whole shop, as the seed gives them: as for its rules, a deploy whose seed gives a person a new key must not
    # keep a demo made that morning without it. PPL-4's deploy kept a Meneja with no staff.manage, so the workers' page
    # stayed out of every visitor's reach until the next morning (#275). The person is found by their nickname among
    # those the system made (created_by empty): a visitor's own workers never count. Only keys that still count: one
    # taken away (PPL-7) is no key, so a seed that finds one ended makes the demo again. Nothing a visitor does takes a
    # seed person's key away, as the seed's people stay as made (demo.people_fixed).
    wanted = {person.display_name: set(person.keys) for person in PEOPLE if person.keys}
    with shop_context(shop):
        given = PermissionGrant.objects.filter(
            shop=shop,
            side__isnull=True,
            ended_at__isnull=True,
            staff__created_by__isnull=True,
            staff__display_name__in=wanted,
        ).values_list("staff__display_name", "permission")
        held: dict[str, set[str]] = {}
        for name, permission in given:
            held.setdefault(name, set()).add(permission)
    return all(keys <= held.get(name, set()) for name, keys in wanted.items())


def _holds_its_rates(shop: Shop) -> bool:
    # Whether today's demo pays each of the seed's people the daily rate this seed gives them (DemoPerson.daily_rate),
    # as the system set it: as for its rules, a deploy whose seed gives its people a rate must not keep a demo made that
    # morning without one, or Wafanyakazi would show no pay until the next morning (WAGE-1). The person is found by
    # their nickname among those the system made, as for the keys; the amount by its rows the system set. Nothing a
    # visitor does changes a seed person's rate (demo.people_fixed), and a rate is never changed, only added to.
    wanted = {(person.display_name, Decimal(person.daily_rate)) for person in PEOPLE if person.daily_rate is not None}
    with shop_context(shop):
        set_by_the_system = set(
            PayRate.objects.filter(shop=shop, created_by__isnull=True, staff__created_by__isnull=True).values_list(
                "staff__display_name", "daily_rate"
            )
        )
    return wanted <= set_by_the_system


def _holds_its_taps(shop: Shop) -> bool:
    # Whether today's demo holds the taps of the days before today this seed sends (DATA-8): as for its rules, a deploy
    # whose seed sends them must not keep a demo an older seed made that morning, with no day before today, or the month
    # page would list nobody until the next morning. Counted: the taps of the seed's own people (created by nobody, as
    # for the keys), timed before today, at least as many as this seed sends. Nothing a visitor does lowers it: a
    # visitor's tap at the counter is today's; one a visitor adds in the office, on a day gone by (ATT-13), has no
    # laptop time, so this count, by the laptop's time, never reads it; and a tap is never deleted, only voided.
    zone = ZoneInfo(shop.timezone)
    today = shop_today(shop)
    with shop_context(shop):
        held = AttendanceEvent.objects.filter(
            shop=shop,
            staff__created_by__isnull=True,
            client_time__lt=datetime.combine(today, time.min, tzinfo=zone),
        ).count()
    return held >= len(_demo_taps(today, zone))


def _holds_its_meals(shop: Shop) -> bool:
    # Whether today's demo holds the meal money this seed types (WAGE-7): as for its taps, a deploy whose seed types it
    # must not keep a demo an older seed made that morning without any. Known by its days: each holds a row, as a row a
    # visitor crosses out is still there (T2), and what a visitor types only adds to them.
    with shop_context(shop):
        held = set(MealMoney.objects.filter(shop=shop).values_list("date", flat=True))
    return set(_days_with_meals(shop_today(shop))) <= held


def _holds_its_advances(shop: Shop) -> bool:
    # Whether today's demo holds the advances this seed types (WAGE-8): as for its meal money. Known by whose and which
    # day: a nickname is one current worker's, and the seed's people stay (demo.people_fixed), so it is theirs. One a
    # visitor crosses out is still there (T2), and what they type only adds to them.
    with shop_context(shop):
        held = set(Advance.objects.filter(shop=shop).values_list("staff__display_name", "date"))
    return {(name, day) for name, day, _amount in _advances_of(shop_today(shop))} <= held


def _holds_its_flags(shop: Shop) -> bool:
    # Whether today's demo holds the flags this seed raises (CTRL-4): as for its taps, a deploy whose seed raises them
    # must not keep a demo an older seed made that morning without them. Known by the refused record's line, sent last,
    # in the same transaction as the rest, of a type nothing else sends; a line is never deleted, whatever a visitor
    # does with its flags. A seed with no days before today sends no record, so it raises none.
    if not _demo_taps(shop_today(shop), ZoneInfo(shop.timezone)):
        return True
    with shop_context(shop):
        return PushedDocument.objects.filter(shop=shop, type=DEMO_UNKNOWN_TYPE).exists()


def _holds_its_closures(shop: Shop) -> bool:
    # Whether today's demo holds every closure this seed adds, as the system added them: as for its rules, a deploy
    # whose seed adds a closure must not keep a demo made that morning without it (ATT-8). Known by its first day and
    # its name, which nothing changes: a visitor may move its last day, or cancel it, and the demo still holds it.
    expected = {(first, name) for first, _last, name in coming_public_holidays(shop_today(shop))}
    with shop_context(shop):
        added = set(Closure.objects.filter(shop=shop, created_by__isnull=True).values_list("first_day", "name"))
    return expected <= added


def _make_the_shop() -> Shop:
    # The new shop's id first, so the shop can be opened before it exists: the services' checks read through the
    # tenancy guard (ADR-0042). One block for the whole shop (_the_shop_and_its_people), which every service there
    # joins, so all its lines (the sides, their drawers, the people) are numbered once, at its end (SYNC-15): a
    # visitor's new laptop starts from them. Then the laptop and its taps, after that block, and all of it before
    # _wipe_and_make's transaction commits.
    shop_id = uuid.uuid7()
    with shop_context(shop_id):
        shop, people, today = _the_shop_and_its_people(shop_id)
        # The taps after the shop's block: its lines numbered first, all at once (SYNC-15), and each tap then numbered
        # as the push numbers any document, at the end of a block of its own, inside a transaction of its own (03 §5.5).
        # Inside the shop's block it would work too, as a block inside an atomic() part is one of its own
        # (apps/core/changes.py); the taps would just take the first numbers. Still in _wipe_and_make's one
        # transaction: a refused tap undoes the whole reset.
        manager = next(people[person.display_name] for person in PEOPLE if person.email == MANAGER_EMAIL)
        laptop = _demo_laptop(manager, Side.objects.get(code=DEMO_LAPTOP_SIDE))
        taps = _demo_taps(today, ZoneInfo(shop.timezone))
        _send_the_taps(laptop, people, taps, today)
        _send_a_refused_record(laptop, people, taps)
        _type_the_meals(shop, manager, today)
        _give_the_advances(people, manager, today)
    return shop


def _the_shop_and_its_people(shop_id: uuid.UUID) -> tuple[Shop, dict[str, StaffMember], date]:
    # The shop, its sides, rules and closures, and its people, by their nicknames, and the shop's day they were made
    # from. The caller opens the shop.
    with recording_changes(shop_id):
        # The shop, its sides with their stock places and cash drawers, and its own copy of the six roles
        # (set_up_shop), as a demo shop: the refusal above knows it as the seed's own at the next run.
        shop = set_up_shop(name=SHOP_NAME, code=SHOP_CODE, sides=SIDES, kind=ShopKind.DEMO, shop_id=shop_id)
        # Both sides switched on, as an owner switches a real shop's on once he starts using it (ADR-0033): a new side
        # starts off (SHOP-2), and the demo shows a shop at work. As the system, which the demo's lock on the switch
        # lets through (demo.sides_fixed). Each side already has its line in this block, so the switch adds none.
        sides = {
            side.code: switch_side(side, version=side.version, is_live=True, by=None) for side in Side.objects.all()
        }
        # The demo's rules, from the 1st of last month, as the system, saying it is the demo's seed, which alone may
        # start a rule on a day gone by, and only on the demo (as_the_demo_seed, DATA-8): the book counts a day only
        # once attendance is on (ATT-10), and fines a late one by that day's rules. A visitor's new value starts
        # tomorrow at the earliest (demo.rules_from_tomorrow). Each row gets its line in this block, as a laptop needs
        # every rule's rows (SYNC-2).
        # The shop's day, asked once, here, as the shop's zone is known from now on: every part of the demo is made
        # from this one answer. A reset that runs across midnight in Arusha and asked again later would make the
        # taps from another day than the rules and the people, and the first day's taps would be flagged, days to
        # decide nobody made (DATA-8's review).
        today = shop_today(shop)
        first_day = _history_starts(today)
        for rule, value in DEMO_RULES:
            set_setting(shop, key=rule.key, value=value, effective_from=first_day, by=None, as_the_demo_seed=True)
        # The coming public holidays, closed, as the system, from the shop's own today (ATT-8): Mipangilio ya duka then
        # lists them (ATT-9), and a visitor can try Ondoa and a new last day on them, from tomorrow on
        # (demo.closures_from_tomorrow). The laptops never get closures, so they add no line to this block.
        for first, last, name in coming_public_holidays(today):
            add_closure(shop, first_day=first, last_day=last, name=name, by=None)
        people = {}
        for person in PEOPLE:
            # A person's account has no shop (rule 1); their job at the shop does. create_user with no password
            # stores one that nothing can match, so a seller can log in only with her PIN.
            user = User.objects.create_user(full_name=person.full_name, email=person.email, password=person.password)
            # by=None everywhere: the system sets the demo up, not one of its people, so no giver is named (02 §1).
            # Working from the 1st of last month, as the rules start (DATA-2): the book counts no day before a job's
            # first (02 §5), and a tap before it would go to review (ATT-11).
            staff = add_staff(shop=shop, user=user, display_name=person.display_name, started_on=first_day, by=None)
            role = Role.objects.get(template=person.role)
            side = None if person.side is None else sides[person.side]
            assign_role(staff, role, side=side, by=None)
            for key in person.keys:
                grant_permission(staff, key, side=None, by=None)
            if person.pin is not None:
                set_pin(staff, person.pin, by=None)
            # Their pay from their first day, as the system: a visitor sees it on the worker's page (WAGE-1), and the
            # month page lists them by it (ATT-5). No laptop gets a rate, so it adds no line to this block.
            if person.daily_rate is not None:
                set_pay_rate(staff, daily_rate=Decimal(person.daily_rate), effective_from=staff.started_on, by=None)
            people[person.display_name] = staff
    return shop, people, today


# Django's error reports list each function's local variables when something fails: `pairing` holds the laptop's key,
# which shows as stars there, as in start_pairing (AUTH-2).
@sensitive_variables("pairing")
def _demo_laptop(manager: StaffMember, side: Side) -> Device:
    # The demo's laptop (DATA-8), paired as any laptop is (03 §5.9): it asks to join, and the manager confirms its code,
    # as the one-tap demo pairs a visitor's browser (register_demo_device). So the devices page shows it, confirmed by
    # Meneja, as any laptop. Its key is dropped here: no browser holds it, so nothing but this seed ever sends as it.
    pairing = start_pairing()
    return confirm_pairing(pairing.request.code, name=DEMO_LAPTOP_NAME, home_side=side, by=manager)


def _history_starts(today: date) -> date:
    # The demo's first day (DATA-2): the 1st of the month before `today`'s. A month's pay is approved once the month
    # is over (WAGE-3), so the demo always holds one whole month gone by, and the one before it has nobody, so nothing
    # waits on it (pay_run.earlier_month_open): on 28 November, 1 October; on 1 December, 1 November; on 1 January,
    # 1 December of the year before. 28 to 61 days, where DATA-8's 21 held a month whole only early in one. The day
    # before the 1st of this month is the last of the one before, whose 1st it is.
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def _working_days_back(today: date) -> list[date]:
    # The working days from the demo's first day to the day before today, the latest first: Sunday is off at every
    # shop, and paid outside the system (01 §8.1), so it has no taps. An OddDay's `back` counts in this list, from 1.
    days = (today - timedelta(days=n) for n in range(1, (today - _history_starts(today)).days + 1))
    return [day for day in days if day.weekday() != SUNDAY]


def _last_months_days(today: date) -> list[date]:
    # The working days of the month before `today`'s, its first first: a LastMonthDay's `place` counts in this list,
    # from 1 (DATA-2). Only when the demo holds that month whole, as it always does (_history_starts); none on a test's
    # shorter span (apps/demo/tests/conftest.py), where they would land among the newest days.
    last = today.replace(day=1) - timedelta(days=1)
    first = last.replace(day=1)
    if _history_starts(today) > first:
        return []
    days = (first + timedelta(days=n) for n in range(last.day))
    return [day for day in days if day.weekday() != SUNDAY]


@dataclass(frozen=True)
class _DemoTap:
    # One tap of the days before today: whose, Ingia or Toka, and when, by the laptop's clock in the shop's zone.
    person: DemoPerson
    kind: ClockKind
    at: datetime


def _demo_taps(today: date, zone: ZoneInfo) -> list[_DemoTap]:
    # Each person's taps on each working day before `today`, the earliest first, as the laptop made them: an ordinary
    # day's minutes drawn from the fixed seed, an odd day's as PEOPLE gives them. From the date and the zone alone, so
    # the seed's check counts them (_holds_its_taps) without reading the shop's rows.
    draws = random.Random(TAPS_SEED)
    last_month = _last_months_days(today)
    taps: list[_DemoTap] = []
    # The oldest day first, and the people in PEOPLE's order, so the draws come in the same order at every reset.
    for back, day in reversed(list(enumerate(_working_days_back(today), start=1))):
        for person in PEOPLE:
            # Drawn on every day, odd or not, so an odd day moved changes no other day's minutes.
            came: datetime | None = datetime.combine(day, ON_TIME_FROM, tzinfo=zone) + timedelta(
                minutes=draws.randint(0, ON_TAPS)
            )
            left: datetime | None = datetime.combine(day, CLOSING_FROM, tzinfo=zone) + timedelta(
                minutes=draws.randint(0, OFF_TAPS)
            )
            odd = _odd_day(person, back, day, last_month)
            if odd is not None:
                came = None if odd.came is None else datetime.combine(day, odd.came, tzinfo=zone)
                left = None if odd.left is None else datetime.combine(day, odd.left, tzinfo=zone)
            taps.extend(_DemoTap(person, kind, at) for kind, at in ((ClockKind.IN, came), (ClockKind.OUT, left)) if at)
    # The laptop numbers its records in the order they were made, so a later one never has an earlier time: that would
    # say its clock moved (ATT-1's sign 1). sorted() keeps two taps of one minute in the order above.
    return sorted(taps, key=lambda tap: tap.at)


def _odd_day(person: DemoPerson, back: int, day: date, last_month: list[date]) -> OddDay | LastMonthDay | None:
    # The person's odd day on `day`, the `back`-th working day before today, if it is one: one of the newest, counted
    # back (OddDay, DATA-8), or one of last month's own, counted forward among its working days, `last_month`
    # (LastMonthDay, DATA-2). Never both on one day (test_seed_demo_odd_days_never_meet).
    newest = next((odd for odd in person.odd_days if odd.back == back), None)
    if newest is not None:
        return newest
    return next(
        (odd for odd in person.last_month_days if odd.place <= len(last_month) and last_month[odd.place - 1] == day),
        None,
    )


def _send_the_taps(laptop: Device, people: dict[str, StaffMember], taps: list[_DemoTap], today: date) -> None:
    # The taps, sent by the demo's laptop through the push (SYNC-4), as the laptop sends its outbox: each a clock
    # document, version 2, made by the person's job in this shop (`people`, by nickname), numbered from 1, in pushes of
    # at most MOST_DOCUMENTS, as the route takes (03 §6.3). Sent now, long after they were made, by a laptop whose
    # clock is right (sent_at, the server's now): so the server keeps each at the laptop's time (device_ok, ATT-1). No
    # photo: the demo keeps none (Jack, ATT-3: A). `today`: the shop's day the taps were made from.
    zone = ZoneInfo(laptop.shop.timezone)
    last_heard = datetime.combine(_history_starts(today), LAST_HEARD, tzinfo=zone)
    documents = [
        Sent(
            id=uuid.uuid7(),
            type="clock",
            schema_version=2,
            device_seq=number,
            client_time=tap.at,
            created_by=people[tap.person.display_name].pk,
            payload={"kind": tap.kind, "last_server_time": last_heard.isoformat(), "no_photo": NoPhoto.DEMO},
        )
        for number, tap in enumerate(taps, start=1)
    ]
    # One tap waits on the laptop until the others are in, so its number is missing, then late (CTRL-4): the flag the
    # server raises for it closes itself as it comes (SYNC-5). The middle one, whose neighbours are sure to be taps too;
    # its time is later than the one before it, as each record's is, so no sign says the laptop's clock moved.
    late = documents[len(documents) // 2 : len(documents) // 2 + 1]
    in_order = [document for document in documents if document not in late]
    batches = [in_order[start : start + MOST_DOCUMENTS] for start in range(0, len(in_order), MOST_DOCUMENTS)]
    unsent = len(documents)
    for batch in [*batches, *([late] if late else [])]:
        unsent -= len(batch)
        answers = _push_from_the_demo_laptop(laptop, batch, unsent_count=unsent)
        # The push never raises for a tap it refuses: it answers invalid, and goes on (03 §6.3). Nor for one it flags:
        # that one is accepted (accept, then flag). The seed's taps are its own, timed by a right clock, so either is a
        # bug in this seed, and a flag would hand a visitor a day to decide nobody made. So it stops the reset, and its
        # transaction takes the wipe back too: yesterday's demo stays, and the deploy's smoke test shows red.
        wrong = [
            (answer.status, answer.code, answer.fields, answer.flags)
            for answer in answers
            if answer.status != PushedStatus.ACCEPTED or answer.flags
        ]
        if wrong:
            raise RuntimeError(f"The push refused or flagged the demo laptop's taps: {wrong}")


def _days_with_meals(today: date) -> list[date]:
    # The working days before `today` whose meal money the seed types: all but the forgotten one. From the date alone,
    # so the seed's check counts them (_holds_its_meals) without reading the shop's rows.
    return [day for back, day in enumerate(_working_days_back(today), start=1) if back != FORGOTTEN_MEALS_BACK]


def _type_the_meals(shop: Shop, manager: StaffMember, today: date) -> None:
    # The meal money of the days before today (WAGE-7), typed by Meneja through the service, as a person types it, the
    # oldest first; with no note, as none is kept on the demo. The book splits it among who came when a page asks.
    # `today`: the shop's day the taps were made from.
    for day in reversed(_days_with_meals(today)):
        record_meal_money(shop, money_id=uuid.uuid7(), date=day, amount=MEALS_A_DAY, by=manager)


def _advances_of(today: date) -> list[tuple[str, date, Decimal]]:
    # Whom the seed gives money before payday, on which day and how much, oldest first: the newest, counted back
    # (ADVANCES), and last month's own, counted forward (LAST_MONTH_ADVANCES, DATA-2). From the date alone, as for the
    # meals. None on a seed with fewer working days than one counts, as a test's shorter span has.
    days = _working_days_back(today)
    given = [(name, days[back - 1], amount) for name, back, amount in ADVANCES if back <= len(days)]
    last_month = _last_months_days(today)
    given += [
        (name, last_month[place - 1], amount) for name, place, amount in LAST_MONTH_ADVANCES if place <= len(last_month)
    ]
    return sorted(given, key=lambda advance: advance[1])


def _give_the_advances(people: dict[str, StaffMember], manager: StaffMember, today: date) -> None:
    # The money given before payday (WAGE-8), typed by Meneja through the service, as a person types it; with no note,
    # as none is kept on the demo. The pay takes it off when a page asks. `today`: the shop's day the taps were made
    # from.
    for name, day, amount in _advances_of(today):
        record_advance(people[name], advance_id=uuid.uuid7(), date=day, amount=amount, by=manager)


def _send_a_refused_record(laptop: Device, people: dict[str, StaffMember], taps: list[_DemoTap]) -> None:
    # The two flags that wait on the demo's Tofauti (CTRL-4): after the last tap, five minutes later, the laptop sends a
    # record of Asha's of a type the server doesn't know, as a laptop whose app is newer than the server's would, so it
    # is set aside (invalid_document); and one number too far, so the number between them is missing (device_gap).
    if not taps:
        return
    seller = next(person for person in PEOPLE if person.side == DEMO_LAPTOP_SIDE)
    (answer,) = _push_from_the_demo_laptop(
        laptop,
        [
            Sent(
                id=uuid.uuid7(),
                type=DEMO_UNKNOWN_TYPE,
                schema_version=1,
                device_seq=len(taps) + 2,
                client_time=taps[-1].at + timedelta(minutes=5),
                created_by=people[seller.display_name].pk,
                payload={},
            )
        ],
        unsent_count=0,
    )
    # A type a later card's documents take would be saved, or refused for its shape: not what the page is to show.
    if (answer.status, answer.code) != (PushedStatus.INVALID, "document.type_unknown"):
        raise RuntimeError(f"The push knows the demo laptop's unknown record: {answer.status} {answer.code}")


def _push_from_the_demo_laptop(laptop: Device, documents: list[Sent], *, unsent_count: int) -> list[Answer]:
    # One push of the demo's laptop, by a right clock: what it sends now, sent and received at the server's now.
    now = timezone.now()
    return push(
        laptop,
        documents,
        received_at=now,
        sent_at=now,
        unsent_count=unsent_count,
        app_version=settings.APP_VERSION,
        outages=[],
    )


@dataclass(frozen=True)
class DemoPin:
    # One seller's PIN, as the PIN screen shows it under their tile (OPS-3): their staff row in the demo shop, so the
    # laptop finds the tile by id, never by a name, and the PIN from PEOPLE, the list the seed sets it from.
    staff_id: uuid.UUID
    pin: str


@dataclass(frozen=True)
class DemoLogin:
    # One person's password login, for the PIN screen's tile of someone with no PIN (OPS-13): today Meneja, whose tile
    # opens the password login with both boxes filled. `login` is what goes in its first box: the email, the one login
    # name the seed gives (_demo_logins).
    # The password is the seed's public one, from PEOPLE, never read from the database, which keeps only its hash:
    # "passwords never leave the server" holds for every real one, and this one is printed in the README.
    staff_id: uuid.UUID
    login: str
    password: str


@dataclass(frozen=True)
class DemoDevice:
    # What one tap on Jaribu demo gives the visitor's browser (register_demo_device): its device, the PINs and the
    # logins to show, and its key, which goes in its cookie only, never in an answer's body (AUTH-2).
    device: Device
    pins: tuple[DemoPin, ...]
    logins: tuple[DemoLogin, ...]
    # repr=False, as NewPairing's (apps/people/services.py): a test's failure message, a log line or an error page that
    # printed this would otherwise show the key itself.
    key: str = field(repr=False)


def demo_shop_if_open() -> Shop | None:
    """The demo shop, when the one-tap demo may make a device of it here (OPS-3, BP15): the sign is set, no shop but a
    demo one exists, and the seed has made the demo shop. None otherwise: on the real server, which never has the sign,
    and on any database with a shop that isn't a demo, even beside the demo shop (ADR-0029)."""
    # The two facts the seed's own refusals read (_check_may_seed): together they say the database holds demo data
    # alone, so a stranger's browser may join its shop with no manager's yes. The sign is read first, so the real
    # server answers without a single query.
    if not settings.DEMO_SEED:
        return None
    # Shop has no tenancy guard (it is the shop itself, rule 1), so this looks across every shop, as it must.
    if Shop.objects.exclude(kind=ShopKind.DEMO).exists():
        return None
    return Shop.objects.filter(kind=ShopKind.DEMO, code=SHOP_CODE).first()


# Django's error reports list each function's local variables when something fails: `replacing`, the browser's old key,
# and `pairing`, which holds the new one, show as stars there, as in start_pairing.
@sensitive_variables("replacing", "pairing")
def register_demo_device(*, replacing: str | None = None) -> DemoDevice:
    """One tap on Jaribu demo (OPS-3, BP15): the visitor's browser becomes a device of the demo shop, with no code to
    read out and no manager to say yes, and gets the demo sellers' PINs and the manager's login to show (OPS-13).
    `replacing`: the key the browser's cookie holds now, if any, as for start_pairing. Refusals: the demo isn't open
    here (demo.closed, demo_shop_if_open); a key that already opens a device (pairing.already_paired), which a new
    cookie would lose for good. A key from yesterday's demo, whose device the seed's daily wipe took, opens nothing, so
    that browser gets a new device."""
    shop = demo_shop_if_open()
    if shop is None:
        # English for the logs; the app translates the code (ADR-0040).
        raise ValidationError("The one-tap demo opens only where the demo shop is the only shop.", code="demo.closed")
    # One transaction: if the confirm is refused, the waiting request goes too, so no code waits for a manager who will
    # never type it.
    with transaction.atomic():
        # The two steps every new device takes (03 §5.9), not a device written by hand: the demo can't hold a device a
        # real shop couldn't, and a rule pairing gains reaches the demo too, as the seed's people come from the
        # services. The first makes the key, and refuses a browser whose key already works.
        pairing = start_pairing(replacing=replacing)
        code = pairing.request.code
        with shop_context(shop.pk):
            # The second, by the demo's manager, standing in for the yes a real laptop gets on the manager's phone:
            # Meneja holds device.manage on every side (PEOPLE). Found by the login visitors read, which no route
            # changes. So the device list shows Meneja as who confirmed it, as for any laptop. A visitor who took
            # Meneja's role away would stop every tap until the next reset: so the seed's people stay as made on the
            # demo, as their logins are (demo.people_fixed, PPL-4; their roles, PPL-7).
            manager = StaffMember.objects.get(user__email=MANAGER_EMAIL)
            home_side = Side.objects.get(code=DEMO_DEVICE_SIDE)
            # Named by its pairing code, "Demo K7P2-MXQ9", as the register screen shows a code: no two requests ever
            # share one (people_pairingrequest_code_once), so two visitors' devices never clash on a name
            # (device.name_taken), and a manager can still rename one.
            device = confirm_pairing(code, name=f"Demo {code[:4]}-{code[4:]}", home_side=home_side, by=manager)
            # Made and committed before the answer leaves: if the answer is lost on its way, the device stays, with
            # a key no browser holds, and the browser taps again for a new one. Harmless: nothing can use it, and
            # the next daily reset takes it with the rest.
            pins = _demo_pins()
            logins = _demo_logins()
    return DemoDevice(device=device, pins=pins, logins=logins, key=pairing.key)


def _demo_pins() -> tuple[DemoPin, ...]:
    # Each person of PEOPLE who has a PIN, as the seed's own row (_seeds_own).
    pins = []
    for person in PEOPLE:
        if person.pin is None:
            continue
        staff = _seeds_own(person)
        if staff is not None:
            pins.append(DemoPin(staff_id=staff.pk, pin=person.pin))
    return tuple(pins)


def _demo_logins() -> tuple[DemoLogin, ...]:
    # Each person of PEOPLE who logs in only with a password (OPS-13): no PIN, so no tile until now (PPL-4's rule), and
    # a login name for the box. Someone with a PIN gets none: their tile opens the PIN pad, never the password login.
    logins = []
    for person in PEOPLE:
        if person.pin is not None or person.password is None or person.email is None:
            continue
        staff = _seeds_own(person)
        if staff is not None:
            logins.append(DemoLogin(staff_id=staff.pk, login=person.email, password=person.password))
    return tuple(logins)


def _seeds_own(person: DemoPerson) -> StaffMember | None:
    # The seed's row of this person, found in the demo shop (the caller opens it) by the nickname the seed gave them.
    # Every visitor shares Meneja's public password, and a manager may add and let staff go (PPL-4), and rename them
    # (PPL-10). The seed's people stay as made on the demo (demo.people_fixed), but a guard missed must not stop every
    # tap: a visitor could mark Asha as left and add a new "Asha" (a nickname is unique among current staff only), or
    # rename her. So the seed's own row is taken, the first made: a UUIDv7 id starts with the time it was made. And
    # someone no longer found is None, left out by the caller: a tile with no PIN or no login, never a tap refused for
    # every visitor until the next reset.
    return StaffMember.objects.filter(display_name=person.display_name).order_by("pk").first()
