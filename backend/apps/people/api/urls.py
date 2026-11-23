"""apps/people/api/urls.py — the people office routes, mounted under /api/v1/people/ by config/urls.py (03 §5.10).

Today a shop's devices (AUTH-5), its workers (PPL-4) with their roles and keys (PPL-7) and their photos (PPL-9), a staff
member's temporary password (AUTH-6), and the shop's roles (PPL-7). The routes a device calls with its own key are
elsewhere, versioned on their own: apps/people/api/device_urls.py, under /api/devices/v1/.
"""

from rest_framework.routers import SimpleRouter

from apps.people.api.views import DeviceViewSet, RoleViewSet, StaffViewSet

# SimpleRouter, as for the sides (apps/shops/api/urls.py): devices/, devices/{id}/, and the view's two actions,
# devices/{id}/block/ and devices/{id}/unblock/. `basename` names the routes (device-list, device-detail, device-block,
# device-unblock), which DRF would otherwise read from a `queryset` in the class body, and ShopViewSet has none. And
# the workers' routes (staff-list, staff-detail, staff-suspend, staff-unsuspend, staff-leave, PPL-4),
# staff/{id}/temporary-password/ (staff-temporary-password, AUTH-6), a worker's roles and keys given and taken away
# (staff-give-role, staff-give-key, staff-end-role, staff-end-key, PPL-7), a worker's photo set and taken off
# (staff-photo, staff-remove-photo, PPL-9), and the shop's roles (role-list, PPL-7).
router = SimpleRouter()
router.register("devices", DeviceViewSet, basename="device")
router.register("staff", StaffViewSet, basename="staff")
router.register("roles", RoleViewSet, basename="role")

urlpatterns = router.urls
