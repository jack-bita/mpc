"""config/settings — Django's settings, one file per environment (03 §4).

- base.py   what every environment shares, and the helpers that read environment variables
- dev.py    Jack's laptop: debug on, safe local defaults            ← manage.py uses it
- test.py   pytest: fixed values, fast password hashing             ← pytest-django uses it
- prod.py   the real server and the demo: every secret is required  ← wsgi.py and asgi.py use it

Pick one with the DJANGO_SETTINGS_MODULE environment variable, e.g. `config.settings.prod`.
"""
