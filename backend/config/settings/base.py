"""config/settings/base.py — the settings every environment shares.

It owns the helpers that read environment variables and every setting that is the same on Jack's laptop,
in tests and on the server. dev.py, test.py and prod.py start from this file and change only what differs.

Secrets never live in this repo, which is public (03 §10). They come from environment variables:
on a laptop from a gitignored `.env` file (`uv run --env-file .env …`, REPO-4), on the server from its
root-only `.env` through Docker (03 §13).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

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
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# Off unless an environment turns it on: debug pages show code and settings to anyone who sees an error.
DEBUG = False

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    # Our domain apps, in layer order (ADR-0015; see apps/__init__.py).
    "apps.core",
    "apps.shops",
    "apps.people",
    "apps.control",
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
# triggers (03 §9, §11). The defaults fit the local PostgreSQL that REPO-4 runs in Docker; prod.py
# requires every value instead. Nothing connects in REPO-2, and no `migrate` before PPL-1 (ADR-0012).
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
