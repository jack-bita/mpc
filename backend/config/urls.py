"""config/urls.py — the root URL list: which path goes to which app.

Each app keeps its own routes in `apps/<app>/api/urls.py`; this file only mounts them (03 §5.10).
The Django admin is left out on purpose: it arrives with PPL-1, together with the custom User.
"""

from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    # /api/health/ — the uptime check (03 §5.10). Office routes will sit beside it under /api/v1/<app>/.
    path("api/", include("apps.core.api.urls")),
]
