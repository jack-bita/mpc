"""config/urls.py — the root URL list: which path goes to which app.

Each app keeps its own routes in `apps/<app>/api/urls.py`; this file mounts them (03 §5.10), and names
the answers for an address no route matches and for a crash.
The Django admin, the creator's back room, sits at /admin/; later it gets its own address, admin.<domain>.
"""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

# An address no route matches, and a crash: under /api/, they answer in the API's one error shape too
# (apps/core/api/errors.py); elsewhere, Django's own pages.
handler404 = "apps.core.api.errors.not_found_page"
handler500 = "apps.core.api.errors.server_error_page"

urlpatterns: list[URLPattern | URLResolver] = [
    # /api/health/ — the uptime check (03 §5.10).
    path("api/", include("apps.core.api.urls")),
    # The office routes, one prefix per app (03 §5.10). A change that would break old devices gets v2
    # routes beside these, until every device has updated.
    path("api/v1/shops/", include("apps.shops.api.urls")),
    # Only the superuser can log in here (PPL-1, apps/people/admin.py).
    path("admin/", admin.site.urls),
]
