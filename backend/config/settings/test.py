"""config/settings/test.py — settings for pytest (pytest-django loads it; see pyproject.toml).

Fixed values, so a test never depends on the machine it runs on. pytest-django creates its own
`test_<DB_NAME>` database for tests that need one, so the development data is never touched.
"""

import tempfile

from .base import *  # noqa: F403 — start from the shared settings, then change what differs.
from .base import STORAGES

SECRET_KEY = "test-only-not-a-secret"

# The secret mixed into every PIN before hashing (prod.py explains it). The PIN tests change it to show
# that a stored PIN can't be checked without the right one.
PIN_PEPPER = "test-only-not-a-secret"

# A test-only app (backend/tests/probe/) whose tables let `core` test its base models before any real
# table builds on them. Only these settings install it, and they are for pytest, which builds its own
# test database: the dev and production settings never install it.
INSTALLED_APPS = [*INSTALLED_APPS, "tests.probe"]  # noqa: F405 — defined in .base, through the * above.

# Files the tests save go to a new, empty folder of this run's own, never into backend/files/, Jack's laptop's: a test
# then never finds a file another run left, and two runs at once never meet. Made once, as pytest loads these settings;
# the system's temporary folder is emptied by the system. A test of the demo's storage asks for it by name.
STORAGES = {
    **STORAGES,
    "default": {"BACKEND": "apps.core.storage.FolderStorage", "OPTIONS": {"location": tempfile.mkdtemp(prefix="mpc-")}},
}

# A deliberately weak, fast hasher: tests create many users, and real password hashing is slow on purpose.
# Only tests use it; the other environments keep strong hashing.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Emails stay in memory, where a test can read them (django.core.mail.outbox).
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
}
