"""apps/people/pins.py — a staff member's PIN: which PINs are allowed, and how one is stored and checked
(03 §5.9).

A PIN is never stored as typed. It is mixed with a server secret (the pepper, settings.PIN_PEPPER), then
hashed with Argon2:

    stored = Argon2( HMAC-SHA256(pepper, pin) )

Two walls stand against a copy of the database. Without the pepper, trying all 10,000 PINs matches
nothing; and even with it, Argon2 makes every guess slow. The services (apps/people/services.py) set a
PIN; PIN login (AUTH-4) checks one.
"""

import functools
import hashlib
import hmac
import logging
import re
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.views.decorators.debug import sensitive_variables

from apps.people.hashers import ShopArgon2PasswordHasher

logger = logging.getLogger(__name__)

# Exactly four of the digits 0–9. [0-9], not \d: \d also matches other scripts' digits (Arabic "٤"),
# which no PIN pad types.
_FOUR_DIGITS = re.compile(r"[0-9]{4}")
# The first PIN anyone tries (03 §5.9). Four of a kind (0000, 1111...) is checked below.
_TOO_EASY = {"1234"}

# Our own Argon2 class, the one passwords use (apps/people/hashers.py): 19 MiB a check, so two checks at once fit the
# demo's 512 MB. Used directly, not through PASSWORD_HASHERS: the test settings swap that list for a fast, weak hasher,
# and PINs must be hashed for real everywhere. Its cost is written into each hash, so a later change still checks the
# old ones.
_hasher = ShopArgon2PasswordHasher()


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


# Every variable shows as stars in Django's error reports, here and in everything these two call, as for a password
# (apps/people/services.py): the library at the bottom of the hash holds the PIN under names of its own.
@sensitive_variables()
def hash_pin(pin: str) -> str:
    """The value to store: Argon2 of the peppered PIN, with a fresh random salt each time."""
    return _hasher.encode(_peppered(pin), _hasher.salt())


@functools.cache
def _nobodys_hash() -> str:
    # What a person with no PIN is checked against, so their "no" takes as long as a wrong PIN's: a quick "no" would
    # show anyone at the counter who has no PIN yet. Made from random text, so no PIN ever matches it. Made once per
    # server worker, the first time it is needed.
    return _hasher.encode(secrets.token_hex(16), _hasher.salt())


@sensitive_variables()
def pin_matches(pin: str, pin_hash: str) -> bool:
    """True if `pin` is the PIN behind `pin_hash`. False for an empty hash (no PIN set) or a damaged one. Each answer
    costs one full check."""
    try:
        return _hasher.verify(_peppered(pin), pin_hash or _nobodys_hash())
    except ValueError, AssertionError:
        # A hash that isn't one: only a bug, or a hand edit of the database, could store it. Nobody gets in, and the log
        # says so, as this person can't log in until they get a new PIN. Django's own check raises these two. The log
        # never holds the hash. One more full check, so even this "no" takes as long.
        logger.error("A stored PIN hash is damaged: give this person a new PIN.")
        _hasher.verify(_peppered(pin), _nobodys_hash())
        return False


def pin_hash_is_old(pin_hash: str) -> bool:
    """True when this hash was made at another cost than today's. Only the login can fix it, as it alone holds the PIN
    itself, just checked: it hashes it again."""
    return _hasher.must_update(pin_hash)
