"""config/urls.py — the root URL list: which path goes to which app.

Each app keeps its own routes in `apps/<app>/api/urls.py`; this file only mounts them (03 §5.10).
The Django admin is left out on purpose: it arrives with PPL-1, together with the custom User.
"""

from django.urls import URLPattern, URLResolver

urlpatterns: list[URLPattern | URLResolver] = []
