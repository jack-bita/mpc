"""apps/core/api/schema.py — how the API describes itself (03 §5.10, ADR-0025): the OpenAPI schema that
drf-spectacular writes from the routes, and who may read it.

The app's TypeScript types will be generated from this description (UI-2), so it must be exact.
RouteSchema tells drf-spectacular the one thing it can't see for itself: a create and an edit take their
own fields in (`create_serializer_class`, `edit_serializer_class`, apps/core/api/base.py), and answer with
the whole row (`serializer_class`). DocsAccess decides who may read the description (/api/schema/) and its
docs page (/api/docs/): everyone on the demo, only the superuser on the real server.
"""

from typing import Any

from django.conf import settings
from drf_spectacular.openapi import AutoSchema
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class RouteSchema(AutoSchema):
    # drf-spectacular reads one serializer per route, both for what it takes and for what it answers. Ours
    # take a create's or an edit's own fields in; what they answer stays drf-spectacular's own reading.
    def get_request_serializer(self) -> Any:
        if self.method == "POST" and hasattr(self.view, "create_serializer_class"):
            return self.view.create_serializer_class
        if self.method == "PATCH" and hasattr(self.view, "edit_serializer_class"):
            return self.view.edit_serializer_class
        return super().get_request_serializer()


class DocsAccess(BasePermission):
    # Read on every visit, not once at startup, so a test or a server can change the setting.
    def has_permission(self, request: Request, view: APIView) -> bool:
        # On the demo, everyone: the API is part of what the demo shows (ADR-0029). On the real server, only
        # the superuser, logged in at /admin/ (is_staff): the routes are no secret, but nobody else needs
        # them, and a shop's staff use the app instead.
        return bool(settings.API_DOCS_PUBLIC or request.user.is_staff)
