"""config/settings/prod.py — settings for the real shop server and the demo. wsgi.py, asgi.py and the image use it.

Every secret is required here, with no default: if one is missing, Django refuses to start and names it.
On the real server the values come from its root-only `.env`, passed in by Docker (03 §13, ADR-0027);
on the demo, from Render (render.yaml).
"""

from wsgiref.headers import Headers

from .base import *  # noqa: F403 — start from the shared settings, then change what differs.
from .base import BASE_DIR, DATABASES, MIDDLEWARE, env, env_list

SECRET_KEY = env("DJANGO_SECRET_KEY")

# Mixed into every PIN before hashing (apps/people/pins.py, 03 §5.9), so a copy of the database alone
# reveals no PIN. Its own secret, not SECRET_KEY: that key may be changed one day, and a changed
# pepper makes every PIN stop working. If it is ever lost, only the PINs go: each person gets a new one.
PIN_PEPPER = env("PIN_PEPPER")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

# Whether the API's description and docs page are open (base.py). The demo sets "true" (render.yaml): the API
# is part of what it shows. The real server leaves it out, so they are closed there, to everyone. Any value
# other than "true", a typo included, keeps them closed.
API_DOCS_PUBLIC = env("API_DOCS_PUBLIC", "false") == "true"

DATABASES["default"].update(
    NAME=env("DB_NAME"),
    USER=env("DB_USER"),
    PASSWORD=env("DB_PASSWORD"),
    HOST=env("DB_HOST"),
    PORT=env("DB_PORT", "5432"),
)

# A proxy sits in front of Django and talks HTTPS with the browser: Caddy on the real server (03 §13),
# Render's proxy on the demo (render.yaml). It tells Django the original request was HTTPS with this
# header; without it Django would think every request is plain HTTP.
# Safe only because in each place the proxy is the one way in, and no plain HTTP gets past it: Caddy
# overwrites the header itself; Render's proxy redirects every http:// request to https:// before it
# reaches Django, which scripts/smoke_demo.sh checks after each deploy. So every request Django sees came
# over HTTPS, and a header a client forges can't make plain HTTP pass for HTTPS. Django's own port must
# never be reachable from outside: anyone who reached it directly could fake "https".
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies only travel over HTTPS, so nobody on the shop's Wi-Fi can read a session (03 §10).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# `check --deploy` still warns about the HTTPS redirect (security.W008) and HSTS (security.W004).
# Both are left to the proxy: on the real server Caddy owns HTTPS and the strict headers (03 §10, OPS-5);
# on the demo, Render's proxy redirects every plain HTTP request to HTTPS before it reaches Django.

# --- Files. In the image, Django serves them itself through WhiteNoise, so one container answers
# everything from one address: the demo's setup (03 §13, OPS-1). Only here, not in base.py: on a laptop
# runserver serves the admin's files and Next.js (behind Caddy) the app's, and the tests serve none.
# WhiteNoise answers a request for a file before Django's URL routing, and before the middleware below
# it. It goes right after SecurityMiddleware, so SecurityMiddleware's headers (nosniff, Referrer-Policy)
# cover files too; XFrameOptionsMiddleware never sees them, hence _deny_framing below.
# A new list, not an insert: base's list is the same object in every settings module.
_after_security = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1
MIDDLEWARE = [
    *MIDDLEWARE[:_after_security],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[_after_security:],
]

# The image's build runs collectstatic, which gathers the admin's styles and scripts here (backend/Dockerfile).
# WhiteNoise serves them under STATIC_URL, /static/. Build output, so gitignored.
STATIC_ROOT = BASE_DIR / "staticfiles"

# The built shop app (frontend/out/, from `pnpm build`), served at the site's root: / is out/index.html.
# The image keeps out/ at the same place relative to backend/ as in the repo, so this path is true in both.
# On the real server Caddy serves the app instead (OPS-5), and these files are never asked for.
WHITENOISE_ROOT = BASE_DIR.parent / "frontend" / "out"
# /sale/ is served from out/sale/index.html: next.config.ts writes one folder per page (trailingSlash).
# WhiteNoise also redirects /sale to /sale/.
WHITENOISE_INDEX_FILE = True

# The app's manifest (frontend/src/app/manifest.ts), which Chrome reads before it offers to install the
# app (SPIKE-1). WhiteNoise's own list of file types has no .webmanifest, so without this line the manifest
# would go out as "application/octet-stream" (unknown bytes). Caddy on the real server (OPS-5) needs the
# same type: check it there.
WHITENOISE_MIMETYPES = {".webmanifest": "application/manifest+json"}

# --- How long a browser may keep each file: the same rules Caddy follows on the real server (03 §13).
# Every file outside /_next/static/ keeps its name from one deploy to the next: the pages, the admin's
# files, the service worker (SPIKE-1). For those, max-age=0: the browser asks each time whether the
# file changed, and WhiteNoise answers a tiny "304 Not Modified" when it didn't, so a deploy reaches every
# browser at once. WhiteNoise's own default, 60 seconds for every file, was right for neither kind.
WHITENOISE_MAX_AGE = 0


def _is_named_after_content(path: str, url: str) -> bool:
    """True for the files under /_next/static/: Next.js names each one after its content
    (chunks/08u9db1j9gey7.js), so new content always gets a new name and an old name never changes.
    The few that aren't (the build manifest) sit in a folder named after the build id, which Next.js makes
    new and random on every build, so they never change under one name either. Never give next.config.ts
    a fixed `generateBuildId`: those files would then change under a name browsers keep for good.
    WhiteNoise sends these with a ten-year cache and `immutable`: the browser never asks for them again,
    and a revisit on a slow shop connection downloads none of them twice. Called once per file, at startup."""
    return url.startswith("/_next/static/")


WHITENOISE_IMMUTABLE_FILE_TEST = _is_named_after_content

# No compression in Django: on the real server Caddy compresses (03 §13); on the demo, Render's proxy
# compresses answers when the browser asks for it (`content-encoding: br` on the first deploy, checked with
# docs/runbooks/demo.md). Compressing here as well would only spend the small server's time.


def _deny_framing(headers: Headers, path: str, url: str) -> None:
    """Forbid other sites to show our files inside a frame: the header XFrameOptionsMiddleware gives
    every other response. Without it, a site could lay an app page in an invisible frame over its own
    and trick a user into clicking on it (clickjacking) — on login and PIN pages too, once they exist.
    WhiteNoise calls this once per file, at startup."""
    headers["X-Frame-Options"] = "DENY"


WHITENOISE_ADD_HEADERS_FUNCTION = _deny_framing
