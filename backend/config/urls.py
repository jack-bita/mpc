"""config/urls.py — the root URL list: which path goes to which app.

Each app keeps its own routes in `apps/<app>/api/urls.py`; this file only mounts them (03 §5.10).
The Django admin, the creator's back room, sits at /admin/; later it gets its own address, admin.<domain>.
"""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    # /api/health/ — the uptime check (03 §5.10). Office routes will sit beside it under /api/v1/<app>/.
    path("api/", include("apps.core.api.urls")),
    # Only the superuser can log in here (PPL-1, apps/people/admin.py).
    path("admin/", admin.site.urls),
]
