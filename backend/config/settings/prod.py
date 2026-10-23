"""config/settings/prod.py — settings for the real shop server and the demo. wsgi.py, asgi.py and the image use it.

Every secret is required here, with no default: if one is missing, Django refuses to start and names it.
The values come from the server's root-only `.env`, passed in by Docker (03 §13, ADR-0027).
"""

from .base import *  # noqa: F403 — start from the shared settings, then change what differs.
from .base import BASE_DIR, DATABASES, MIDDLEWARE, env, env_list

SECRET_KEY = env("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

DATABASES["default"].update(
    NAME=env("DB_NAME"),
    USER=env("DB_USER"),
    PASSWORD=env("DB_PASSWORD"),
    HOST=env("DB_HOST"),
    PORT=env("DB_PORT", "5432"),
)

# Caddy sits in front of Django and talks HTTPS with the browser (03 §13). It tells Django the original
# request was HTTPS with this header; without it Django would think every request is plain HTTP.
# Safe only because Caddy is the one way in, and Caddy always overwrites the header. Django's own port
# must never be published: anyone who reached it directly could fake "https".
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies only travel over HTTPS, so nobody on the shop's Wi-Fi can read a session (03 §10).
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# `check --deploy` still warns about the HTTPS redirect (security.W008) and HSTS (security.W004).
# Both are left to Caddy, which owns HTTPS and the strict headers (03 §10); the deploy cards set it up.

# --- Files. In the image, Django serves them itself through WhiteNoise, so one container answers
# everything from one address: the demo's setup (03 §13, OPS-1). Only here, not in base.py: on a laptop
# runserver and Caddy serve the files, and the tests serve none.
# WhiteNoise answers a request for a file before Django's URL routing. It goes right after
# SecurityMiddleware, so the security headers cover files too. A new list, not an insert: base's list
# is the same object in every settings module.
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
