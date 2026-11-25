"""apps/staffpay/api/urls.py — the staffpay routes, mounted under /api/v1/staffpay/ by config/urls.py (WAGE-1,
ATT-5, ATT-12, ATT-6, ATT-13, WAGE-7, WAGE-8, WAGE-2)."""

from rest_framework.routers import SimpleRouter

from apps.staffpay.api.views import (
    AdvanceViewSet,
    AttendanceDayViewSet,
    AttendanceMonthViewSet,
    AttendanceTapViewSet,
    AttendanceWorkerViewSet,
    MealMoneyViewSet,
    PayRateViewSet,
    PayViewSet,
)

# SimpleRouter, as every app's: `basename` names the routes ("pay-rate-list"), as ShopViewSet has no `queryset` to read
# it from. One address, pay-rates/, for the list and the create: no row has an address of its own. And one for the month
# page, attendance-month/, a read alone (ATT-5); one for a worker's month, attendance-worker/{id}/, its worker's job
# in the address, a read alone too (ATT-12); one for a decision on a day, attendance-days/{id}/decide/, its day in
# the address (ATT-6); one for a manager's fixes to the taps, attendance-taps/ to add one and
# attendance-taps/{id}/void/ to cross one out, its tap in the address (ATT-13); one for the day's meal money,
# meal-money/ for the days and to type some, meal-money/{id}/void/ to cross one out (WAGE-7); one for money given before
# payday, advances/ for a month's and to type one, advances/{id}/ for one, advances/{id}/void/ to cross it out (WAGE-8);
# and one for the month's pay, pay/ for everyone's and pay/{id}/ for one worker's, its job in the address, reads alone
# (WAGE-2).
router = SimpleRouter()
router.register("pay-rates", PayRateViewSet, basename="pay-rate")
router.register("attendance-month", AttendanceMonthViewSet, basename="attendance-month")
router.register("attendance-worker", AttendanceWorkerViewSet, basename="attendance-worker")
router.register("attendance-days", AttendanceDayViewSet, basename="attendance-day")
router.register("attendance-taps", AttendanceTapViewSet, basename="attendance-tap")
router.register("meal-money", MealMoneyViewSet, basename="meal-money")
router.register("advances", AdvanceViewSet, basename="advance")
router.register("pay", PayViewSet, basename="pay")

urlpatterns = router.urls
