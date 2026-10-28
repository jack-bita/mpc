"""apps/core/api/urls.py — core's routes, mounted under /api/ by config/urls.py: the health check, and the
API's description with its docs page (03 §5.10)."""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .schema import DocsAccess
from .views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    # The API's description (OpenAPI), which UI-2 turns into the app's TypeScript types (ADR-0025).
    path("schema/", SpectacularAPIView.as_view(permission_classes=[DocsAccess]), name="schema"),
    # The same description as a page, to read the routes and try them (Swagger UI).
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[DocsAccess]), name="docs"),
]
