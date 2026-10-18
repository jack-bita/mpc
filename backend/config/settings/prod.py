"""config/settings/prod.py — settings for the real shop server and the demo. wsgi.py and asgi.py use it.

Every secret is required here, with no default: if one is missing, Django refuses to start and names it.
The values come from the server's root-only `.env`, passed in by Docker (03 §13, ADR-0027).
"""

from .base import *  # noqa: F403 — start from the shared settings, then change what differs.
from .base import DATABASES, env, env_list

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
