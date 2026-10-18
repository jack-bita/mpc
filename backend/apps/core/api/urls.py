"""apps/core/api/urls.py — core's routes, mounted under /api/ by config/urls.py."""

from django.urls import path

from .views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
]
