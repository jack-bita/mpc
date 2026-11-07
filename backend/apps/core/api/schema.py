"""apps/core/api/schema.py — how the API describes itself (03 §5.10, ADR-0025): the OpenAPI schema that
drf-spectacular writes from the routes, and who may read it.

The app's TypeScript types are generated from this description (UI-2), so it must be exact. RouteSchema
tells drf-spectacular two things it can't see for itself. A create and an edit take their own fields in
(`create_serializer_class`, `edit_serializer_class`, apps/core/api/base.py), and answer with the whole row
(`serializer_class`). And every route refuses in the one error shape (apps/core/api/errors.py), described
here by ApiErrorSerializer. DocsAccess opens the description (/api/schema/) and its docs page (/api/docs/)
to everyone on the demo and on a laptop, and closes them on the real server.
"""

from typing import Any

from django.conf import settings
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import Direction, extend_schema_field
from rest_framework import exceptions, serializers
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


# One value an error's message may need, such as `wait`, the seconds until the next try. Only what
# _json_safe() lets through (apps/core/api/errors.py): text, a whole number, yes or no, or nothing. A
# JSONField would say "any JSON at all", and the app's types would have to treat each value as unknown.
@extend_schema_field({"oneOf": [{"type": "string"}, {"type": "integer"}, {"type": "boolean"}], "nullable": True})
class ErrorParamField(serializers.JSONField):
    pass


# The one error shape, as the description shows it: `{"code", "message", "fields", "params"}`. It only
# describes: the handler builds the shape itself (apps/core/api/errors.py, which says what each key holds),
# so no refusal ever passes through this class. A comment, not a docstring: drf-spectacular copies a
# serializer's docstring into the description, onto the public docs page, and this note is for us.
class ApiErrorSerializer(serializers.Serializer[Any]):
    # The four keys are listed here, not as class attributes as usual: one of them is named "fields", the
    # name a serializer already gives the list of its own fields, and the type checker would see a clash.
    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        return {
            "code": serializers.CharField(),
            "message": serializers.CharField(),
            # Each wrong input field, by its dotted name (`lines.1.quantity`), with its codes.
            "fields": serializers.DictField(child=serializers.ListField(child=serializers.CharField())),
            "params": serializers.DictField(child=ErrorParamField()),
        }


class RouteSchema(AutoSchema):
    # drf-spectacular reads one serializer per route, both for what it takes and for what it answers. Ours
    # take a create's or an edit's own fields in; what they answer stays drf-spectacular's own reading.
    def get_request_serializer(self) -> Any:
        if self.method == "POST" and hasattr(self.view, "create_serializer_class"):
            return self.view.create_serializer_class
        if self.method == "PATCH" and hasattr(self.view, "edit_serializer_class"):
            return self.view.edit_serializer_class
        return super().get_request_serializer()

    # Every route refuses in the one error shape: a service's refusal, a wrong field, a missing login, a
    # throttle, and under /api/ even a crash (apps/core/api/errors.py). drf-spectacular can't see that, as
    # the handler sits outside every view, so each route gets it as its `default` answer: in OpenAPI, the
    # answer for every status the route doesn't list. The app's typed client reads it as the type of every
    # error (UI-2); without it, an error's type would be unknown, and a screen couldn't read its code safely.
    # A private method, the one drf-spectacular's own FAQ points to for an answer every route shares:
    # test_every_route_refuses_in_the_error_shape fails if a new version stops calling it.
    def _get_response_bodies(self, direction: Direction = "response") -> dict[str, Any]:
        responses: dict[str, Any] = super()._get_response_bodies(direction)
        # The same helper drf-spectacular uses for a route's own answers, so the error shape becomes one
        # shared component (ApiError), not a copy in every route. drf-spectacular leaves it without type
        # hints, hence the ignore.
        error = self._get_response_for_code(ApiErrorSerializer, "default", direction=direction)  # type: ignore[no-untyped-call]
        responses.setdefault("default", error)
        return responses


class DocsAccess(BasePermission):
    # Read on every visit, not once at startup, so a test or a server can change the setting.
    def has_permission(self, request: Request, view: APIView) -> bool:
        # Open on the demo, to everyone: the API is part of what the demo shows (ADR-0029). Closed on the
        # real server, to everyone, the superuser too (Jack, CORE-6): the docs page runs code from another
        # website (a CDN) on our address, and there the superuser would run it logged in, beside the real
        # shop's data. Nobody needs it there: the app's types are built from the code (UI-2), and the demo
        # shows the same API. "Not found", as if there were no docs there at all.
        if not settings.API_DOCS_PUBLIC:
            raise exceptions.NotFound()
        return True
