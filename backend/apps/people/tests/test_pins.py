"""apps/people/tests/test_pins.py — the PIN rules (03 §5.9).

A PIN is 4 digits, so only 10,000 exist. Two walls keep them safe when someone copies the database:
1. The pepper: a server secret, kept outside the database, is mixed into the PIN before hashing. With
   the database alone, trying all 10,000 PINs matches nothing.
2. Argon2, a hash that is slow on purpose: even with the secret, every guess costs time and memory.
Easy PINs (1234, four of a kind) are refused, because a coworker would try them first. A person who has
left gets no PIN.

The check itself costs the same whoever is asked (AUTH-4): a set amount of memory, whether the person has a PIN or not,
so the time an answer takes says nothing about them, and a damaged hash lets nobody in.
"""

from unittest import mock

import pytest
from django.contrib.auth.hashers import Argon2PasswordHasher
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone
from django.views.debug import ExceptionReporter

from apps.core.tenancy import shop_context
from apps.people.models import StaffMember, User
from apps.people.pins import _hasher, _peppered, hash_pin, pin_hash_is_old, pin_matches
from apps.people.services import add_staff, mark_left, set_pin
from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

# Fake data only: the repo is public (03 §10).
PIN = "4829"
# How a hash made today names its cost: 19 MiB, 2 passes, 1 lane (apps/people/hashers.py).
TODAYS_COST = "$m=19456,t=2,p=1$"


@pytest.fixture
def asha(shop_a: Shop) -> StaffMember:
    user = User.objects.create_user(full_name="Asha Demo")
    with shop_context(shop_a):
        return add_staff(shop=shop_a, user=user, display_name="Asha", by=None)


@pytest.mark.parametrize(
    ("pin", "code"),
    [
        # Too easy: the first PINs anyone tries.
        ("1234", "pin.too_easy"),
        ("0000", "pin.too_easy"),
        ("1111", "pin.too_easy"),
        ("7777", "pin.too_easy"),
        # Not exactly 4 digits.
        ("123", "pin.not_four_digits"),
        ("12345", "pin.not_four_digits"),
        ("12a4", "pin.not_four_digits"),
        ("", "pin.not_four_digits"),
    ],
)
def test_weak_pin_refused(asha: StaffMember, shop_a: Shop, pin: str, code: str) -> None:
    with shop_context(shop_a):
        with pytest.raises(ValidationError) as refused:
            set_pin(asha, pin, by=None)
        asha.refresh_from_db()

    assert refused.value.code == code
    # Nothing was stored: she still has no PIN.
    assert asha.pin_hash == ""


def test_pin_stored_hashed(asha: StaffMember, shop_a: Shop) -> None:
    before = timezone.now()
    with shop_context(shop_a):
        set_pin(asha, PIN, by=None)
        asha.refresh_from_db()

    # Never as typed: the database holds only the Argon2 hash.
    assert asha.pin_hash != PIN
    assert asha.pin_hash.startswith("argon2$")
    assert pin_matches(PIN, asha.pin_hash)
    assert not pin_matches("4830", asha.pin_hash)
    # Devices compare this time with their own copy and drop an old offline check value (03 §5.9).
    assert asha.pin_changed_at is not None
    assert asha.pin_changed_at >= before


def test_pin_check_needs_pepper(asha: StaffMember, shop_a: Shop) -> None:
    with shop_context(shop_a):
        set_pin(asha, PIN, by=None)
        asha.refresh_from_db()

    # Wall 1. A thief with a copy of the database has the hash but not the server's secret, and Argon2
    # alone on the right PIN doesn't match: the secret was mixed in before hashing.
    assert not Argon2PasswordHasher().verify(PIN, asha.pin_hash)
    # A server with another secret can't check it either: the secret is part of every PIN hash.
    with override_settings(PIN_PEPPER="another-secret"):
        assert not pin_matches(PIN, asha.pin_hash)
    # With the right secret, the right PIN matches.
    assert pin_matches(PIN, asha.pin_hash)


def test_left_staff_cannot_get_pin(asha: StaffMember, shop_a: Shop) -> None:
    with shop_context(shop_a):
        mark_left(asha, left_on=asha.started_on, by=None, reason="Moved to another town")
        with pytest.raises(ValidationError) as refused:
            set_pin(asha, PIN, by=None)
        asha.refresh_from_db()

    assert refused.value.code == "staff.left"
    assert asha.pin_hash == ""


def test_pin_cost_is_set_on_purpose(asha: StaffMember, shop_a: Shop) -> None:
    # Django's default is 100 MiB a check: two at once would take 200 MiB of the demo's 512 MB. Ours is the same as a
    # password's (apps/people/hashers.py): 19 MiB, 2 passes, 1 lane.
    with shop_context(shop_a):
        set_pin(asha, PIN, by=None)
        asha.refresh_from_db()

    assert TODAYS_COST in asha.pin_hash


def test_old_pin_hash_still_checks_and_is_seen_as_old() -> None:
    # A PIN hashed before AUTH-4, at Django's default cost. Its owner must still get in, and the login then moves it
    # to today's cost.
    django_default = Argon2PasswordHasher()
    old = django_default.encode(_peppered(PIN), django_default.salt())

    assert pin_matches(PIN, old)
    assert pin_hash_is_old(old)
    assert not pin_hash_is_old(hash_pin(PIN))


def test_no_pin_takes_as_long_as_a_wrong_one(monkeypatch: pytest.MonkeyPatch) -> None:
    # A quick "no" would show anyone at the counter who has no PIN yet. Counted, not timed, as a clock would fail on a
    # busy machine: each answer runs exactly one full check, at today's cost.
    checked: list[str] = []
    real_check = _hasher.verify

    def counted(password: str, encoded: str) -> bool:
        checked.append(encoded)
        return real_check(password, encoded)

    monkeypatch.setattr(_hasher, "verify", counted)

    assert not pin_matches(PIN, "")
    assert not pin_matches("4830", hash_pin(PIN))
    assert len(checked) == 2
    assert all(TODAYS_COST in encoded for encoded in checked)


@pytest.mark.parametrize("damaged", ["not-a-hash", "md5$abc$def", "argon2$broken"])
def test_broken_pin_hash_never_matches(damaged: str, caplog: pytest.LogCaptureFixture) -> None:
    # Nobody gets in, nothing crashes, and the log says so, since this person can't log in until they get a new PIN.
    # The log never holds the hash.
    assert not pin_matches(PIN, damaged)
    assert "damaged" in caplog.text
    assert damaged not in caplog.text


def test_pin_stays_out_of_error_reports(asha: StaffMember, shop_a: Shop) -> None:
    # Django's error report lists each function's variables when something fails. The PIN shows as stars.
    crashing = mock.patch("apps.people.services.hash_pin", side_effect=RuntimeError("no memory"))
    with crashing, shop_context(shop_a), pytest.raises(RuntimeError) as crash:
        set_pin(asha, PIN, by=None)
    frames = ExceptionReporter(None, crash.type, crash.value, crash.tb).get_traceback_frames()
    [frame] = [frame for frame in frames if frame["function"] == "set_pin"]
    assert set(str(dict(frame["vars"])["pin"])) == {"*"}
