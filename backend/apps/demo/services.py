"""apps/demo/services.py — the demo seed: wipes a demo-only database, then makes the demo shop again (DATA-1); and
the one-tap demo, which makes a visitor's browser a device of that shop (OPS-3).

It owns the demo shop as visitors meet it (Jack, 8 Nov 2026): Duka la Mfano, a demo shop with the sides Dawa and
Vyakula; Meneja, its manager on both sides, who logs in with a password; Asha, a seller on Dawa, and Baraka, a seller
on Vyakula, who log in with a PIN. `manage.py seed_demo` (management/commands/seed_demo.py) runs it, on every start
of the demo (backend/start-demo.sh) and of the browser tests' container, which starts the same way (compose.e2e.yml):
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
when it was made on an earlier day. `fresh=True` makes it again whatever its day.

Made through the services, as a real shop is set up (set_up_shop, add_staff, assign_role, set_pin), never by writing
rows: the demo can't hold anything a real shop couldn't, and a service that changes its rules changes the demo too.

It also owns the one-tap demo (OPS-3, BP15): a recruiter has no manager to confirm a pairing code, so *Jaribu demo*
makes the visitor's browser a device of the demo shop at once (register_demo_device), and hands it the sellers' PINs
from PEOPLE below, the one list the seed sets them from, for the PIN screen to show under their tiles. It is open only
where the seed itself may run, and the seed has made the demo shop (demo_shop_if_open): the same sign and the same
"no shop but a demo one" that keep the wipe shut keep this shut on the real server.

Fake data only (rule 10): the names are made up, and the password and the PINs are public on purpose, because
visitors need them. Nobody here is staff in Django's sense (`is_staff`), so no seeded login opens the admin, whose
login page has no rate limit yet (04 DATA-1, v1.8).
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import OperationalError, connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.core.changes import recording_changes
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, Role, StaffMember, User
from apps.people.selectors import shop_today
from apps.people.services import (
    add_staff,
    assign_role,
    confirm_pairing,
    set_pin,
    set_up_shop,
    start_pairing,
)
from apps.shops.models import Shop, ShopKind, Side
from apps.shops.services import NewSide

SHOP_NAME = "Duka la Mfano"
SHOP_CODE = "DEMO"
# The two sides MPC has, in the words the app already uses for them (Jack, 8 Nov 2026).
SIDES = (NewSide("D", "Dawa"), NewSide("F", "Vyakula"))

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
    # a person who logs in only with their password.
    full_name: str
    display_name: str
    role: RoleTemplate
    side: str | None
    pin: str | None = None
    email: str | None = None
    password: str | None = None


PEOPLE = (
    # The manager on every side: device.manage among the role's keys lets them confirm a new laptop on either side
    # (confirm_pairing). A password and no PIN: the manager works from their own phone, as at a real shop.
    DemoPerson(
        "Meneja Mfano",
        "Meneja",
        RoleTemplate.MANAGER,
        side=None,
        email=MANAGER_EMAIL,
        password=MANAGER_PASSWORD,
    ),
    # A seller on each side, with a PIN only: they log in at the shop's laptop, as a seller does.
    DemoPerson("Asha Mfano", "Asha", RoleTemplate.SELLER, side="D", pin="2580"),
    DemoPerson("Baraka Mfano", "Baraka", RoleTemplate.SELLER, side="F", pin="1470"),
)

# The side a one-tap demo device serves (OPS-3): Dawa, where Asha sells. Any seller can still log in on it.
DEMO_DEVICE_SIDE = "D"


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
    if not fresh and _made_today():
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


def _made_today() -> bool:
    # True when the demo shop exists and was made today, in the shop's own time zone: the night in Arusha, not in UTC,
    # decides when a new day starts (02 §1).
    shop = Shop.objects.filter(kind=ShopKind.DEMO, code=SHOP_CODE).first()
    if shop is None:
        return False
    made_on = timezone.localtime(shop.created_at, ZoneInfo(shop.timezone)).date()
    return made_on == shop_today(shop)


def _make_the_shop() -> Shop:
    # The new shop's id first, so the shop can be opened before it exists: the services' checks read through the
    # tenancy guard (ADR-0042). One block for the whole shop, which every service below joins, so all its lines (the
    # sides, their drawers, the people) are numbered once, at the very end (SYNC-15): a visitor's new laptop starts
    # from them. The block ends just before _wipe_and_make's transaction commits.
    shop_id = uuid.uuid7()
    with shop_context(shop_id), recording_changes(shop_id):
        # The shop, its sides with their stock places and cash drawers, and its own copy of the six roles
        # (set_up_shop), as a demo shop: the refusal above knows it as the seed's own at the next run.
        shop = set_up_shop(name=SHOP_NAME, code=SHOP_CODE, sides=SIDES, kind=ShopKind.DEMO, shop_id=shop_id)
        sides = {side.code: side for side in Side.objects.all()}
        for person in PEOPLE:
            # A person's account has no shop (rule 1); their job at the shop does. create_user with no password
            # stores one that nothing can match, so a seller can log in only with her PIN.
            user = User.objects.create_user(full_name=person.full_name, email=person.email, password=person.password)
            # by=None everywhere: the system sets the demo up, not one of its people, so no giver is named (02 §1).
            staff = add_staff(shop=shop, user=user, display_name=person.display_name, by=None)
            role = Role.objects.get(template=person.role)
            side = None if person.side is None else sides[person.side]
            assign_role(staff, role, side=side, by=None)
            if person.pin is not None:
                set_pin(staff, person.pin, by=None)
    return shop


@dataclass(frozen=True)
class DemoPin:
    # One seller's PIN, as the PIN screen shows it under their tile (OPS-3): their staff row in the demo shop, so the
    # laptop finds the tile by id, never by a name, and the PIN from PEOPLE, the list the seed sets it from.
    staff_id: uuid.UUID
    pin: str


@dataclass(frozen=True)
class DemoDevice:
    # What one tap on Jaribu demo gives the visitor's browser (register_demo_device): its device, the PINs to show, and
    # its key, which goes in its cookie only, never in an answer's body (AUTH-2).
    device: Device
    pins: tuple[DemoPin, ...]
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
    read out and no manager to say yes, and gets the demo sellers' PINs to show. `replacing`: the key the browser's
    cookie holds now, if any, as for start_pairing. Refusals: the demo isn't open here (demo.closed, demo_shop_if_open);
    a key that already opens a device (pairing.already_paired), which a new cookie would lose for good. A key from
    yesterday's demo, whose device the seed's daily wipe took, opens nothing, so that browser gets a new device."""
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
            # Meneja's role away would stop every tap until the next reset: a note on PPL-4's card asks it to keep the
            # seed's people as made on the demo, as their logins are (demo.logins_fixed).
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
    return DemoDevice(device=device, pins=pins, key=pairing.key)


def _demo_pins() -> tuple[DemoPin, ...]:
    # Each person of PEOPLE who has a PIN, found in the demo shop (the caller opens it) by the nickname the seed gave
    # them. Every visitor shares Meneja's public password, so once a manager can add, rename and let staff go (PPL-4),
    # a visitor may mark Asha as left and add a new "Asha" (a nickname is unique among current staff only), or rename
    # her. So the seed's own row is taken, the first made: a UUIDv7 id starts with the time it was made. And someone
    # no longer found is left out: a tile with no PIN, never a tap refused for every visitor until the next reset.
    pins = []
    for person in PEOPLE:
        if person.pin is None:
            continue
        staff = StaffMember.objects.filter(display_name=person.display_name).order_by("pk").first()
        if staff is not None:
            pins.append(DemoPin(staff_id=staff.pk, pin=person.pin))
    return tuple(pins)
