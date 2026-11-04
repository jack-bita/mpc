"""apps/people/tests/test_pin_lock.py — wrong PINs lock a person on one device (AUTH-4; 03 §5.9).

A PIN has only 4 digits, so without a lock a coworker could keep guessing until one works. Five wrong tries lock that
person, on that device, for a minute, and each lock after that lasts twice as long, up to an hour (Jack, 4 Nov 2026):

    5 wrong ──▶ wait 1 minute ──▶ 5 wrong ──▶ wait 2 ──▶ 4 ──▶ 8 ──▶ 16 ──▶ 32 ──▶ 60 ──▶ 60 ...

Someone who only mistyped waits one minute; someone guessing soon gives up. The limit is there because of the other way
round: someone typing wrong PINs on purpose, to keep a coworker out, could otherwise stretch her wait to days. The right
PIN starts it all again from zero, and so does a new PIN, which needs no waiting. These tests call the service
(check_pin, apps/people/services.py) with the time each try happens, so none of them waits for a clock.

Fake data only: the repo is public (03 §10).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, PinLock, StaffMember, User
from apps.people.pins import pin_matches
from apps.people.services import add_staff, check_pin, confirm_pairing, set_pin, start_pairing
from apps.shops.models import Shop, Side
from tests.concurrency import in_another_transaction

pytestmark = pytest.mark.django_db

GiveRole = Callable[[StaffMember, RoleTemplate, Side | None], None]

PIN = "4829"
WRONG = "4830"
NEW_PIN = "5930"
START = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)


def a_device(manager: StaffMember, side: Side, name: str) -> Device:
    # A device paired the way the app pairs one: it asks, and a manager confirms its code.
    asked = start_pairing()
    with shop_context(manager.shop_id):
        return confirm_pairing(asked.request.code, name=name, home_side=side, by=manager)


@pytest.fixture
def manager(staff_a2: StaffMember, side_a: Side, give_role: GiveRole) -> StaffMember:
    give_role(staff_a2, RoleTemplate.MANAGER, None)
    return staff_a2


@pytest.fixture
def laptop(manager: StaffMember, side_a: Side) -> Device:
    return a_device(manager, side_a, "Laptop ya Dawa")


@pytest.fixture
def asha(staff_a: StaffMember) -> StaffMember:
    with shop_context(staff_a.shop_id):
        return set_pin(staff_a, PIN, by=None)


@pytest.fixture
def juma(shop_a: Shop) -> StaffMember:
    user = User.objects.create_user(full_name="Juma Demo")
    with shop_context(shop_a):
        return set_pin(add_staff(shop=shop_a, user=user, display_name="Juma", by=None), PIN, by=None)


def five_wrong_tries(staff: StaffMember, device: Device, *, at: datetime) -> ValidationError:
    # The refusal of the fifth, the one that locks.
    for _ in range(5):
        with pytest.raises(ValidationError) as refused:
            check_pin(staff, device, WRONG, at=at)
    return refused.value


def test_four_wrong_tries_lock_nobody(asha: StaffMember, laptop: Device) -> None:
    with shop_context(asha.shop_id):
        for _ in range(4):
            with pytest.raises(ValidationError) as refused:
                check_pin(asha, laptop, WRONG, at=START)
            assert refused.value.code == "pin.wrong"
        # The fifth says so at once, with the wait, so the screen can tell her how long.
        with pytest.raises(ValidationError) as refused:
            check_pin(asha, laptop, WRONG, at=START)
    assert refused.value.code == "pin.locked"


def test_pin_lockout_doubles(asha: StaffMember, laptop: Device) -> None:
    at = START
    with shop_context(asha.shop_id):
        for minutes in (1, 2, 4, 8):
            refused = five_wrong_tries(asha, laptop, at=at)
            assert refused.code == "pin.locked"
            # The wait, in seconds, for the app's "try again in..." (ADR-0032).
            assert refused.params == {"wait": minutes * 60}
            # The lock has ended exactly then, so the next five tries are heard.
            at += timedelta(minutes=minutes)


def test_pin_lock_stops_growing_at_an_hour(asha: StaffMember, laptop: Device) -> None:
    at = START
    waits = []
    with shop_context(asha.shop_id):
        for _ in range(8):
            params = five_wrong_tries(asha, laptop, at=at).params or {}
            waits.append(params["wait"] // 60)
            at += timedelta(seconds=params["wait"])
    assert waits == [1, 2, 4, 8, 16, 32, 60, 60]


def test_locked_person_is_refused_even_with_the_right_pin(asha: StaffMember, laptop: Device) -> None:
    # 0.2 seconds before the lock ends, and the wait is still a whole second, never 0. The PIN isn't checked: a locked
    # person costs the server no memory, however many tries are sent.
    just_before_the_end = START + timedelta(seconds=59, milliseconds=800)
    with shop_context(asha.shop_id):
        five_wrong_tries(asha, laptop, at=START)
        with (
            mock.patch("apps.people.services.pin_matches") as check,
            pytest.raises(ValidationError) as refused,
        ):
            check_pin(asha, laptop, PIN, at=just_before_the_end)
    assert refused.value.code == "pin.locked"
    assert refused.value.params == {"wait": 1}
    check.assert_not_called()


def test_right_pin_clears_the_lock(asha: StaffMember, laptop: Device) -> None:
    with shop_context(asha.shop_id):
        # The count: four wrong tries, the right one, and four more lock nobody.
        for _ in range(4):
            with pytest.raises(ValidationError):
                check_pin(asha, laptop, WRONG, at=START)
        check_pin(asha, laptop, PIN, at=START)
        for _ in range(4):
            with pytest.raises(ValidationError) as refused:
                check_pin(asha, laptop, WRONG, at=START)
        assert refused.value.code == "pin.wrong"
        check_pin(asha, laptop, PIN, at=START)

        # The wait: a first lock, the right PIN once it ends, and the next lock is one minute again, not two.
        five_wrong_tries(asha, laptop, at=START)
        check_pin(asha, laptop, PIN, at=START + timedelta(minutes=1))
        assert five_wrong_tries(asha, laptop, at=START + timedelta(minutes=2)).params == {"wait": 60}


def test_new_pin_lifts_the_lock(asha: StaffMember, laptop: Device) -> None:
    # A manager gives her a new PIN while she waits, on the same minute.
    with shop_context(asha.shop_id):
        five_wrong_tries(asha, laptop, at=START)
        renewed = set_pin(asha, NEW_PIN, by=None)
        check_pin(renewed, laptop, NEW_PIN, at=START)
        # And the wait starts over too.
        assert five_wrong_tries(renewed, laptop, at=START).params == {"wait": 60}


def test_lock_is_per_person_per_device(
    asha: StaffMember, juma: StaffMember, laptop: Device, manager: StaffMember, side_a: Side
) -> None:
    other_laptop = a_device(manager, side_a, "Laptop ya Vyakula")
    with shop_context(asha.shop_id):
        five_wrong_tries(asha, laptop, at=START)
        # Juma isn't locked: someone can't shut a whole laptop by locking one name.
        check_pin(juma, laptop, PIN, at=START)
        # Asha isn't locked on another laptop.
        check_pin(asha, other_laptop, PIN, at=START)


def test_person_with_no_pin_gets_the_same_answers(staff_a: StaffMember, laptop: Device) -> None:
    # Told apart from a wrong PIN, these answers would show anyone at the counter who has no PIN yet (03 §5.9).
    with shop_context(staff_a.shop_id):
        for _ in range(4):
            with pytest.raises(ValidationError) as refused:
                check_pin(staff_a, laptop, PIN, at=START)
            assert refused.value.code == "pin.wrong"
        with pytest.raises(ValidationError) as refused:
            check_pin(staff_a, laptop, PIN, at=START)
    assert refused.value.code == "pin.locked"


def test_person_of_another_shop_is_refused(staff_b: StaffMember, laptop: Device) -> None:
    # T1. The login reads a person through the guard, so it can never hand this over: the service's own check, as every
    # service has, for a bug in the calling code.
    with shop_context(laptop.shop_id), pytest.raises(ValidationError) as refused:
        check_pin(staff_b, laptop, PIN, at=START)
    assert refused.value.code == "staff.other_shop"


@pytest.mark.django_db(transaction=True)
def test_tries_sent_at_once_cannot_pass_five(asha: StaffMember, laptop: Device) -> None:
    # Twelve tries at the same moment, each on its own database connection, as twelve requests are. A check that came
    # before the count would let all twelve through: each would read "no wrong tries yet". So each one counts first,
    # holding the row's lock, and only then checks.
    checked: list[str] = []

    def counted(pin: str, pin_hash: str) -> bool:
        checked.append(pin)
        return pin_matches(pin, pin_hash)

    def one_try() -> None:
        with shop_context(asha.shop_id):
            check_pin(asha, laptop, WRONG, at=START)

    with mock.patch("apps.people.services.pin_matches", counted):
        tries = [in_another_transaction(one_try) for _ in range(12)]
        for thread, _ in tries:
            thread.join()

    refusals = [ended[0] for _, ended in tries]
    assert all(isinstance(refusal, ValidationError) for refusal in refusals), refusals
    # Four wrong; then the fifth, which locks, and seven that find the lock.
    assert sorted(refusal.code for refusal in refusals) == ["pin.locked"] * 8 + ["pin.wrong"] * 4  # type: ignore[attr-defined]
    assert len(checked) == 5


@pytest.mark.parametrize("numbers", [{"wrong_tries": 5}, {"next_lock_minutes": 0}, {"next_lock_minutes": 61}])
def test_database_refuses_impossible_numbers(asha: StaffMember, laptop: Device, numbers: dict[str, int]) -> None:
    # The database is the last guard (03 §5.6): even an update() that skips the service can't store these.
    with shop_context(asha.shop_id):
        row = PinLock.objects.create(shop_id=asha.shop_id, staff=asha, device=laptop)
        with pytest.raises(IntegrityError), transaction.atomic():
            PinLock.objects.filter(pk=row.pk).update(**numbers)


def test_one_row_per_person_per_device(asha: StaffMember, laptop: Device) -> None:
    # Two rows would be two counts, and each would let five more tries through.
    with shop_context(asha.shop_id):
        PinLock.objects.create(shop_id=asha.shop_id, staff=asha, device=laptop)
        with pytest.raises(IntegrityError), transaction.atomic():
            PinLock.objects.create(shop_id=asha.shop_id, staff=asha, device=laptop)
