"""apps/control/api/urls.py — the control routes, mounted under /api/v1/control/ by config/urls.py (CTRL-3)."""

from rest_framework.routers import SimpleRouter

from apps.control.api.views import AttachmentViewSet

# SimpleRouter, as every app's: `basename` names the routes, as ShopViewSet has no `queryset` to read it from. The
# view has only its @action, so the one address is attachments/{id}/file/ ("attachment-file").
router = SimpleRouter()
router.register("attachments", AttachmentViewSet, basename="attachment")

urlpatterns = router.urls
