"""config/settings/dev.py — settings for Jack's laptop. `manage.py` uses this file unless told otherwise.

Debug pages are on, and the values have safe local defaults: on a fresh clone with no `.env`, `manage.py check`
and the tests already run. The local database runs in Docker (`compose.dev.yml`); the root `.env` gives its
password and port (REPO-4).
"""

from .base import *  # noqa: F403 — start from the shared settings, then change what differs.
from .base import env, env_list

DEBUG = True

# Only for this laptop: a key anyone can read signs nothing that matters. prod.py has no default.
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-not-a-secret")

# The secret mixed into every PIN before hashing (prod.py explains it). Laptop PINs protect nothing real.
PIN_PEPPER = env("PIN_PEPPER", "dev-only-not-a-secret")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Emails (password resets, later) are printed in the terminal instead of being sent.
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"},
}
