"""apps/people/api/device_urls.py — the routes a device calls with its key, mounted under /api/devices/v1/ by
config/urls.py (03 §5.10).

Versioned, as sync's routes are: devices are the clients slowest to update, so a change that would break them gets
v2 routes beside these until every device has moved over. Plain paths, not a router: each is one view, with no rows
to list or look up.
"""

from django.urls import path

from apps.people.api.views import PairingView

urlpatterns = [
    path("pairing/", PairingView.as_view(), name="device-pairing"),
]
