"""tests/probe/urls.py — a test-only address list, for the tenancy sweep's own tests: the probe's routes
(tests/probe/api.py) under api/, as the app's own would be. A test switches to it through the
ROOT_URLCONF setting; config/urls.py never mounts it."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from tests.probe.api import LeakyNoteViewSet, NoteViewSet, note_count

router = SimpleRouter()
router.register("notes", NoteViewSet, basename="note")
router.register("leaky-notes", LeakyNoteViewSet, basename="leaky-note")

urlpatterns = [
    path("api/v1/probe/", include(router.urls)),
    path("api/v1/probe/count/", note_count, name="note-count"),
]
