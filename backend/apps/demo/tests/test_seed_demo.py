"""apps/demo/tests/test_seed_demo.py — the demo seed: the same shop every time, and never on data that isn't the demo's
(DATA-1, ADR-0029).

The seed wipes the whole database before it makes the demo shop (apps/demo/services.py says why), so most of these
tests prove what it refuses, and that a refusal writes nothing:

    no DEMO_SEED=yes          → refused (demo.no_sign): the real server never has the sign
    a shop that isn't a demo  → refused (demo.other_shop): a live shop's data is real, beside the demo's too
    today's demo shop         → kept: a visitor back from a break finds their work
    an earlier day's          → made again, the day being Arusha's, not UTC's

And the 21 days before today (DATA-8): Asha, Baraka and Meneja tapping Ingia and Toka on the demo's laptop, so the month
page (ATT-5) has days to show. Those tests work the days out through the book (ATT-10) and count them. Only the tests
that take `three_weeks` get them; the others make the shop with no day before today, as the taps cost the seed some 3
seconds (conftest.py).

The logins are written here as the visitors read them (README, docs/runbooks/demo.md, 04's notes, the browser test),
never imported from the seed: a changed PIN must turn a test red, not pass quietly while the README says another.

`fresh_content_types` clears Django's memory of content types after each test: the seed's flush makes them again
with new ids, and the test's rollback takes those back, so the next test must not find them in memory.
"""

from collections import Counter
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from typing import Any
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection
from django.test import Client
from django.utils import timezone
from pytest_django import Settings

from apps.control.models import Flag
from apps.core.models import ChangeOp, SequenceName
from apps.core.permissions import Permission
from apps.core.sequences import next_numbers
from apps.core.settings_registry import ATTENDANCE_ON, CLOSING, LATE_FINE, SECOND_FINE
from apps.core.tenancy import shop_context
from apps.demo import services
from apps.demo.services import SHOP_CODE, PublicHoliday, Seeded, coming_public_holidays, seed_demo
from apps.people.models import Device, PermissionGrant, RoleAssignment, StaffMember, User
from apps.people.permissions import effective_permissions
from apps.people.pins import pin_matches
from apps.people.services import add_worker, end_permission, mark_left, suspend
from apps.shops.models import Closure, ClosureStatus, Setting, Shop, ShopKind, Side
from apps.shops.selectors import get_setting, shop_today
from apps.shops.services import NewSide, create_shop
from apps.staffpay.models import AttendanceEvent, DayStatus, NoPhoto, PayRate, ReviewReason, TimeCheck
from apps.staffpay.services import set_pay_rate, work_out_days
from apps.sync.models import PushedDocument, PushedStatus
from apps.sync.push import Answer
from apps.sync.registry import REGISTRY
from tests.change_log import lines_after

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
            # Keys given beyond a role (grant_permission), as the roles are read: code and side.
            keys = sorted(
                (grant.permission, "every side" if grant.side_id is None else sides[grant.side_id])
                for grant in PermissionGrant.objects.filter(staff=member)
            )
            # Their daily rates (WAGE-1): the amount, whether they share the meals, and that each starts on their
            # first day, set by the system.
            rates = [
                (str(rate.daily_rate), rate.shares_meals, rate.effective_from == member.started_on, rate.created_by_id)
                for rate in PayRate.objects.filter(staff=member)
            ]
            pin = PINS.get(member.display_name)
            people.append(
                {
                    "name": (user.full_name, member.display_name),
                    "email": user.email,
                    "staff": user.is_staff,
                    "roles": roles,
                    "keys": keys,
                    "rates": rates,
                    "pin works": pin is not None and pin_matches(pin, member.pin_hash, staff_id=member.pk),
                    "password works": user.check_password(MANAGER_PASSWORD),
                }
            )
        # Every tap (DATA-8): who, in or out, and when by the laptop's clock. Two builds on one day make the same, as
        # the minutes come from a fixed seed.
        taps = sorted(
            (event.staff.display_name, event.kind, event.client_time)
            for event in AttendanceEvent.objects.select_related("staff")
        )
    return {"shop": (shop.name, shop.code, shop.kind), "sides": side_list, "people": people, "taps": taps}


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


def test_seed_demo_is_repeatable(three_weeks: None) -> None:
    # The card's first box: the same shop every time. Built twice, both builds hold the same shop, sides, people, roles
    # and logins, and the shop as Jack chose it (8 Nov 2026). The taps' minutes are picked at random from a fixed seed
    # (TAPS_SEED, DATA-8), so both builds pick the same.
    seed_demo(fresh=True)
    first = what_the_shop_holds()
    seed_demo(fresh=True)
    second = what_the_shop_holds()

    assert first == second
    # The taps, the same in both builds above (DATA-8), and as many as the card's days give: two a working day, of 18,
    # but none on Baraka's absent day and no Toka on Asha's day to decide.
    taps = first.pop("taps")
    assert Counter(name for name, _kind, _at in taps) == {"Asha": 35, "Baraka": 34, "Meneja": 36}
    assert first == {
        "shop": ("Duka la Mfano", "DEMO", ShopKind.DEMO),
        "sides": [("D", "Dawa"), ("F", "Vyakula")],
        "people": [
            {
                "name": ("Asha Mfano", "Asha"),
                "email": None,
                "staff": False,
                "roles": [("seller", "D")],
                "keys": [],
                # A made-up rate from her first day, set by nobody (WAGE-1).
                "rates": [("10000.00", True, True, None)],
                "pin works": True,
                "password works": False,
            },
            {
                "name": ("Baraka Mfano", "Baraka"),
                "email": None,
                "staff": False,
                "roles": [("seller", "F")],
                "keys": [],
                "rates": [("10000.00", True, True, None)],
                "pin works": True,
                "password works": False,
            },
            {
                "name": ("Meneja Mfano", "Meneja"),
                "email": "meneja@example.com",
                "staff": False,
                "roles": [("manager", "every side")],
                # The owner's key to the shop's rules, so a visitor can try Badilisha (SHOP-5); and to its workers, so a
                # visitor can try Wafanyakazi (PPL-4).
                "keys": [("settings.manage", "every side"), ("staff.manage", "every side")],
                "rates": [("15000.00", True, True, None)],
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


def test_seed_demo_makes_todays_shop_again_without_its_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    # A deploy starts the new code on the demo the old code made that morning. A seed that sets one more rule than the
    # one that made it, as ATT-2's did, makes the shop again at once, so the deploy shows the new rule the same day.
    seed_demo(fresh=True)
    made = the_demo_shop()
    monkeypatch.setattr(services, "DEMO_RULES", (*services.DEMO_RULES, (CLOSING, "19:00")))

    assert seed_demo() == Seeded.MADE
    shop = the_demo_shop()
    assert shop != made
    with shop_context(shop):
        assert get_setting(CLOSING, shop, on=shop_today(shop)) == time(19, 0)
    # Then kept, as it holds them all now.
    assert seed_demo() == Seeded.KEPT


def test_seed_demo_makes_todays_shop_again_without_its_closures(monkeypatch: pytest.MonkeyPatch) -> None:
    # As for its rules: a deploy whose seed closes one more day than the one that made this morning's demo, as ATT-8's
    # first did, makes the shop again at once, so the page shows the closure the same day.
    seed_demo(fresh=True)
    made = the_demo_shop()
    tomorrow = shop_today(made) + timedelta(days=1)
    extra = PublicHoliday("Siku ya mfano", tomorrow.month, tomorrow.day)
    monkeypatch.setattr(services, "PUBLIC_HOLIDAYS", (*services.PUBLIC_HOLIDAYS, extra))

    assert seed_demo() == Seeded.MADE
    shop = the_demo_shop()
    assert shop != made
    with shop_context(shop):
        assert Closure.objects.filter(first_day=tomorrow, name="Siku ya mfano").exists()
    # Then kept, as it holds them all now.
    assert seed_demo() == Seeded.KEPT


def test_seed_demo_makes_todays_shop_again_without_its_peoples_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # As for its rules and closures: a deploy whose seed gives one of its people one more key than this morning's demo
    # holds, as PPL-4's gave Meneja staff.manage, makes the shop again at once, so the deploy shows what the key opens
    # the same day. Kept instead, the live demo went a whole day with no Wafanyakazi for Meneja (#275).
    seed_demo(fresh=True)
    made = the_demo_shop()
    meneja = next(person for person in services.PEOPLE if person.keys)
    # One of the owner's own four, which no role of the demo holds: only the seed's grant can give it.
    more = replace(meneja, keys=(*meneja.keys, Permission.PAY_APPROVE))
    monkeypatch.setattr(services, "PEOPLE", tuple(more if person is meneja else person for person in services.PEOPLE))

    assert seed_demo() == Seeded.MADE
    shop = the_demo_shop()
    assert shop != made
    with shop_context(shop):
        staff = StaffMember.objects.get(display_name=meneja.display_name)
        assert PermissionGrant.objects.filter(
            staff=staff, permission=Permission.PAY_APPROVE, side__isnull=True
        ).exists()
    # Then kept, as its people hold them all now.
    assert seed_demo() == Seeded.KEPT


def test_seed_demo_makes_todays_shop_again_without_its_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    # As for its rules, closures and keys: a deploy whose seed pays one of its people a rate this morning's demo doesn't
    # hold, as WAGE-1's first deploy gives everyone one, makes the shop again at once, so Wafanyakazi shows the pay the
    # same day, and the month page (ATT-5) lists the workers.
    seed_demo(fresh=True)
    made = the_demo_shop()
    asha = next(person for person in services.PEOPLE if person.display_name == "Asha")
    raised = replace(asha, daily_rate="11000")
    monkeypatch.setattr(services, "PEOPLE", tuple(raised if person is asha else person for person in services.PEOPLE))

    assert seed_demo() == Seeded.MADE
    shop = the_demo_shop()
    assert shop != made
    with shop_context(shop):
        assert PayRate.objects.get(staff__display_name="Asha").daily_rate == Decimal("11000.00")
    # Then kept, as its people hold their rates now.
    assert seed_demo() == Seeded.KEPT


def test_seed_demo_makes_todays_shop_again_without_its_taps(three_weeks: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # As for its rules, closures, keys and rates: DATA-8's deploy finds the demo the older seed made that morning, with
    # no day before today, and makes the shop again at once, so the month page (ATT-5) shows its weeks the same day.
    with monkeypatch.context() as older_seed:
        older_seed.setattr(services, "HISTORY_DAYS", 0)
        seed_demo(fresh=True)
    made = the_demo_shop()

    assert seed_demo() == Seeded.MADE
    shop = the_demo_shop()
    assert shop != made
    with shop_context(shop):
        assert AttendanceEvent.objects.exists()
    # Then kept, as it holds them now.
    assert seed_demo() == Seeded.KEPT


def test_seed_demo_keeps_todays_shop_with_its_taps(three_weeks: None) -> None:
    # The demo wakes from its 15-minute sleep: a demo made today with its weeks stays, with a visitor's work in it. A
    # check that never found the taps would make it again at every wake-up.
    seed_demo(fresh=True)
    made = the_demo_shop()

    assert seed_demo() == Seeded.KEPT
    assert the_demo_shop() == made


def test_seed_demo_keeps_its_peoples_rates_as_made() -> None:
    # Every visitor logs in as Meneja, who holds both keys a rate needs, so a visitor can try Weka malipo on a worker
    # they add (WAGE-1), with no note. The seed's people keep their rates: a visitor's 1 shilling for Asha would show to
    # every visitor after, until the morning's seed (demo.people_fixed); and Meneja can't set his own (staff.own is
    # never reached: his own login is the seed's too).
    seed_demo(fresh=True)

    with shop_context(the_demo_shop()):
        meneja = StaffMember.objects.select_related("shop").get(display_name="Meneja")
        for nickname in ("Asha", "Baraka", "Meneja"):
            person = StaffMember.objects.get(display_name=nickname)
            with pytest.raises(ValidationError) as setting:
                set_pay_rate(person, daily_rate=Decimal("1"), effective_from=person.started_on, by=meneja)
            assert setting.value.code == "demo.people_fixed", nickname
        juma = add_worker(shop=meneja.shop, full_name="Juma Mfano", display_name="Juma", by=meneja)
        rate = set_pay_rate(juma, daily_rate=Decimal("9000"), effective_from=juma.started_on, by=meneja)
        assert rate.created_by_id == meneja.pk
    # Still kept: the visitor's own worker's rate leaves the seed's as they were.
    assert seed_demo() == Seeded.KEPT


def test_seed_demo_makes_todays_shop_again_when_a_seed_persons_key_ended() -> None:
    # A key taken away is no key (PPL-7): if one of the seed's people lost a key the seed gives them, which only the
    # system can do there (demo.people_fixed), the demo is made again, so Meneja's page works for the next visitor.
    seed_demo(fresh=True)
    made = the_demo_shop()
    meneja = next(person for person in services.PEOPLE if person.keys)
    with shop_context(made):
        staff = StaffMember.objects.get(display_name=meneja.display_name)
        [key] = PermissionGrant.objects.filter(staff=staff, permission=meneja.keys[0], side__isnull=True)
        end_permission(key, reason="Jaribio la mfumo", by=None)

    assert seed_demo() == Seeded.MADE
    assert the_demo_shop() != made


def test_seed_demo_keeps_a_shop_whose_closure_a_visitor_changed() -> None:
    # A visitor moves the last day of one of the seed's closures, and cancels another: today's demo still holds what
    # the seed made, so the demo's next wake-up keeps it, and the visitor's work with it.
    seed_demo(fresh=True)
    shop = the_demo_shop()
    with shop_context(shop):
        first, second = Closure.objects.order_by("first_day")[:2]
        Closure.objects.filter(pk=first.pk).update(last_day=first.last_day + timedelta(days=1))
        Closure.objects.filter(pk=second.pk).update(status=ClosureStatus.CANCELLED)
    assert seed_demo() == Seeded.KEPT


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
    # the shop's time: kept. Read in UTC, 3 March and 4 March differ and the shop would wrongly be made again. Made at
    # that moment, not today: the shop then holds 4 March's coming holidays, as one made then would, and the seed keeps
    # a shop only if it holds its day's (ATT-8).
    made_at = datetime(2026, 3, 3, 21, 10, tzinfo=UTC)
    monkeypatch.setattr(timezone, "now", lambda: made_at)
    seed_demo(fresh=True)
    made = the_demo_shop()
    Shop.objects.filter(pk=made.pk).update(created_at=made_at)
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


class _Deadlock(Exception):
    # Stands in for psycopg's own error, which Django wraps in its OperationalError: the code is all the seed reads.
    sqlstate = "40P01"


def flush_that_clashes(monkeypatch: pytest.MonkeyPatch, times: int, sqlstate: str = "40P01") -> list[str]:
    # The seed's flush, failing as PostgreSQL ends it the first `times` calls, then running for real. Returns the calls.
    # Django's own call_command, the one the seed imports, so the real flush runs after the clashes.
    real = call_command
    calls: list[str] = []

    def flush(*args: Any, **kwargs: Any) -> None:
        calls.append(args[0])
        if len(calls) <= times:
            cause = _Deadlock()
            cause.sqlstate = sqlstate
            raise OperationalError("deadlock detected") from cause
        real(*args, **kwargs)

    monkeypatch.setattr(services, "call_command", flush)
    return calls


def test_seed_demo_tries_again_once_after_a_deadlock(monkeypatch: pytest.MonkeyPatch) -> None:
    # The nightly deploy: the old demo's request and the new start's wipe met halfway, and PostgreSQL ended the wipe.
    # One more try makes the shop, as if nothing happened.
    calls = flush_that_clashes(monkeypatch, times=1)

    assert seed_demo(fresh=True) == Seeded.MADE
    assert calls == ["flush", "flush"]
    assert the_demo_shop().kind == ShopKind.DEMO


def test_seed_demo_stops_after_a_second_deadlock(monkeypatch: pytest.MonkeyPatch) -> None:
    # Twice in a row is no passing clash: the start stops, and the deploy's smoke test shows it red.
    calls = flush_that_clashes(monkeypatch, times=2)

    with pytest.raises(OperationalError):
        seed_demo(fresh=True)
    assert calls == ["flush", "flush"]
    assert not Shop.objects.exists()


def test_seed_demo_stops_at_once_on_another_database_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Any other database error (here, permission denied) isn't a clash that passes: no second try.
    calls = flush_that_clashes(monkeypatch, times=1, sqlstate="42501")

    with pytest.raises(OperationalError):
        seed_demo(fresh=True)
    assert calls == ["flush"]


def test_seed_demo_switches_its_sides_on() -> None:
    # A demo shows a shop at work, so both its sides are switched on, as an owner would switch a real shop's on once he
    # starts using it (ADR-0033). A new side starts off (SHOP-2), so the seed does it, as the system (switch_side).
    seed_demo(fresh=True)

    with shop_context(the_demo_shop()):
        assert {(side.code, side.is_live) for side in Side.objects.all()} == {("D", True), ("F", True)}


def test_seed_demo_gives_each_side_its_band() -> None:
    # The demo shows each side's band under the top bar (SHOP-4): Dawa blue, Vyakula striped, like the Foods bags
    # (UI-8). A visitor can't change either (demo.sides_fixed), so every visitor sees the same two.
    seed_demo(fresh=True)

    with shop_context(the_demo_shop()):
        assert {(side.code, side.band) for side in Side.objects.all()} == {("D", "blue"), ("F", "striped")}


def test_seed_demo_lets_its_manager_change_the_shops_rules() -> None:
    # The demo has no owner, and a manager alone may not change the shop's rules (settings.manage is one of the
    # owner's own four, spec §6). Meneja holds that key besides the role, on the whole shop, so a visitor can try
    # Badilisha on Mipangilio ya duka (Jack, SHOP-5). Not the Owner's whole role: the demo's people stay as the seed
    # made them, which the Owner's role would let a visitor change (see the test below, PPL-4).
    seed_demo(fresh=True)

    with shop_context(the_demo_shop()):
        meneja = StaffMember.objects.get(display_name="Meneja")
        asha = StaffMember.objects.get(display_name="Asha")
        assert "settings.manage" in effective_permissions(meneja, None)
        for side in Side.objects.all():
            assert "settings.manage" in effective_permissions(meneja, side)
        # The sellers change no rule.
        assert "settings.manage" not in effective_permissions(asha, None)


def test_seed_demo_lets_a_visitor_manage_the_workers_they_add() -> None:
    # Every visitor logs in as Meneja, who holds staff.manage on the whole shop, so a visitor can try Wafanyakazi: add a
    # worker, then suspend him (Jack, PPL-4: A). The seed's people stay as made, so no visitor takes Asha or Baraka off
    # another visitor's PIN tiles, nor stops Meneja's one tap (demo.people_fixed; Meneja can't change himself).
    seed_demo(fresh=True)

    with shop_context(the_demo_shop()):
        meneja = StaffMember.objects.select_related("shop").get(display_name="Meneja")
        assert "staff.manage" in effective_permissions(meneja, None)
        juma = add_worker(shop=meneja.shop, full_name="Juma Mfano", display_name="Juma", by=meneja)
        assert suspend(juma, by=meneja, reason="Jaribio").status == "suspended"
        # Meneja among them: a visitor who suspended him, or marked him left, through his own login, would lock every
        # visitor after out of the office and stop every one tap.
        for nickname in ("Asha", "Baraka", "Meneja"):
            person = StaffMember.objects.get(display_name=nickname)
            with pytest.raises(ValidationError) as suspending:
                suspend(person, by=meneja, reason="Jaribio")
            with pytest.raises(ValidationError) as leaving:
                mark_left(person, left_on=person.started_on, by=meneja, reason="Jaribio")
            assert suspending.value.code == leaving.value.code == "demo.people_fixed", nickname
            assert StaffMember.objects.get(pk=person.pk).status == "active"


def test_seed_demo_closes_on_the_coming_public_holidays() -> None:
    # ATT-9's page shows a shop's closures, and a visitor tries Ondoa and a new last day on them (ATT-8): the demo
    # closes on the next three public holidays, added by the system, from the shop's own today.
    seed_demo(fresh=True)

    shop = the_demo_shop()
    today = shop_today(shop)
    with shop_context(shop):
        rows = Closure.objects.order_by("first_day")
        assert [(row.first_day, row.last_day, row.name, row.status, row.created_by) for row in rows] == [
            (first, last, name, ClosureStatus.ACTIVE, None) for first, last, name in coming_public_holidays(today)
        ]
    assert len(coming_public_holidays(today)) == 3


def test_coming_public_holidays() -> None:
    # The next three fixed-date public holidays from a day, that day's own among them; Krismasi and the day after as one
    # closure of two days. One that began before the day is left out: a closure can't start in the past.
    uhuru = (date(2026, 12, 9), date(2026, 12, 9), "Siku ya Uhuru")
    krismasi = (date(2026, 12, 25), date(2026, 12, 26), "Krismasi")
    mwaka_mpya = (date(2027, 1, 1), date(2027, 1, 1), "Mwaka Mpya")
    mapinduzi = (date(2027, 1, 12), date(2027, 1, 12), "Mapinduzi ya Zanzibar")
    karume = (date(2027, 4, 7), date(2027, 4, 7), "Siku ya Karume")
    assert coming_public_holidays(date(2026, 11, 16)) == [uhuru, krismasi, mwaka_mpya]
    assert coming_public_holidays(date(2026, 12, 25)) == [krismasi, mwaka_mpya, mapinduzi]
    # On the 26th Krismasi has begun, so the year's last ones come from the next year.
    assert coming_public_holidays(date(2026, 12, 26)) == [mwaka_mpya, mapinduzi, karume]


def test_seed_demo_sets_its_fines_and_switches_attendance_on(three_weeks: None) -> None:
    # A shop's fines start at nothing, as this public repo names no real amount (rule 10), so the demo types made-up
    # ones, and a visitor sees a late day's fine. Attendance is on (ADR-0033), so its laptops keep Mahudhurio (ATT-2):
    # from three weeks back, as are the fines and each person's first day, so the book counts the days the demo's
    # laptop tapped on (DATA-8). The day before, the shop had no attendance and no fines.
    seed_demo(fresh=True)

    shop = the_demo_shop()
    with shop_context(shop):
        three_weeks_back = shop_today(shop) - timedelta(days=21)
        assert get_setting(ATTENDANCE_ON, shop, on=three_weeks_back) is True
        assert get_setting(LATE_FINE, shop, on=three_weeks_back) == Decimal("500.00")
        assert get_setting(SECOND_FINE, shop, on=three_weeks_back) == Decimal("1500.00")
        assert get_setting(ATTENDANCE_ON, shop, on=three_weeks_back - timedelta(days=1)) is False
        # Set by the system, with no note, as no person of the demo set them.
        rows = Setting.objects.order_by("key")
        assert [(row.key, row.effective_from, row.note, row.created_by) for row in rows] == [
            ("attendance.enabled", three_weeks_back, "", None),
            ("attendance.late_fine", three_weeks_back, "", None),
            ("attendance.second_fine", three_weeks_back, "", None),
        ]
        assert set(StaffMember.objects.values_list("started_on", flat=True)) == {three_weeks_back}


def test_seed_demo_numbers_every_record_once(three_weeks: None) -> None:
    # A visitor's new laptop starts from the demo shop's change log (SYNC-3): every record it gets names a line, made
    # through the services, and the seed numbers them all once, at the end of its one block (SYNC-15). The demo shop's
    # two sides, their two drawers, its three rules (ATT-2) and its three people: ten lines, from 1. Then the demo
    # laptop's taps (DATA-8), each numbered as the push numbers any document, at the end of its own (SYNC-4): its line
    # is the tap's posted_seq. No laptop is sent a tap, so the pull skips those lines (apps/sync/pull.py).
    with mock.patch("apps.core.changes.next_numbers", wraps=next_numbers) as numbering:
        seed_demo(fresh=True)

    shop = the_demo_shop()
    with shop_context(shop):
        taps = {event.pk for event in AttendanceEvent.objects.all()}
    assert numbering.call_args_list == [
        mock.call(shop.pk, SequenceName.CHANGE, 10),
        *[mock.call(shop.pk, SequenceName.CHANGE, 1)] * len(taps),
    ]
    lines = lines_after(shop, 0)
    assert [number for number, *_ in lines] == list(range(1, 11 + len(taps)))
    assert all(op == ChangeOp.UPSERT for *_, op in lines)
    # One line for each record a laptop is sent, and one for each tap, and none for anything else: the registry's rows
    # (apps/sync/registry.py).
    with shop_context(shop):
        sent = {(code, row.pk) for code, entry in REGISTRY.items() for row in entry.rows(shop)}
    assert {(entity, record_id) for _number, entity, record_id, _op in lines} == sent | {
        ("attendance_event", tap) for tap in taps
    }


def test_seed_demo_gives_three_weeks_of_taps(three_weeks: None) -> None:
    # The card's first box (DATA-8): the 21 days before today, worked out by the book (ATT-10), give each of the demo's
    # people the days the card names, wherever today falls. 21 days hold three Sundays, off, so 18 working days each:
    # Asha late twice, a half day and a day to decide; Baraka late once and absent once; Meneja late once.
    seed_demo(fresh=True)

    shop = the_demo_shop()
    with shop_context(shop):
        today = shop_today(shop)
        days = work_out_days(shop, today - timedelta(days=21), today - timedelta(days=1))
    kinds = {
        name: Counter(day.status for day in days if day.staff.display_name == name)
        for name in ("Asha", "Baraka", "Meneja")
    }
    assert kinds == {
        "Asha": {
            DayStatus.ON_TIME: 14,
            DayStatus.LATE: 2,
            DayStatus.HALF: 1,
            DayStatus.NEEDS_REVIEW: 1,
            DayStatus.OFF: 3,
        },
        "Baraka": {DayStatus.ON_TIME: 16, DayStatus.LATE: 1, DayStatus.ABSENT: 1, DayStatus.OFF: 3},
        "Meneja": {DayStatus.ON_TIME: 17, DayStatus.LATE: 1, DayStatus.OFF: 3},
    }
    # Each late day takes its fine: Asha's 08:10 the second, 1,500, the others the first, 500 (DEMO_RULES).
    assert sorted((day.staff.display_name, day.fine) for day in days if day.status == DayStatus.LATE) == [
        ("Asha", Decimal("500.00")),
        ("Asha", Decimal("1500.00")),
        ("Baraka", Decimal("500.00")),
        ("Meneja", Decimal("500.00")),
    ]
    # The one day to decide is Asha's latest working day, the day before today, or Saturday when today is Monday: an
    # Ingia with no Toka. So the month page's list always shows it, at the top of the latest month (ATT-5).
    latest = today - timedelta(days=2 if today.weekday() == 0 else 1)
    to_decide = [(day.staff.display_name, day.date, day.review_reason) for day in days if day.review_reason]
    assert to_decide == [("Asha", latest, ReviewReason.NO_OUT)]


def test_seed_demo_taps_are_the_laptops_time(three_weeks: None) -> None:
    # Each tap reaches the server as a laptop's do, through the push (SYNC-4), from the demo's laptop on Dawa, sent at
    # the reset, long after it was made: so the server keeps the laptop's time (device_ok, ATT-1), as no sign says its
    # clock moved, and no photo, as the demo keeps none (ATT-3). The laptop numbers them from 1 with none missing, every
    # line of the answer log says accepted, and nothing is flagged.
    seed_demo(fresh=True)

    shop = the_demo_shop()
    with shop_context(shop):
        laptop = Device.objects.select_related("home_side").get()
        taps = list(AttendanceEvent.objects.order_by("device_seq"))
        assert (laptop.name, laptop.home_side.code) == ("Laptop ya Dawa", "D")
        assert {(tap.device_id, tap.time_check, tap.no_photo) for tap in taps} == {
            (laptop.pk, TimeCheck.DEVICE_OK, NoPhoto.DEMO)
        }
        assert all(tap.trusted_time == tap.client_time for tap in taps)
        assert [tap.device_seq for tap in taps] == list(range(1, len(taps) + 1))
        assert list(PushedDocument.objects.values_list("status", flat=True).distinct()) == [PushedStatus.ACCEPTED]
        assert PushedDocument.objects.count() == len(taps)
        assert not Flag.objects.exists()


def test_seed_demo_stops_when_a_tap_is_refused(three_weeks: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # The push never raises for a tap it refuses: it answers invalid and goes on (03 §6.3). A refused tap is a bug in
    # the seed, so the reset stops, and its one transaction takes the wipe back too: the demo made before stays, never
    # a shop with holes in its weeks (DATA-8's card).
    seed_demo(fresh=True)
    made = the_demo_shop()

    def refuses(laptop: Device, documents: list[Any], **kwargs: object) -> list[Answer]:
        return [Answer(id=document.id, status=PushedStatus.INVALID, code="invalid") for document in documents]

    monkeypatch.setattr(services, "push", refuses)

    with pytest.raises(RuntimeError, match="refused the demo laptop's taps"):
        seed_demo(fresh=True)
    assert the_demo_shop() == made
