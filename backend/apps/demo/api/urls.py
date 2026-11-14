"""apps/demo/api/urls.py — the one-tap demo's routes, mounted under /api/devices/v1/ by config/urls.py (OPS-3).

Beside the device routes (apps/people/api/device_urls.py), under the same prefix, as a demo device is a device like
any other; in the demo app, as only it may read the seed's list of people and their PINs (ADR-0043's layers).
"""

from django.urls import path

from apps.demo.api.views import DemoDeviceView, DemoOpenView

urlpatterns = [
    path("demo/", DemoDeviceView.as_view(), name="device-demo"),
    path("demo/open/", DemoOpenView.as_view(), name="device-demo-open"),
]
