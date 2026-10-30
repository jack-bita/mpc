"""apps/people/device_keys.py — what a pairing code and a device key look like (AUTH-1, 03 §5.9).

A pairing code is the short name a new device shows on its screen, for a manager to type on their own phone:
8 characters, valid 10 minutes, used once. A device key is the device's secret, kept in an HttpOnly cookie
(AUTH-2): 32 random bytes, which the server keeps only as their SHA-256 hash. The tables (apps/people/models.py)
build their database rules from these shapes.
"""

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
