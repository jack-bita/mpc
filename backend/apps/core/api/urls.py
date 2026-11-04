"""apps/core/api/urls.py — core's routes, mounted under /api/ by config/urls.py: the health check, and the
API's description with its docs page (03 §5.10)."""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .schema import DocsAccess
from .views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    # The API's description (OpenAPI), which UI-2 turns into the app's TypeScript types (ADR-0025). No login is read:
    # these hold no shop's data and answer everyone alike (DocsAccess), so a browser still holding a suspended person's
    # session must not be refused here. The login's own check would run before DocsAccess, so it would answer 403 even
    # where the docs are closed, which shows that the address is there.
    path(
        "schema/",
        SpectacularAPIView.as_view(permission_classes=[DocsAccess], authentication_classes=[]),
        name="schema",
    ),
    # The same description as a page, to read the routes and try them (Swagger UI).
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[DocsAccess], authentication_classes=[]),
        name="docs",
    ),
]
