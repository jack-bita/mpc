"""tests/probe/urls_delete.py — a test-only address list with a route that takes a DELETE, for the tenancy
sweep's own test of its DELETE (backend/tests/test_tenancy_sweep.py). Its own list, apart from
tests/probe/urls.py: the leaky route's DELETE really deletes shop A's note, which the routes checked after it
would then miss. The guarded route comes first, so it is checked while the note is still there."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from tests.probe.api import DeletableNoteViewSet, LeakyDeletableNoteViewSet

router = SimpleRouter()
router.register("deletable-notes", DeletableNoteViewSet, basename="deletable-note")
router.register("leaky-deletable-notes", LeakyDeletableNoteViewSet, basename="leaky-deletable-note")

urlpatterns = [path("api/v1/probe/", include(router.urls))]
