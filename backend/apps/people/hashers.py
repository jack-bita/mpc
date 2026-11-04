"""apps/people/hashers.py — how hard a person's password is hashed (AUTH-3; 03 §10).

A password is stored as Argon2, which needs a lot of memory for every guess. That is what makes a stolen copy of the
database slow to attack: an attacker's graphics cards are fast, but have little memory for each of their many workers.

This file owns the cost. Django's default is about 100 MiB for each check, which doesn't fit the demo: its server has
512 MB, shared by two workers (backend/Dockerfile), so two logins at once would take 200 MiB, and a flood of guesses
could run it out of memory, stopping the shop's work. So we set it on purpose, to OWASP's published minimum for
Argon2id: 19 MiB, 2 passes, 1 lane. About 40 ms on the laptop.

A stored hash names the cost it was made with. If this cost changes later, each person's hash moves to the new one at
their next login, with no migration and nobody locked out.

PINs don't come through here: they are hashed directly, with a secret added (apps/people/pins.py), and AUTH-4 sets
their cost.
"""

from django.contrib.auth.hashers import Argon2PasswordHasher


class ShopArgon2PasswordHasher(Argon2PasswordHasher):
    # Keeps Django's algorithm name, `argon2`, so hashes from either class are read the same way, and one made at
    # another cost is recognised as out of date rather than refused.
    memory_cost = 19456  # in KiB: 19 MiB
    time_cost = 2
    parallelism = 1
