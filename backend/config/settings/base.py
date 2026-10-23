"""config/settings/base.py — the settings every environment shares.

It owns the helpers that read environment variables and every setting that is the same on Jack's laptop,
in tests and on the server. dev.py, test.py and prod.py start from this file and change only what differs.

Secrets never live in this repo, which is public (03 §10). They come from environment variables:
on a laptop from the gitignored root `.env` (`uv run --env-file ../.env …`, REPO-4), on the server from its
root-only `.env` through Docker (03 §13).
"""

import os
from pathlib import Path

import django_stubs_ext
from django.core.exceptions import ImproperlyConfigured

# Lets Django's classes take a type in brackets (`UserAdmin[User]`) at run time, as mypy's strict mode
# asks for (django-stubs' own advice). It changes nothing else.
django_stubs_ext.monkeypatch()

# backend/ — the folder that holds manage.py.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    """Read one environment variable. With no default, a missing or empty one stops Django at startup.

    Failing at startup is the point: a server that starts without its secret key or database
    password would fail later, in the middle of a sale, with a far less clear error.
    An empty value counts as missing too: `DB_PASSWORD=` in a `.env` file is a mistake, not a choice.
    """
    value = os.environ.get(name, "")
    if value:
        return value
    if default is None:
        raise ImproperlyConfigured(f"The environment variable {name} is not set.")
    return default


def env_list(name: str, default: str | None = None) -> list[str]:
    """Read a comma-separated environment variable, e.g. DJANGO_ALLOWED_HOSTS=demo.example,localhost."""
    items = [item.strip() for item in env(name, default).split(",") if item.strip()]
    # A required list of only commas is as good as missing: with no allowed hosts, prod would start
    # and then refuse every request, instead of stopping at startup with a clear message.
    if default is None and not items:
        raise ImproperlyConfigured(f"The environment variable {name} has no values.")
    return items


# Off unless an environment turns it on: debug pages show code and settings to anyone who sees an error.
DEBUG = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # Our domain apps, in layer order (ADR-0035; see apps/__init__.py).
    "apps.core",
    "apps.control",
    "apps.shops",
    "apps.people",
    "apps.catalog",
    "apps.contacts",
    "apps.inventory",
    "apps.money",
    "apps.sales",
    "apps.services",
    "apps.staffpay",
    "apps.sync",
    "apps.reports",
]

# The custom User (apps/people/models.py) replaces Django's own. Set before the first migration and
# never changed: Django can't swap its user model afterwards (ADR-0012).
AUTH_USER_MODEL = "people.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL only — never SQLite, not even in tests: we rely on its exact decimals, constraints and
# triggers (03 §9, §11). The defaults are for a local PostgreSQL; on a laptop it runs in Docker
# (compose.dev.yml) and the root `.env` gives its password and port. prod.py requires every value
# instead. No `migrate` on any database before PPL-1 (ADR-0012).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "mpc"),
        "USER": env("DB_USER", "mpc"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
    }
}

# Django's own tables (sessions, permissions) get big integer ids. Our models use UUIDv7 ids from the
# base classes in `core` instead (CORE-1), so this applies only to those infrastructure tables.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Screen text lives in the app and the API sends codes (ADR-0032), so this only affects Django's own pages.
LANGUAGE_CODE = "en-us"
USE_I18N = True

# Every time is stored in UTC (03 §9). A shop's business date uses its own time zone
# (Africa/Dar_es_Salaam), worked out per shop — never from this server-wide setting.
TIME_ZONE = "UTC"
USE_TZ = True

STATIC_URL = "static/"

# The version this process runs. A deploy builds the image with its git commit as the version
# (backend/Dockerfile, `make check-image APP_VERSION=<commit>`); every other build, and a laptop, say "dev".
# The health check shows it, so after a deploy the smoke test can tell whether the new version is
# answering or the old one still is (OPS-2).
APP_VERSION = env("APP_VERSION", "dev")
