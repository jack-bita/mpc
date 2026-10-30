"""apps/people/device_keys.py — what a pairing code and a device key look like, and how they are made and kept
(AUTH-1, 03 §5.9).

A pairing code is the short name a new device shows on its screen, for a manager to type on their own phone:
8 characters, valid 10 minutes, used once. A device key is the device's secret, kept in an HttpOnly cookie
(AUTH-2): 32 random bytes, which the server keeps only as their SHA-256 hash. The tables (apps/people/models.py)
build their database rules from these shapes; the pairing services (apps/people/services.py) use the four helpers
at the bottom.

Both are drawn with `secrets`, Python's randomness for secrets, never `random`, whose next numbers can be worked out
from the ones before.
"""

import hashlib
import secrets
from datetime import timedelta

# The characters a code is drawn from: digits and capital letters, without the ones a person misreads from a
# screen or a phone's keyboard: 0 and O, 1, I and L. 31 characters, so 31^8 codes, about 850 billion: a guess
# within a code's 10 minutes is hopeless, and AUTH-2's throttle makes it slower still.
PAIRING_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
PAIRING_CODE_LENGTH = 8
# How long a code waits for a manager (03 §5.9): long enough to walk to the manager, short enough that a code read
# over a shoulder is soon worth nothing.
PAIRING_CODE_LIFETIME = timedelta(minutes=10)

# A SHA-256 hash, written in hexadecimal: 64 characters, 0-9 and a-f. The key itself, written in URL-safe
# characters, never has this shape, so a database rule on it refuses a key stored by mistake instead of its hash.
KEY_HASH_LENGTH = 64
KEY_HASH_SHAPE = r"^[0-9a-f]{64}$"

# The key's length in random bytes: 256 bits, more than anyone could ever guess.
KEY_BYTES = 32


def make_pairing_code() -> str:
    """A new code, 8 characters drawn at random from the alphabet above: "K7P2MXQ9"."""
    return "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def clean_typed_code(typed: str) -> str:
    """The code as a manager typed it, put back in the shape it is stored in. The screen shows it in two halves with a
    dash ("K7P2-MXQ9"), and a phone may type small letters or add a space: " k7p2-mxq9 " is "K7P2MXQ9"."""
    return "".join(typed.split()).replace("-", "").upper()


def make_device_key() -> str:
    """A new device's secret: 32 random bytes, written in 43 URL-safe characters, so it fits in a cookie as it is."""
    return secrets.token_urlsafe(KEY_BYTES)


def hash_device_key(key: str) -> str:
    """What the server keeps instead of the key: its SHA-256 hash, in 64 hexadecimal characters.

    A fast hash, not Argon2 as for PINs (Jack, AUTH-1; 03 §5.9). A slow hash protects a secret a person chose, which
    others can guess: a 4-digit PIN has only 10,000 values, so each guess must cost time. A key of 32 random bytes
    can't be guessed at any speed, so slowness would add nothing, and it would cost about 0.1 s and 100 MiB on every
    request AUTH-2 checks. No salt either, for the same reason, and so the same key always gives the same hash: a
    request finds its device by this hash in one index lookup."""
    return hashlib.sha256(key.encode()).hexdigest()
