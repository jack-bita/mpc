"""apps/people/api/urls.py — the people office routes, mounted under /api/v1/people/ by config/urls.py (03 §5.10).

Today a shop's devices (AUTH-5), and a staff member's temporary password (AUTH-6). The routes a device calls with its
own key are elsewhere, versioned on their own: apps/people/api/device_urls.py, under /api/devices/v1/.
"""

from rest_framework.routers import SimpleRouter

from apps.people.api.views import DeviceViewSet, StaffViewSet

# SimpleRouter, as for the sides (apps/shops/api/urls.py): devices/, devices/{id}/, and the view's two actions,
# devices/{id}/block/ and devices/{id}/unblock/. `basename` names the routes (device-list, device-detail, device-block,
# device-unblock), which DRF would otherwise read from a `queryset` in the class body, and ShopViewSet has none. And
# staff/{id}/temporary-password/ (staff-temporary-password), the staff routes' only one until PPL-4.
router = SimpleRouter()
router.register("devices", DeviceViewSet, basename="device")
router.register("staff", StaffViewSet, basename="staff")

urlpatterns = router.urls
