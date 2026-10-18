"""config/settings/test.py — settings for pytest (pytest-django loads it; see pyproject.toml).

Fixed values, so a test never depends on the machine it runs on. pytest-django creates its own
`test_<DB_NAME>` database for tests that need one, so the development data is never touched.
"""

from .base import *  # noqa: F403 — start from the shared settings, then change what differs.

SECRET_KEY = "test-only-not-a-secret"

# A deliberately weak, fast hasher: tests create many users, and real hashing (Argon2) is slow on purpose.
# Only tests use it; the other environments keep strong hashing.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Emails stay in memory, where a test can read them (django.core.mail.outbox).
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
}
