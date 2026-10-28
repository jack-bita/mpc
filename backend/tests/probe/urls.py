"""tests/probe/urls.py — a test-only address list, for the tenancy sweep's own tests: the probe's routes
(tests/probe/api.py) under api/, as the app's own would be, some of them mounted in the awkward ways a real
address list could be. A test switches to it through the ROOT_URLCONF setting; config/urls.py never mounts it."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from tests.probe.api import LeakyNoteViewSet, NoteViewSet, note_count

router = SimpleRouter()
router.register("notes", NoteViewSet, basename="note")
router.register("leaky-notes", LeakyNoteViewSet, basename="leaky-note")

# Two apps whose routers happen to pick one name. config/urls.py mounts each app with no namespace, so their
# names meet. The leaky one comes first: Django finds a name's last route, so a sweep that went by names
# alone would only ever call the guarded one.
leaky_twin = SimpleRouter()
leaky_twin.register("twin-notes-leaky", LeakyNoteViewSet, basename="twin-note")
twin = SimpleRouter()
twin.register("twin-notes", NoteViewSet, basename="twin-note")

urlpatterns = [
    path("api/v1/probe/", include(router.urls)),
    path("api/v1/probe/", include(leaky_twin.urls)),
    path("api/v1/probe/", include(twin.urls)),
    # A list nested under another row, and a route with no name: the sweep can build neither address.
    path("api/v1/probe/owners/<uuid:owner>/notes/", NoteViewSet.as_view({"get": "list"}), name="nested-note-list"),
    path("api/v1/probe/unnamed-notes/", NoteViewSet.as_view({"get": "list"})),
    path("api/v1/probe/count/", note_count, name="note-count"),
]
