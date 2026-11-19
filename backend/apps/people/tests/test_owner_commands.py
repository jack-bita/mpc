"""apps/people/tests/test_owner_commands.py — `manage.py owner`: the superuser sets up a shop's owner (PPL-13).

Nobody in a shop may make someone Owner or set the Owner's PIN (PPL-7), so the superuser does it on the server:

    owner add --shop MFANO: Baba, Baba Mfano, 0712 345 678, PIN twice (unseen), yes
        → Baba works at MFANO, holds the Owner role on every side, and has his PIN: his tile reaches the laptops

Each test types its answers in through the `keyboard` fixture (conftest.py), PINs apart, as getpass reads them. Fake
shops and people only: the repo is public.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest_django import Settings

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context, system_context
from apps.people.models import RoleAssignment, StaffMember, User
from apps.people.pins import pin_matches
from apps.people.services import add_worker, set_up_shop
from apps.people.tests.conftest import Keyboard
from apps.shops.models import Shop
from apps.shops.services import NewSide
from tests.change_log import lines_written

pytestmark = pytest.mark.django_db

PIN = "4826"
PHONE = "0712 345 678"


@pytest.fixture
def mfano() -> Shop:
    # A shop as open_shop leaves it: its sides and its six roles, nobody working there yet.
    return set_up_shop(name="Duka la Mfano", code="MFANO", sides=[NewSide("D", "Dawa"), NewSide("F", "Vyakula")])


def owner(*args: str) -> str:
    # The command as the superuser runs it; what it said, for the test to read.
    out = StringIO()
    call_command("owner", *args, stdout=out)
    return out.getvalue()


def owner_rows(staff: StaffMember) -> list[tuple[str, object, object]]:
    # The person's open Owner rows, as (template, side, who gave it).
    with shop_context(staff.shop_id):
        rows = RoleAssignment.objects.filter(staff=staff, role__template=RoleTemplate.OWNER, ended_at=None)
        return [(row.role.template, row.side_id, row.created_by_id) for row in rows.select_related("role")]


def test_owner_add_makes_a_new_owner_with_his_pin(mfano: Shop, keyboard: Keyboard) -> None:
    keyboard.type("Baba", "Baba Mfano", PHONE, "y")
    keyboard.type_pins(PIN, PIN)

    with lines_written(mfano) as lines:
        said = owner("add", "--shop", "mfano")

    with shop_context(mfano):
        baba = StaffMember.objects.select_related("user").get(display_name="Baba")
    # The person, their job here, and the phone in its one stored form (+255…).
    assert (baba.user.full_name, baba.user.phone, baba.status) == ("Baba Mfano", "+255712345678", "active")
    # The Owner role on every side (side None), given by the superuser, whom nobody names (by=None).
    assert owner_rows(baba) == [(RoleTemplate.OWNER, None, None)]
    # His PIN, as typed, and its time, which his laptops read.
    assert pin_matches(PIN, baba.pin_hash)
    assert baba.pin_changed_at is not None
    # His staff line for the shop's laptops, once, as all three services joined one block: his tile shows on each laptop
    # after its next sync (SYNC-15).
    assert lines == [("staff", baba.pk, "upsert")]
    assert "Baba is now MFANO's Owner on every side, with a PIN." in said


def test_owner_add_shows_everything_before_the_yes_but_the_pin(
    mfano: Shop, keyboard: Keyboard, capsys: pytest.CaptureFixture[str]
) -> None:
    keyboard.type("Baba", "Baba Mfano", PHONE, "y")
    keyboard.type_pins(PIN, PIN)

    said = owner("add", "--shop", "MFANO")

    shown = said[: said.index("is now")]
    assert f"New at MFANO: Baba Mfano, nickname Baba, phone {PHONE}." in shown
    assert "the Owner role on every side, and the PIN just typed" in shown
    # The PIN was asked with getpass, never input(), and is shown nowhere: not in what the command said, nor in anything
    # else written to the screen.
    assert keyboard.asked == [
        "Nickname, as the PIN tiles show it: ",
        "Full name: ",
        "Phone, or Enter for none: ",
        "New PIN, 4 digits (not shown): ",
        "The same PIN again: ",
        "Make them the Owner? [y/N]: ",
    ]
    screen = capsys.readouterr()
    assert PIN not in said + screen.out + screen.err


def test_the_pin_is_never_an_argument(mfano: Shop, keyboard: Keyboard) -> None:
    # An argument stays in the shell's history and shows in the server's list of running programs (the card's default).
    with pytest.raises(CommandError, match="unrecognized arguments: --pin"):
        owner("add", "--shop", "MFANO", "--pin", PIN)


@pytest.mark.parametrize("answer", ["n", ""])
def test_owner_add_writes_nothing_without_a_yes(mfano: Shop, keyboard: Keyboard, answer: str) -> None:
    keyboard.type("Baba", "Baba Mfano", PHONE, answer)
    keyboard.type_pins(PIN, PIN)

    said = owner("add", "--shop", "MFANO")

    assert "Nothing written." in said
    assert not User.objects.exists()
    with shop_context(mfano):
        assert not StaffMember.objects.exists()


def test_two_pins_that_differ_are_asked_again(mfano: Shop, keyboard: Keyboard) -> None:
    keyboard.type("Baba", "Baba Mfano", PHONE, "y")
    keyboard.type_pins(PIN, "4827", PIN, PIN)

    said = owner("add", "--shop", "MFANO")

    assert "The two PINs differ. Type them again." in said
    with shop_context(mfano):
        assert pin_matches(PIN, StaffMember.objects.get().pin_hash)


@pytest.mark.parametrize(("weak", "code"), [("1234", "pin.too_easy"), ("482", "pin.not_four_digits")])
def test_a_pin_its_rule_refuses_is_asked_again_at_once(mfano: Shop, keyboard: Keyboard, weak: str, code: str) -> None:
    # Jack, PPL-13: 2A. Asked as soon as it is typed, by the rule's own function, not after the person is made: the
    # answers typed before it are kept.
    keyboard.type("Baba", "Baba Mfano", PHONE, "y")
    keyboard.type_pins(weak, weak, PIN, PIN)

    said = owner("add", "--shop", "MFANO")

    assert f"{code}: " in said
    assert weak not in said
    with shop_context(mfano):
        assert pin_matches(PIN, StaffMember.objects.get().pin_hash)


def test_owner_add_warns_of_a_person_with_no_phone(mfano: Shop, keyboard: Keyboard) -> None:
    # Jack, PPL-13: 3A. Allowed, as on the office's form: the PIN works without one. The warning comes before the yes,
    # as the admin's temporary password, the runbook's next step, needs a phone or an email to log in by.
    keyboard.type("Baba", "Baba Mfano", "", "y")
    keyboard.type_pins(PIN, PIN)

    said = owner("add", "--shop", "MFANO")

    assert said.index("No phone: they can't log in with a password") < said.index("is now")
    with shop_context(mfano):
        assert StaffMember.objects.select_related("user").get().user.phone is None


def test_a_taken_phone_is_refused_and_writes_nothing(mfano: Shop, keyboard: Keyboard) -> None:
    # Asha works at another shop with this phone. A person at two shops waits for AUTH-7, so the phone is refused like
    # any phone a person has (unique), as on the office's form (PPL-10): never saying whose. All or nothing: no person,
    # job, role or PIN is left behind.
    other = set_up_shop(name="Duka la Pili", code="PILI", sides=[NewSide("D", "Dawa")])
    with shop_context(other):
        add_worker(shop=other, full_name="Asha Mfano", display_name="Asha", phone=PHONE, by=None)
    keyboard.type("Baba", "Baba Mfano", PHONE, "y")
    keyboard.type_pins(PIN, PIN)

    with pytest.raises(CommandError, match=r"Refused, nothing written:\n  unique \(phone\): "):
        owner("add", "--shop", "MFANO")

    assert User.objects.count() == 1
    with shop_context(mfano):
        assert not StaffMember.objects.exists()


def test_owner_add_gives_a_worker_already_there_the_role_alone(mfano: Shop, keyboard: Keyboard) -> None:
    # Juma works at MFANO already. Typed in small letters, as the nickname's own rule ignores letter case. He is given
    # the role alone, after a yes: no full name, phone or PIN is asked, and his own stay as they are.
    with shop_context(mfano):
        juma = add_worker(shop=mfano, full_name="Juma Mfano", display_name="Juma", phone=PHONE, by=None)
    keyboard.type("juma", "y")

    with lines_written(mfano) as lines:
        said = owner("add", "--shop", "MFANO")

    assert "Juma Mfano already works at MFANO as Juma (active)." in said
    assert "Juma is now MFANO's Owner on every side." in said
    assert owner_rows(juma) == [(RoleTemplate.OWNER, None, None)]
    assert User.objects.count() == 1
    with shop_context(mfano):
        assert StaffMember.objects.get().pin_hash == ""
    assert lines == [("staff", juma.pk, "upsert")]


def test_owner_add_asks_a_yes_for_a_worker_already_there(mfano: Shop, keyboard: Keyboard) -> None:
    with shop_context(mfano):
        juma = add_worker(shop=mfano, full_name="Juma Mfano", display_name="Juma", by=None)
    keyboard.type("Juma", "n")

    said = owner("add", "--shop", "MFANO")

    assert "Nothing written." in said
    assert owner_rows(juma) == []


def test_an_owner_already_is_refused_by_the_roles_own_rule(mfano: Shop, keyboard: Keyboard) -> None:
    # The second add finds him already working there, and assign_role refuses the same role on the same sides twice.
    keyboard.type("Baba", "Baba Mfano", PHONE, "y", "Baba", "y")
    keyboard.type_pins(PIN, PIN)
    owner("add", "--shop", "MFANO")

    with pytest.raises(CommandError, match=r"role\.already_given"):
        owner("add", "--shop", "MFANO")


def test_an_unknown_shop_is_refused(mfano: Shop, keyboard: Keyboard) -> None:
    with pytest.raises(CommandError, match="No shop has the code NOPE."):
        owner("add", "--shop", "nope")


def test_owner_add_is_refused_on_the_demo(mfano: Shop, keyboard: Keyboard, settings: Settings) -> None:
    # The demo's seed makes its own people, and keeps them as made (DATA-1). Refused before anything is asked.
    settings.DEMO_SEED = True

    with pytest.raises(CommandError, match="Refused on the demo"):
        owner("add", "--shop", "MFANO")

    assert keyboard.asked == []
    with system_context():
        assert not StaffMember.objects.exists()
