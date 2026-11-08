"""apps/demo/tests/test_seed_demo.py — the demo seed: the same shop every time, and never on data that isn't the demo's
(DATA-1, ADR-0029).

The seed wipes the whole database before it makes the demo shop (apps/demo/services.py says why), so most of these
tests prove what it refuses, and that a refusal writes nothing:

    no DEMO_SEED=yes          → refused (demo.no_sign): the real server never has the sign
    a shop that isn't a demo  → refused (demo.other_shop): a live shop's data is real, beside the demo's too
    today's demo shop         → kept: a visitor back from a break finds their work
    an earlier day's          → made again, the day being Arusha's, not UTC's

The logins are written here as the visitors read them (README, docs/runbooks/demo.md, 04's notes, the browser test),
never imported from the seed: a changed PIN must turn a test red, not pass quietly while the README says another.

`fresh_content_types` clears Django's memory of content types after each test: the seed's flush makes them again
with new ids, and the test's rollback takes those back, so the next test must not find them in memory.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client
from django.utils import timezone
from pytest_django import Settings

from apps.core.tenancy import shop_context
from apps.demo.services import SHOP_CODE, Seeded, seed_demo
from apps.people.models import RoleAssignment, StaffMember, User
from apps.people.pins import pin_matches
from apps.shops.models import Shop, ShopKind, Side
from apps.shops.services import NewSide, create_shop

pytestmark = pytest.mark.django_db

# The demo's public logins, as visitors read them. Change them here only together with every place that prints them.
MANAGER_EMAIL = "meneja@example.com"
MANAGER_PASSWORD = "jaribu-demo"
PINS = {"Asha": "2580", "Baraka": "1470"}


@pytest.fixture(autouse=True)
def demo_sign(settings: Settings) -> None:
    # Every test here runs where the sign is set, as on the demo; the one that proves the refusal takes it away.
    settings.DEMO_SEED = True


@pytest.fixture(autouse=True)
def fresh_content_types() -> Iterator[None]:
    yield
    ContentType.objects.clear_cache()


def the_demo_shop() -> Shop:
    return Shop.objects.get(kind=ShopKind.DEMO, code=SHOP_CODE)


def what_the_shop_holds() -> dict[str, Any]:
    # Everything a visitor meets, with nothing that changes from one build to the next: no ids, no times, no hashes.
    # Whether each PIN and the password work is checked against the public logins instead, as a visitor would.
    shop = the_demo_shop()
    with shop_context(shop):
        side_list = sorted(Side.objects.values_list("code", "name"))
        sides = {side.pk: side.code for side in Side.objects.all()}
        staff = list(StaffMember.objects.order_by("display_name"))
        users = {user.pk: user for user in User.objects.filter(pk__in=[member.user_id for member in staff])}
        people = []
        for member in staff:
            user = users[member.user_id]
            roles = sorted(
                (assignment.role.template, "every side" if assignment.side_id is None else sides[assignment.side_id])
                for assignment in RoleAssignment.objects.filter(staff=member).select_related("role")
            )
            pin = PINS.get(member.display_name)
            people.append(
                {
                    "name": (user.full_name, member.display_name),
                    "email": user.email,
                    "staff": user.is_staff,
                    "roles": roles,
                    "pin works": pin is not None and pin_matches(pin, member.pin_hash, staff_id=member.pk),
                    "password works": user.check_password(MANAGER_PASSWORD),
                }
            )
    return {"shop": (shop.name, shop.code, shop.kind), "sides": side_list, "people": people}


def row_counts() -> dict[str, int]:
    # How many rows each of Django's tables holds, read straight from PostgreSQL, past every manager and guard. The
    # names come from Django's own list of its tables, never from outside, and are quoted as PostgreSQL wants them.
    counts = {}
    with connection.cursor() as cursor:
        for table in connection.introspection.django_table_names(only_existing=True):
            cursor.execute(f"SELECT count(*) FROM {connection.ops.quote_name(table)}")
            counts[table] = cursor.fetchone()[0]
    return counts


def test_seed_demo_refuses_live_shop() -> None:
    # The real server's data, or a laptop's shop made by hand: the seed would wipe it with its flush. Refused before
    # anything is written: every table holds what it held, and no demo shop or person was made.
    live = create_shop(name="Duka Halisi", code="HALISI", sides=[NewSide("D", "Dawa")])
    before = row_counts()

    with pytest.raises(ValidationError) as refused:
        seed_demo(fresh=True)

    assert refused.value.code == "demo.other_shop"
    assert row_counts() == before
    assert list(Shop.objects.all()) == [live]


def test_seed_demo_refuses_a_live_shop_beside_the_demo_shop() -> None:
    # The likelier accident: the demo's own database, with a live shop beside the demo shop. A demo shop being there
    # must not let the seed wipe the other one.
    seed_demo(fresh=True)
    create_shop(name="Duka Halisi", code="HALISI", sides=[NewSide("D", "Dawa")])
    before = row_counts()

    with pytest.raises(ValidationError) as refused:
        seed_demo(fresh=True)

    assert refused.value.code == "demo.other_shop"
    assert row_counts() == before


def test_seed_demo_refuses_a_practice_shop() -> None:
    # A practice shop copies a live one (ADR-0014): not demo data either. Saved straight to the table, as only Django's
    # own form check stops it naming the demo shop, so this is the one database where a practice shop sits beside the
    # demo shop alone: still refused, as the seed asks for demo shops only, not for "no live shop".
    seed_demo(fresh=True)
    Shop.objects.create(name="Duka la Zoezi", code="ZOEZI", kind=ShopKind.PRACTICE, practice_of=the_demo_shop())
    before = row_counts()

    with pytest.raises(ValidationError) as refused:
        seed_demo(fresh=True)

    assert refused.value.code == "demo.other_shop"
    assert row_counts() == before


def test_seed_demo_refused_without_the_sign(settings: Settings) -> None:
    # The real server never sets DEMO_SEED, so even on its first day, before any shop exists, the seed can't put a
    # shop with a public password there (Jack, 8 Nov 2026).
    settings.DEMO_SEED = False

    with pytest.raises(ValidationError) as refused:
        seed_demo(fresh=True)

    assert refused.value.code == "demo.no_sign"
    assert not Shop.objects.exists()
    assert not User.objects.exists()


def test_seed_demo_refused_without_the_sign_writes_nothing(settings: Settings) -> None:
    # Without the sign, today's demo shop isn't wiped either: every table holds what it held.
    seed_demo(fresh=True)
    before = row_counts()
    settings.DEMO_SEED = False

    with pytest.raises(ValidationError):
        seed_demo(fresh=True)

    assert row_counts() == before


def test_seed_demo_is_repeatable() -> None:
    # The card's first box: the same shop every time. Built twice, both builds hold the same shop, sides, people, roles
    # and logins, and the shop as Jack chose it (8 Nov 2026). Nothing in this version is picked at random.
    seed_demo(fresh=True)
    first = what_the_shop_holds()
    seed_demo(fresh=True)
    second = what_the_shop_holds()

    assert first == second
    assert first == {
        "shop": ("Duka la Mfano", "DEMO", ShopKind.DEMO),
        "sides": [("D", "Dawa"), ("F", "Vyakula")],
        "people": [
            {
                "name": ("Asha Mfano", "Asha"),
                "email": None,
                "staff": False,
                "roles": [("seller", "D")],
                "pin works": True,
                "password works": False,
            },
            {
                "name": ("Baraka Mfano", "Baraka"),
                "email": None,
                "staff": False,
                "roles": [("seller", "F")],
                "pin works": True,
                "password works": False,
            },
            {
                "name": ("Meneja Mfano", "Meneja"),
                "email": "meneja@example.com",
                "staff": False,
                "roles": [("manager", "every side")],
                "pin works": False,
                "password works": True,
            },
        ],
    }
    # Made again, not added to: one demo shop, and only its three people.
    assert Shop.objects.count() == 1
    assert User.objects.count() == 3


def test_seed_demo_opens_no_admin(client: Client) -> None:
    # The admin's login page has no rate limit yet (04 DATA-1, v1.8), and the demo's logins are public. Nobody the seed
    # makes is staff in Django's sense, so even the right password is turned away there: the form comes back (200)
    # instead of going on to the admin.
    seed_demo(fresh=True)

    assert not User.objects.filter(is_staff=True).exists()
    assert not User.objects.filter(is_superuser=True).exists()
    answer = client.post("/admin/login/", {"username": MANAGER_EMAIL, "password": MANAGER_PASSWORD, "next": "/admin/"})
    assert answer.status_code == 200
    # And nobody is logged in: a 200 alone could be any page.
    assert "_auth_user_id" not in client.session


def test_seed_demo_keeps_todays_shop() -> None:
    # The demo wakes from its 15-minute sleep and runs its start again: a demo shop made today stays, with whatever a
    # visitor did in it.
    seed_demo(fresh=True)
    made = the_demo_shop()

    assert seed_demo() == Seeded.KEPT
    assert the_demo_shop() == made


def test_seed_demo_makes_yesterdays_shop_again() -> None:
    # The night's redeploy, or the first wake-up of a new day: a demo shop made yesterday is wiped and made again.
    # The day is the shop's own: a whole day back is yesterday in Arusha at any hour.
    seed_demo(fresh=True)
    yesterdays = the_demo_shop()
    Shop.objects.filter(pk=yesterdays.pk).update(created_at=timezone.now() - timedelta(days=1))

    assert seed_demo() == Seeded.MADE
    assert not Shop.objects.filter(pk=yesterdays.pk).exists()
    assert Shop.objects.count() == 1


def test_seed_demo_makes_the_shop_again_after_midnight_in_arusha(monkeypatch: pytest.MonkeyPatch) -> None:
    # Made at 20:50 UTC, 23:50 in Arusha; started at 21:10 UTC the same UTC day, 00:10 in Arusha the next. A new day
    # in the shop's time: made again. Read in UTC, both are 3 March and the shop would wrongly be kept.
    seed_demo(fresh=True)
    made = the_demo_shop()
    Shop.objects.filter(pk=made.pk).update(created_at=datetime(2026, 3, 3, 20, 50, tzinfo=UTC))
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 3, 3, 21, 10, tzinfo=UTC))

    assert seed_demo() == Seeded.MADE
    assert not Shop.objects.filter(pk=made.pk).exists()


def test_seed_demo_keeps_a_shop_made_after_midnight_in_arusha(monkeypatch: pytest.MonkeyPatch) -> None:
    # Made at 21:10 UTC, 00:10 on 4 March in Arusha; started at 00:30 UTC on 4 March, 03:30 in Arusha. The same day in
    # the shop's time: kept. Read in UTC, 3 March and 4 March differ and the shop would wrongly be made again.
    seed_demo(fresh=True)
    made = the_demo_shop()
    Shop.objects.filter(pk=made.pk).update(created_at=datetime(2026, 3, 3, 21, 10, tzinfo=UTC))
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 3, 4, 0, 30, tzinfo=UTC))

    assert seed_demo() == Seeded.KEPT
    assert the_demo_shop() == made


def test_seed_demo_makes_the_shop_on_an_empty_database() -> None:
    # The browser tests' new database, or the demo's after its 30 days: no demo shop yet, so a plain start makes one.
    assert seed_demo() == Seeded.MADE
    assert the_demo_shop().kind == ShopKind.DEMO


def test_seed_demo_keeps_every_row_the_migrations_made() -> None:
    # The wipe empties every table, and only Django's own rows (content types, permissions) are made again after it.
    # Today no migration writes rows of its own; the day one does (a list of units, CAT-1), its rows would vanish from
    # the demo every night. This turns red that day, so the seed learns to make them again, or the reset changes.
    before = row_counts()

    seed_demo(fresh=True)

    after = row_counts()
    assert {table: after[table] for table, count in before.items() if count and after[table] < count} == {}


def test_seed_demo_command_says_what_it_did_with_no_logins() -> None:
    # One line at the start and one at the end (ops rule), and none holds a name, an email, a PIN or the password: the
    # demo's log is open to whoever runs it (privacy rule).
    out = StringIO()

    call_command("seed_demo", "--fresh", stdout=out)
    call_command("seed_demo", stdout=out)

    lines = out.getvalue().splitlines()
    assert lines == [
        "demo seed: start",
        "demo seed: made the demo shop, with 3 people",
        "demo seed: start",
        "demo seed: kept today's demo shop",
    ]


def test_seed_demo_command_stops_with_the_reason(settings: Settings) -> None:
    # A refusal is the command's error: Django prints the reason and exits with 1, so the demo's start (`set -e`) stops
    # instead of serving a database it shouldn't.
    settings.DEMO_SEED = False

    with pytest.raises(CommandError, match="DEMO_SEED=yes is not set"):
        call_command("seed_demo", stdout=StringIO())
