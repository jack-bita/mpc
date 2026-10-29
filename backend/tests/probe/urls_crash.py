"""tests/probe/urls_crash.py — a test-only address list with a leaky route that crashes on a key both shops
have, for the tenancy sweep's own test of what a crash does (backend/tests/test_tenancy_sweep.py). Its own list,
apart from tests/probe/urls.py: the crash stops the whole check, so it can't sit among the other routes."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from tests.probe.api import LeakyNoteByTextViewSet

router = SimpleRouter()
router.register("leaky-notes-by-text", LeakyNoteByTextViewSet, basename="leaky-note-by-text")

urlpatterns = [path("api/v1/probe/", include(router.urls))]
