"""apps/sync/api/urls.py — the sync routes, mounted under /api/sync/v1/ by config/urls.py (03 §5.10, §6).

Versioned, as the device routes are: devices are the clients slowest to update, so a change that would break them gets
v2 routes beside these until every device has moved over. Plain paths, not a router: each is one view.
"""

from django.urls import path

from apps.sync.api.views import BootstrapView, PullView, PushView

urlpatterns = [
    # A new or reset device's copy of its whole shop (SYNC-2).
    path("bootstrap/", BootstrapView.as_view(), name="sync-bootstrap"),
    # What changed after the last change the device read (SYNC-3).
    path("pull/", PullView.as_view(), name="sync-pull"),
    # What a laptop saved offline, sent in its own order (SYNC-4).
    path("push/", PushView.as_view(), name="sync-push"),
]
