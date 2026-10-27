"""apps/people/pins.py — a staff member's PIN: which PINs are allowed, and how one is stored and checked
(03 §5.9).

A PIN is never stored as typed. It is mixed with a server secret (the pepper, settings.PIN_PEPPER), then
hashed with Argon2:

    stored = Argon2( HMAC-SHA256(pepper, pin) )

Two walls stand against a copy of the database. Without the pepper, trying all 10,000 PINs matches
nothing; and even with it, Argon2 makes every guess slow. The services (apps/people/services.py) set a
PIN; PIN login (AUTH-4) checks one.
"""

import hashlib
import hmac
import re

from django.conf import settings
from django.contrib.auth.hashers import Argon2PasswordHasher
from django.core.exceptions import ValidationError

# Exactly four of the digits 0–9. [0-9], not \d: \d also matches other scripts' digits (Arabic "٤"),
# which no PIN pad types.
_FOUR_DIGITS = re.compile(r"[0-9]{4}")
# The first PIN anyone tries (03 §5.9). Four of a kind (0000, 1111...) is checked below.
_TOO_EASY = {"1234"}

# Django's own Argon2 hasher, used directly instead of through PASSWORD_HASHERS: the test settings swap
# that list for a fast, weak hasher, and PINs must be hashed for real everywhere. Its cost settings are
# written into each hash, so a later change still checks the old ones.
_hasher = Argon2PasswordHasher()


def check_pin_strength(pin: str) -> None:
    """Refuse a PIN that isn't 4 digits, or that a coworker would guess first."""
    if not _FOUR_DIGITS.fullmatch(pin):
        raise ValidationError("A PIN is exactly 4 digits.", code="pin.not_four_digits")
    if pin in _TOO_EASY or len(set(pin)) == 1:
        raise ValidationError("This PIN is too easy to guess.", code="pin.too_easy")


def _peppered(pin: str) -> str:
    # HMAC-SHA256 with the pepper as its key: a fixed text that only someone holding the pepper can make
    # from a PIN. Read from settings on every call, so a server with another pepper gets another result.
    return hmac.new(settings.PIN_PEPPER.encode(), pin.encode(), hashlib.sha256).hexdigest()


def hash_pin(pin: str) -> str:
    """The value to store: Argon2 of the peppered PIN, with a fresh random salt each time."""
    return _hasher.encode(_peppered(pin), _hasher.salt())


def pin_matches(pin: str, pin_hash: str) -> bool:
    """True if `pin` is the PIN behind `pin_hash`. False for an empty hash (no PIN set)."""
    if not pin_hash:
        return False
    return _hasher.verify(_peppered(pin), pin_hash)
