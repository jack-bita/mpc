"""apps/people/api/urls.py — the people office routes, mounted under /api/v1/people/ by config/urls.py (03 §5.10).

Today a shop's devices (AUTH-5). The routes a device calls with its own key are elsewhere, versioned on their own:
apps/people/api/device_urls.py, under /api/devices/v1/.
"""

from rest_framework.routers import SimpleRouter

from apps.people.api.views import DeviceViewSet

# SimpleRouter, as for the sides (apps/shops/api/urls.py): devices/ and devices/{id}/. `basename` names the routes
# (device-list, device-detail), which DRF would otherwise read from a `queryset` in the class body, and ShopViewSet has
# none.
router = SimpleRouter()
router.register("devices", DeviceViewSet, basename="device")

urlpatterns = router.urls
