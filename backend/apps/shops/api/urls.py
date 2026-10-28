"""apps/shops/api/urls.py — the shops routes, mounted under /api/v1/shops/ by config/urls.py."""

from rest_framework.routers import SimpleRouter

from apps.shops.api.views import SideViewSet

# SimpleRouter: one address for the list and one for each row (sides/, sides/{id}/). Not DefaultRouter,
# which adds a page listing every route: the API docs do that (CORE-6). `basename` names the routes,
# which DRF would otherwise read from a `queryset` in the class body, and ShopViewSet has none.
router = SimpleRouter()
router.register("sides", SideViewSet, basename="side")

urlpatterns = router.urls
