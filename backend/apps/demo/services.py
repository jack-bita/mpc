"""apps/demo/services.py — the demo seed: wipes a demo-only database, then makes the demo shop again (DATA-1).

It owns the demo shop as visitors meet it (Jack, 8 Nov 2026): Duka la Mfano, a demo shop with the sides Dawa and
Vyakula; Meneja, its manager on both sides, who logs in with a password; Asha, a seller on Dawa, and Baraka, a seller
on Vyakula, who log in with a PIN. `manage.py seed_demo` (management/commands/seed_demo.py) runs it.

Why it wipes the whole database instead of taking out the demo shop's rows: the ledgers refuse every DELETE
(ADR-0021, apps/core/operations.py), and every link PROTECTs what it points at (rule 7), so a shop's rows can't be
taken out one by one. Django's `flush` empties every table at once (TRUNCATE), which the ledgers' triggers don't
watch. That is safe only on a database that holds nothing but demo data, so the seed refuses, before it writes
anything, in two cases:
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

Fake data only (rule 10): the names are made up, and the password and the PINs are public on purpose, because
visitors need them. Nobody here is staff in Django's sense (`is_staff`), so no seeded login opens the admin, whose
login page has no rate limit yet (04 DATA-1, v1.8).
"""

from dataclasses import dataclass
from enum import StrEnum
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Role, User
from apps.people.selectors import shop_today
from apps.people.services import add_staff, assign_role, set_pin, set_up_shop
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


class Seeded(StrEnum):
    # What a run did, for the command's output line.
    MADE = "made"
    KEPT = "kept"


def seed_demo(*, fresh: bool = False) -> Seeded:
    """Make the demo shop again on a database that holds only demo data, or keep today's (see above). `fresh`: make it
    again even if it was made today. Refuses with a ValidationError, before anything is written, without the sign or
    with a shop that isn't a demo."""
    _check_may_seed()
    if not fresh and _made_today():
        return Seeded.KEPT
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
    return Seeded.MADE


def _check_may_seed() -> None:
    # The two refusals, both before anything is written. Codes, as every refusal has (ADR-0032): the command prints
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
    # The shop, its sides with their stock places and cash drawers, and its own copy of the six roles (set_up_shop),
    # as a demo shop: the refusal above knows it as the seed's own at the next run.
    shop = set_up_shop(name=SHOP_NAME, code=SHOP_CODE, sides=SIDES, kind=ShopKind.DEMO)
    # The services' checks read through the tenancy guard (ADR-0037), so the shop is opened for the people's jobs.
    with shop_context(shop):
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
