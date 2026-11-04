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
    # A shop's devices: the list, which whoever works on a side sees, and a manager's confirm, rename, block and
    # unblock (AUTH-5).
    path("api/v1/people/", include("apps.people.api.urls")),
    # The routes a device calls with its key: the start of a pairing, and what a paired device learns (AUTH-2).
    path("api/devices/v1/", include("apps.people.api.device_urls")),
    # Who stands at a shop's device: PIN login (AUTH-4).
    path("api/auth/", include("apps.people.api.auth_urls")),
    # Only the superuser can log in here (PPL-1, apps/people/admin.py).
    path("admin/", admin.site.urls),
    # The owner's and managers' password login and logout: the few routes of django-allauth's JSON API for the
    # browser that the app may call, and no others (ADR-0038). Outside /api/: allauth answers in its own shape, not the
    # API's one error shape, and Caddy sends /_allauth/ to Django as it does /api/ (03 v1.3).
    path("_allauth/browser/v1/", include("apps.people.api.password_urls")),
]
