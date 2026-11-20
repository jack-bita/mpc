"""apps/staffpay/api/urls.py — the staffpay routes, mounted under /api/v1/staffpay/ by config/urls.py (WAGE-1,
ATT-5, ATT-12)."""

from rest_framework.routers import SimpleRouter

from apps.staffpay.api.views import AttendanceMonthViewSet, AttendanceWorkerViewSet, PayRateViewSet

# SimpleRouter, as every app's: `basename` names the routes ("pay-rate-list"), as ShopViewSet has no `queryset` to read
# it from. One address, pay-rates/, for the list and the create: no row has an address of its own. And one for the month
# page, attendance-month/, a read alone (ATT-5); and one for a worker's month, attendance-worker/{id}/, its worker's job
# in the address, a read alone too (ATT-12).
router = SimpleRouter()
router.register("pay-rates", PayRateViewSet, basename="pay-rate")
router.register("attendance-month", AttendanceMonthViewSet, basename="attendance-month")
router.register("attendance-worker", AttendanceWorkerViewSet, basename="attendance-worker")

urlpatterns = router.urls
