"""apps/people/tests/test_owner_commands.py — `manage.py owner`: the superuser sets up a shop's owner (PPL-13).

Nobody in a shop may make someone Owner or set the Owner's PIN (PPL-7), so the superuser does it on the server:

    owner add --shop MFANO: Baba, Baba Mfano, 0712 345 678, PIN twice (unseen), yes
        → Baba works at MFANO, holds the Owner role on every side, and has his PIN: his tile reaches the laptops
    owner set-pin --shop MFANO --nickname Baba: PIN twice (unseen)
        → a new PIN; his lock from wrong tries is lifted on every device
    owner take --shop MFANO --nickname Baba: the reason (and a yes, if he is the last working Owner)
        → every Owner row of his ended, with that reason; his job and PIN stay

Each test types its answers in through the `keyboard` fixture (conftest.py), PINs apart, as getpass reads them. Fake
shops and people only: the repo is public.
"""

import shlex
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from pytest_django import Settings

from apps.core.changes import recording_changes
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, PinLock, Role, RoleAssignment, StaffMember, User
from apps.people.pins import PIN_TRIES, pin_matches
from apps.people.services import add_worker, assign_role, check_pin, mark_left, set_pin, set_up_shop, suspend
from apps.shops.models import Shop, Side
from apps.shops.selectors import shop_today
from apps.shops.services import NewSide
from tests.change_log import lines_written
from tests.keyboard import Keyboard

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


def an_owner(shop: Shop, nickname: str, *, pin: str | None = None) -> StaffMember:
    # Someone the superuser made Owner on every side earlier, as owner add does, through the same services.
    with shop_context(shop), recording_changes(shop):
        staff = add_worker(shop=shop, full_name=f"{nickname} Mfano", display_name=nickname, by=None)
        assign_role(staff, Role.objects.get(template=RoleTemplate.OWNER), side=None, by=None)
        if pin is not None:
            set_pin(staff, pin, by=None)
    return staff


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


@pytest.mark.parametrize("action", [("add",), ("set-pin", "--nickname", "Baba")])
def test_the_pin_is_never_an_argument(mfano: Shop, keyboard: Keyboard, action: tuple[str, ...]) -> None:
    # An argument stays in the shell's history and shows in the server's list of running programs (the card's default).
    with pytest.raises(CommandError, match="unrecognized arguments: --pin"):
        owner(*action, "--shop", "MFANO", "--pin", PIN)


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


def test_owner_add_never_finds_another_shops_worker(mfano: Shop, keyboard: Keyboard) -> None:
    # T1, rule 1. Baba is the Owner of PILI, the shop next door. At MFANO he is nobody: the nickname is looked for
    # inside MFANO's shop_context, where the tenancy guard shows MFANO's rows alone, so a new person is asked for, and
    # PILI's Baba is never given MFANO's role. No other test pins this: a lookup through every shop would pass them all.
    pili = set_up_shop(name="Duka la Pili", code="PILI", sides=[NewSide("D", "Dawa")])
    pilis_baba = an_owner(pili, "Baba", pin=PIN)
    keyboard.type("Baba", "Baba Mfano", PHONE, "y")
    keyboard.type_pins("3907", "3907")

    said = owner("add", "--shop", "MFANO")

    assert "already works" not in said
    with shop_context(mfano):
        baba = StaffMember.objects.get(display_name="Baba")
    assert baba.user_id != pilis_baba.user_id
    # PILI's Baba is as he was: PILI's Owner, with his own PIN.
    assert owner_rows(pilis_baba) == [(RoleTemplate.OWNER, None, None)]
    with shop_context(pili):
        assert pin_matches(PIN, StaffMember.objects.get(pk=pilis_baba.pk).pin_hash)


@pytest.mark.parametrize("action", ["set-pin", "take"])
def test_set_pin_and_take_never_find_another_shops_worker(mfano: Shop, keyboard: Keyboard, action: str) -> None:
    # The same for a change: MFANO's command can't set PILI's Owner's PIN, nor take his role. Nothing is asked.
    pili = set_up_shop(name="Duka la Pili", code="PILI", sides=[NewSide("D", "Dawa")])
    pilis_baba = an_owner(pili, "Baba", pin=PIN)

    with pytest.raises(CommandError, match="Nobody working at MFANO has the nickname Baba."):
        owner(action, "--shop", "MFANO", "--nickname", "Baba")

    assert owner_rows(pilis_baba) == [(RoleTemplate.OWNER, None, None)]
    with shop_context(pili):
        assert pin_matches(PIN, StaffMember.objects.get(pk=pilis_baba.pk).pin_hash)


def test_an_unknown_shop_is_refused(mfano: Shop, keyboard: Keyboard) -> None:
    with pytest.raises(CommandError, match="No shop has the code NOPE."):
        owner("add", "--shop", "nope")


@pytest.mark.parametrize("action", [("add",), ("set-pin", "--nickname", "Baba"), ("take", "--nickname", "Baba")])
def test_owner_is_refused_on_the_demo(
    mfano: Shop, keyboard: Keyboard, settings: Settings, action: tuple[str, ...]
) -> None:
    # The demo's seed makes its own people, and keeps them as made (DATA-1). Refused before anything is asked or read.
    baba = an_owner(mfano, "Baba", pin=PIN)
    settings.DEMO_SEED = True

    with pytest.raises(CommandError, match="Refused on the demo"):
        owner(*action, "--shop", "MFANO")

    assert keyboard.asked == []
    with shop_context(mfano):
        assert StaffMember.objects.get() == baba
        assert pin_matches(PIN, StaffMember.objects.get().pin_hash)
    assert owner_rows(baba) == [(RoleTemplate.OWNER, None, None)]


@pytest.mark.parametrize(("nickname", "typed"), [("Juma", "Juma"), ("Mama Juma", "'Mama Juma'")])
def test_owner_add_points_a_worker_with_no_pin_to_set_pin(
    mfano: Shop, keyboard: Keyboard, nickname: str, typed: str
) -> None:
    # No PIN, no tile on the shop's laptops: the command names the next one to run, ready to copy. A nickname with a
    # space, common in Swahili (Mama Juma), is quoted, or the shell would split it in two and argparse refuse the rest.
    with shop_context(mfano):
        juma = add_worker(shop=mfano, full_name="Juma Mfano", display_name=nickname, by=None)
    keyboard.type(nickname, "y")

    said = owner("add", "--shop", "MFANO")

    printed = f"python manage.py owner set-pin --shop MFANO --nickname {typed}"
    assert f"No PIN yet: {printed}" in said
    # The printed command works as it is: split as the shell splits it, it gives the PIN to the same person.
    keyboard.type_pins(PIN, PIN)
    owner(*shlex.split(printed)[3:])
    with shop_context(mfano):
        assert pin_matches(PIN, StaffMember.objects.get(pk=juma.pk).pin_hash)


# --- set-pin


def test_owner_set_pin_gives_a_new_pin_and_lifts_the_lock(mfano: Shop, keyboard: Keyboard) -> None:
    # Baba forgot his PIN, and his wrong tries locked him out of the Dawa laptop (AUTH-4). The new PIN logs him in at
    # once there: set_pin lifts every lock, and moves his PIN's time, which ends the logins made with the old one.
    baba = an_owner(mfano, "Baba", pin=PIN)
    with shop_context(mfano):
        laptop = Device.objects.create(
            shop=mfano, home_side=Side.objects.get(code="D"), name="Laptop ya Dawa", code=1, key_hash="a" * 64
        )
        for _ in range(PIN_TRIES):
            with pytest.raises(ValidationError):
                check_pin(baba, laptop, "9157", at=timezone.now())
        assert PinLock.objects.get(staff=baba).locked_until is not None
        # Read again: set_pin saved the time on its own copy of the row, not on the one an_owner handed back.
        before = StaffMember.objects.get(pk=baba.pk).pin_changed_at
    keyboard.type_pins("3907", "3907")

    with lines_written(mfano) as lines:
        said = owner("set-pin", "--shop", "MFANO", "--nickname", "baba")

    with shop_context(mfano):
        baba = StaffMember.objects.get(pk=baba.pk)
        lock = PinLock.objects.get(staff=baba)
    assert pin_matches("3907", baba.pin_hash)
    assert not pin_matches(PIN, baba.pin_hash)
    assert baba.pin_changed_at is not None and before is not None and baba.pin_changed_at > before
    assert (lock.wrong_tries, lock.locked_until) == (0, None)
    # His staff line: each laptop drops its offline check of the old PIN at its next sync (SYNC-15).
    assert lines == [("staff", baba.pk, "upsert")]
    assert "A new PIN for Baba Mfano, Baba at MFANO (active)." in said
    assert "Any lock from wrong tries is lifted, on every device." in said
    assert "3907" not in said


def test_owner_set_pin_serves_any_current_worker(mfano: Shop, keyboard: Keyboard) -> None:
    # The card's default: the superuser may help anyone when no manager is there, a suspended worker too, who needs it
    # once brought back. Two PINs that differ, and one too easy, are asked again here as in `add`.
    with shop_context(mfano):
        juma = add_worker(shop=mfano, full_name="Juma Mfano", display_name="Juma", by=None)
        suspend(juma, by=None, reason="Away for a month")
    keyboard.type_pins("3907", "3970", "1111", "1111", "3907", "3907")

    said = owner("set-pin", "--shop", "MFANO", "--nickname", "Juma")

    assert "The two PINs differ." in said
    assert "pin.too_easy: " in said
    with shop_context(mfano):
        assert pin_matches("3907", StaffMember.objects.get(pk=juma.pk).pin_hash)


@pytest.mark.parametrize("action", ["set-pin", "take"])
def test_nobody_is_found_by_a_nickname_of_one_who_left(mfano: Shop, keyboard: Keyboard, action: str) -> None:
    # One who left is history: set_pin and end_role would refuse them (staff.left), so they aren't even found, and
    # nothing is asked.
    baba = an_owner(mfano, "Baba", pin=PIN)
    with shop_context(mfano):
        mark_left(baba, left_on=shop_today(mfano), by=None, reason="Sold the shop")

    with pytest.raises(CommandError, match="Nobody working at MFANO has the nickname Baba."):
        owner(action, "--shop", "MFANO", "--nickname", "Baba")


# --- take


def test_owner_take_ends_the_owner_role_with_its_reason(mfano: Shop, keyboard: Keyboard) -> None:
    # Two Owners working: Baba's role is taken with a reason, and Mama, still Owner, means nothing more is asked.
    baba = an_owner(mfano, "Baba", pin=PIN)
    mama = an_owner(mfano, "Mama")
    keyboard.type("Handed the shop to Mama")

    with lines_written(mfano) as lines:
        said = owner("take", "--shop", "MFANO", "--nickname", "Baba")

    with shop_context(mfano):
        row = RoleAssignment.objects.get(staff=baba)
        baba = StaffMember.objects.get(pk=baba.pk)
    # Ended, never deleted (rule 7), with when and why, by the superuser, whom nobody names.
    assert (row.end_reason, row.ended_by_id) == ("Handed the shop to Mama", None)
    assert row.ended_at is not None
    assert owner_rows(mama) == [(RoleTemplate.OWNER, None, None)]
    # His job and PIN stay: he may still work there, and the owner gives him another role if he does.
    assert (baba.status, pin_matches(PIN, baba.pin_hash)) == ("active", True)
    assert lines == [("staff", baba.pk, "upsert")]
    assert "Baba Mfano, Baba at MFANO, is Owner on: every side." in said
    assert keyboard.asked == ["Why is it taken away: "]


def test_owner_take_ends_every_owner_row_of_that_person(mfano: Shop, keyboard: Keyboard) -> None:
    # Jack, PPL-13: 4A. Baba is Owner on every side and on Dawa too: both end, together, with the one reason, so nothing
    # of the Owner's is left behind. One staff line, as one block holds both ends.
    baba = an_owner(mfano, "Baba")
    an_owner(mfano, "Mama")
    with shop_context(mfano):
        assign_role(baba, Role.objects.get(template=RoleTemplate.OWNER), side=Side.objects.get(code="D"), by=None)
    keyboard.type("Handed the shop to Mama")

    with lines_written(mfano) as lines:
        said = owner("take", "--shop", "MFANO", "--nickname", "Baba")

    assert "is Owner on: every side, Dawa." in said
    assert owner_rows(baba) == []
    with shop_context(mfano):
        assert set(RoleAssignment.objects.filter(staff=baba).values_list("end_reason", flat=True)) == {
            "Handed the shop to Mama"
        }
    assert lines == [("staff", baba.pk, "upsert")]


@pytest.mark.parametrize(("answer", "taken"), [("y", True), ("n", False), ("", False)])
def test_taking_the_last_owner_asks_once_more(mfano: Shop, keyboard: Keyboard, answer: str, taken: bool) -> None:
    # The card's default: with no Owner working, nobody at the shop holds the owner's own keys, and nobody there can
    # give the role again. So a yes is asked, and only y or yes takes it.
    baba = an_owner(mfano, "Baba")
    keyboard.type("Sold the shop", answer)

    said = owner("take", "--shop", "MFANO", "--nickname", "Baba")

    assert "No other Owner is working at MFANO." in said
    assert keyboard.asked[-1] == "Take it all the same? [y/N]: "
    assert owner_rows(baba) == ([] if taken else [(RoleTemplate.OWNER, None, None)])
    assert ("Nothing written." in said) is not taken


def test_a_suspended_owner_is_not_another_owner(mfano: Shop, keyboard: Keyboard) -> None:
    # Jack, PPL-13: 4A. Mama is Owner but suspended: she holds nothing until brought back, so Baba is the last working
    # Owner, and the yes is asked.
    baba = an_owner(mfano, "Baba")
    mama = an_owner(mfano, "Mama")
    with shop_context(mfano):
        suspend(mama, by=None, reason="Away for a month")
    keyboard.type("Sold the shop", "y")

    said = owner("take", "--shop", "MFANO", "--nickname", "Baba")

    assert "No other Owner is working at MFANO." in said
    assert owner_rows(baba) == []


def test_a_suspended_owner_taken_hears_no_untrue_words(mfano: Shop, keyboard: Keyboard) -> None:
    # Baba himself is suspended, and nobody else is Owner: the words must not call him "working" (PPL-13's review),
    # nor claim nobody holds the owner's keys, as a manager may hold them one by one.
    baba = an_owner(mfano, "Baba")
    with shop_context(mfano):
        suspend(baba, by=None, reason="Away for a month")
    keyboard.type("Sold the shop", "y")

    said = owner("take", "--shop", "MFANO", "--nickname", "Baba")

    assert "No other Owner is working at MFANO." in said
    assert "only with someone given them one by one" in said
    assert "Baba is" not in said and "nobody there approves" not in said
    assert owner_rows(baba) == []


def test_a_blank_reason_is_asked_again(mfano: Shop, keyboard: Keyboard) -> None:
    # Rule 7: an end is always kept with its why. end_role refuses a blank one too; the command asks again first.
    baba = an_owner(mfano, "Baba")
    an_owner(mfano, "Mama")
    keyboard.type("  ", "Handed the shop to Mama")

    said = owner("take", "--shop", "MFANO", "--nickname", "Baba")

    assert "An answer is needed." in said
    assert owner_rows(baba) == []


def test_owner_take_refuses_someone_with_no_owner_role(mfano: Shop, keyboard: Keyboard) -> None:
    # Juma works there, as a worker: there is nothing of the Owner's to take, and nothing is asked.
    with shop_context(mfano):
        add_worker(shop=mfano, full_name="Juma Mfano", display_name="Juma", by=None)

    with pytest.raises(CommandError, match="Juma holds no Owner role at MFANO."):
        owner("take", "--shop", "MFANO", "--nickname", "Juma")
