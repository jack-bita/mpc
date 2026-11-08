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
    # PostgreSQL's own column kinds, such as a role's list of codes (apps/people/models.py). Part of Django
    # itself, not a new package: we run on PostgreSQL only (ADR-0023).
    "django.contrib.postgres",
    "rest_framework",
    # Writes the API's OpenAPI description from the routes (ADR-0025, apps/core/api/schema.py).
    "drf_spectacular",
    # django-allauth: the owner's and managers' password login (ADR-0038). `account` is the login itself, with its
    # own table of email addresses; `headless` answers it as JSON at /_allauth/ for our own app, which draws its own
    # screens (UI-5), so allauth's HTML pages stay off (HEADLESS_ONLY, below).
    "allauth",
    "allauth.account",
    "allauth.headless",
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
    # The demo shop's seed (DATA-1): not a domain app, so on a layer of its own above them all (03 §5.1).
    "apps.demo",
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
    # allauth's own: it keeps a login's steps together across requests, and refuses to start without it.
    "allauth.account.middleware.AccountMiddleware",
]

# Who may check a password: allauth's checker alone, for every login, the admin's too (it takes the admin form's email
# as well as our own login by email or phone, ADR-0038). Never two: Django tries each in turn until one says yes, so a
# wrong password would be hashed twice and a right one once. The answer's time would then show a right password, and
# the admin's login has no limit, so a stranger could try passwords there past every limit we count. Ours is allauth's,
# with its variables hidden from error reports (apps/people/accounts.py). A session names its checker, so a person's
# session ends once when this name changes.
AUTHENTICATION_BACKENDS = ["apps.people.accounts.PasswordBackend"]

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

# How a password is stored: the first hashes every new one (Argon2, at the cost in apps/people/hashers.py). The rest can
# only read older hashes, which move to the first at that person's next login: every password set before AUTH-3 is
# PBKDF2, Django's default, and must not lock its owner out.
PASSWORD_HASHERS = [
    "apps.people.hashers.ShopArgon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    # A password too much like the person's own details is refused. Django's list names a username, first and last
    # names, which our User doesn't have (PPL-1): it is told ours instead, so "Baba Mfano" can't pick "babamfano", nor
    # their phone number.
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("full_name", "email", "phone")},
    },
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

# --- Django REST framework: how every API view behaves, unless a view says otherwise (03 §5.10).
REST_FRAMEWORK = {
    # Every refusal leaves in the API's one error shape, with a code the app translates (ADR-0032).
    "EXCEPTION_HANDLER": "apps.core.api.errors.handle_error",
    # How the office routes log in: Django's session cookie, read as the person's staff member at their shop, checked
    # on every visit (apps/people/api/staff_session.py; 03 §5.9, ADR-0038). Only the session: a device's key logs in on
    # the device routes alone, which name their own login (DeviceView, apps/people/api/base.py), so a device's cookie
    # opens no office route (AUTH-2, CORE-6).
    # DRF's default also accepts a password sent with every request (Basic), which nothing here uses.
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.people.api.staff_session.StaffSessionAuthentication"],
    # Closed unless a view says otherwise: a route open to everyone, like the health check, says so itself.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # JSON only, in and out (03 §5.10). DRF's browsable HTML pages would also build a form for each route,
    # after the view has returned and closed the visit's shop (apps/core/api/base.py), so they would fail.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Every list comes in pages, by cursor (apps/core/api/pagination.py). 50 rows *(default)*: a few phone
    # screens, light enough for a slow connection at the shop.
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.pagination.CursorPage",
    "PAGE_SIZE": 50,
    # The test client sends JSON, as the app does.
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # How drf-spectacular describes each route: drf-spectacular's own way, plus what our creates and edits
    # take (apps/core/api/schema.py).
    "DEFAULT_SCHEMA_CLASS": "apps.core.api.schema.RouteSchema",
    # Pairing's two limits, an hour each *(default)* (AUTH-5, apps/people/api/throttles.py): starts per caller's
    # network, which every device of a shop shares (its one IPv4 address, or its IPv6 /64), so a few devices an hour
    # is plenty; a manager's tries of a code per person, a wrong code included. No route is slowed down unless it names
    # its limit: a device's own calls never are. And a device's tries of a PIN, each a full check of 19 MiB (AUTH-4).
    "DEFAULT_THROTTLE_RATES": {"pairing.start": "10/hour", "pairing.confirm": "10/hour", "pin.login": "30/minute"},
    # How many proxies stand in front of Django and add the caller's address to X-Forwarded-For: Caddy, 1, on a
    # laptop and on the real server (03 §12). DRF reads the address that many entries from the end; the entries
    # before them are whatever the caller wrote, so without this a phone could claim any address and never be slowed
    # down. The demo reads Cloudflare's header instead (CLIENT_IP_HEADER, below).
    "NUM_PROXIES": int(env("NUM_PROXIES", "1")),
}

# The header a proxy in front writes the caller's address in, over any the caller sent, when there is one to trust:
# on the demo, Cloudflare's `CF-Connecting-IP`, Render's own advice, since Render puts two proxies in front and
# X-Forwarded-For's count is unsure there (render.yaml). Empty elsewhere: X-Forwarded-For and NUM_PROXIES above.
# Never set it where that proxy isn't in front: a caller could then write the header themselves.
CLIENT_IP_HEADER = env("CLIENT_IP_HEADER", "")

# The caches: Django's database cache, tables in PostgreSQL, shared by every server worker, so a limit counts a
# caller's requests whichever worker answers them (ADR-0023: PostgreSQL only, no Redis). Their tables are made by
# `manage.py createcachetable`, not by a migration: start-demo.sh runs it on the demo, `make migrate` on a laptop, and
# the test database gets them by itself. 10,000 entries each *(default)*, one per caller and limit, far above Django's
# 300.
# One table per limit: past its 10,000, a table loses a third of its rows, picked by their keys' ABC order, not their
# age, so in one shared table a flood of one kind would clear every other kind's counts, the managers' among the first
# (apps/people/api/throttles.py). Apart, a flood clears only its own kind.
# `default` is the login limits' own: allauth counts only in `default`, with no setting to change it (AUTH-3). Nothing
# else may count there. 100,000 entries *(default)*: a guesser's own count sits in this table beside a flood's, so the
# table is sized to be dear to fill, and a login's row counts for 5 minutes at most, so filling it takes about 2,000
# networks at once. A row past its time stays until it is read again or the table fills: OPS-7 prunes them. A database
# made before AUTH-3 keeps an empty, unused table, `django_cache`.
_DATABASE_CACHE = {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "OPTIONS": {"MAX_ENTRIES": 10_000}}
CACHES = {
    "default": {**_DATABASE_CACHE, "LOCATION": "throttle_login", "OPTIONS": {"MAX_ENTRIES": 100_000}},
    "pairing_start": {**_DATABASE_CACHE, "LOCATION": "throttle_pairing_start"},
    "pairing_confirm": {**_DATABASE_CACHE, "LOCATION": "throttle_pairing_confirm"},
    "pin_login": {**_DATABASE_CACHE, "LOCATION": "throttle_pin_login"},
}

# --- The API's description, /api/schema/, and its docs page, /api/docs/ (03 §5.10, ADR-0025).
SPECTACULAR_SETTINGS = {
    "TITLE": "MPC API",
    "DESCRIPTION": (
        "The routes of the MPC shop system. Every refusal has one shape: "
        '{"code", "message", "fields", "params"}; the app translates the code.'
    ),
    # The description's own version, not the deploy's commit: CI compares the committed description with the
    # code (test_committed_schema_matches_the_code, UI-2), and a version that changed with every commit would
    # never match.
    "VERSION": "1",
    # The description doesn't list its own route.
    "SERVE_INCLUDE_SCHEMA": False,
    # What is left out before a route's first part is read: /api/, and the version. The docs page then
    # groups routes by app ("shops", not "v1"), and the app's generated client names them so
    # (shops_sides_list).
    "SCHEMA_PATH_PREFIX": r"/api(/v[0-9]+)?",
    # Separate shapes for what a route takes and what it answers (SideCreateRequest beside Side), so a field
    # the server fills, like `created_at`, is never one the app's types make it send.
    "COMPONENT_SPLIT_REQUEST": True,
    # An edit's fields keep their own "required": every edit sends the `version` it read. Otherwise
    # drf-spectacular marks every field of a PATCH optional.
    "COMPONENT_SPLIT_PATCH": False,
    # A field's fixed choices are named after their own type, not after the field: drf-spectacular would call a
    # device's status StatusEnum, and rename it, with a warning, once another table shows a `status` of its own. The
    # app's generated types keep these names (UI-2).
    "ENUM_NAME_OVERRIDES": {"DeviceStatusEnum": "apps.people.models.DeviceStatus"},
    # The docs page's own code comes from a CDN: one exact version, never "latest", so the code that runs on
    # our address can't change under us. Only on the demo and a laptop: the real server keeps it closed.
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.0",
    "SWAGGER_UI_FAVICON_HREF": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.0/favicon-32x32.png",
}

# --- django-allauth: the owner's and managers' password login (03 §5.9, ADR-0038), at /_allauth/browser/v1/.
# Our app draws its own screens (UI-5), so allauth answers only its JSON API, for a browser, with Django's session
# cookie (ADR-0038): its HTML pages are off, and so are its tokens for mobile apps, which we don't have.
HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
# How a person names themselves at login: their email, or their phone, which most of the shop's people have instead
# (ADR-0038). allauth finds a person by phone through our adapter (apps/people/accounts.py).
ACCOUNT_LOGIN_METHODS = {"email", "phone"}
# allauth's check of a phone by an SMS code, off: the owner typed every phone face to face, and an SMS costs money
# (ADR-0038).
ACCOUNT_PHONE_VERIFICATION_ENABLED = False
# No username: our User has none (PPL-1).
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
# The fields of allauth's sign-up form. Nobody signs up, as our adapter refuses it (apps/people/accounts.py), but
# allauth checks at start-up that this list fits the login methods above.
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
# An email is typed by the owner, who knows the person, never by a stranger signing up: nobody is sent a link to
# confirm it, which most of the shop's people couldn't open anyway.
ACCOUNT_EMAIL_VERIFICATION = "none"
# What allauth asks of our people: sign-up closed, the login by phone, and what its limits count by
# (apps/people/accounts.py).
ACCOUNT_ADAPTER = "apps.people.accounts.AccountAdapter"
# A reset link opens the app (UI-5), at this path on the address the request came to. The key sits after the #, which a
# browser never sends to a server: so it stays out of Caddy's and Django's logs, and out of any Referer header. A static
# app (ADR-0016) can read it there with no route of its own for each key. The path ends in a slash, as the app's page
# does (trailingSlash, frontend/next.config.ts): it opens that page itself, rather than leaning on the server's redirect
# from /password-reset to carry the key along.
HEADLESS_FRONTEND_URLS = {"account_reset_password_from_key": "/password-reset/#{key}"}
# Asked to reset an email nobody here has, allauth would send that address a note saying so: anyone could make us send
# mail to any stranger. The answer to the asker stays the same either way, so nobody learns who has an account.
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
# Django's own reset key, not allauth's default. allauth's writes the person's email into its own table of addresses
# whenever a link is made or checked, which anyone can cause with no login, and its login and reset both trust that
# table. A copy there outlives a change of email: an old mailbox would still get working links, and a reused address
# would open its old owner's account, perhaps at another shop. Our User holds the email and the table stays empty.
# Django's key is made from the User's email too, so a change of email also ends a link already sent.
ACCOUNT_PASSWORD_RESET_TOKEN_GENERATOR = "django.contrib.auth.tokens.PasswordResetTokenGenerator"
# 3 reset emails an hour to one address. allauth's default, 5 a minute, would let a stranger who knows the address send
# 7,200 a day. A stranger using these up can't keep the person out: each link goes to the person's own mailbox and
# works. allauth's limit per caller stays as it was. Its other limits keep their defaults.
ACCOUNT_RATE_LIMITS = {"reset_password": "20/m/ip,3/h/key"}
# A reset link works for an hour, not Django's 3 days: one left in a mailbox is a way in for whoever opens it later.
PASSWORD_RESET_TIMEOUT = 60 * 60

# Whether the description and the docs page are open (apps/core/api/schema.py). False: closed to everyone,
# the real server's rule. Off unless an environment turns it on: dev.py does, and the demo does (prod.py).
API_DOCS_PUBLIC = False

# The demo seed's sign (DATA-1, apps/demo/services.py): `manage.py seed_demo` wipes the database, so it runs only where
# DEMO_SEED=yes is set, the mark of a place that holds demo data alone. The real server never sets it, so the seed
# refuses there even before its first shop exists (Jack, 8 Nov 2026). Read here, in base.py, so every environment
# reads it the same way, and off unless that environment turns it on.
DEMO_SEED = env("DEMO_SEED", "no") == "yes"

# The version this process runs. A deploy builds the image with its git commit as the version
# (backend/Dockerfile, `make check-image APP_VERSION=<commit>`); every other build, and a laptop, say "dev".
# The health check shows it, so after a deploy the smoke test can tell whether the new version is
# answering or the old one still is (OPS-2).
APP_VERSION = env("APP_VERSION", "dev")
