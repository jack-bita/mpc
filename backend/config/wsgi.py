"""config/wsgi.py — the entry point a WSGI server (gunicorn, 03 §3) loads to run the backend.

It exposes `application`; it owns nothing else.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
