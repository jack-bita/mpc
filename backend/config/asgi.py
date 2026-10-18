"""config/asgi.py — the entry point for an ASGI server (uvicorn), kept for R2's live updates (03 §3, §5.12).

R1 runs under WSGI; this file exposes `application` so the switch needs no new code.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
