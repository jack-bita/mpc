"""apps/core/api/errors.py — the API's one error shape, and the handler that gives it to every refusal
(03 §5.10, ADR-0032).

Every refusal the API sends has four keys:

    {"code": "side.code_taken", "message": "Another side of this shop has this letter.",
     "fields": {}, "params": {}}

- `code`: what went wrong, for the app to translate (sw.json, en.json). It is the first problem with the
  whole request: a service's refusal, a database rule, `not_found`, `not_authenticated`... When only input
  fields are wrong, it is `invalid`.
- `fields`: each wrong input field, with its codes, for the app to show beside its box. A field inside a
  list gets a dotted name, counted from 0: `lines.1.quantity`.
- `params`: the values the code's message needs, such as `wait`, the seconds until a throttled person may
  try again. Exact numbers travel as strings (ADR-0024).
- `message`: English, naming every problem, for developers and logs. The app never shows it: the server
  sends no sentences for the screen.

DRF calls handle_error() for every exception a view raises (REST_FRAMEWORK in config/settings/base.py).
It shapes three kinds of refusal: Django's ValidationError, which the services and full_clean raise (03
§5.2); a VersionConflict, an edit made on an old copy (apps/core/editing.py); and DRF's own (not found,
not logged in, a serializer's checks, a throttle). Anything else is a bug, left to Django, which answers
500 and logs it.

Two answers never reach a view, so DRF never sees them: an address no route matches, and a crash. Django
answers those through not_found_page() and server_error_page() (config/urls.py), which give the same shape
under /api/, so the app reads every answer from /api/ the same way.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from typing import Any

from django.core.exceptions import NON_FIELD_ERRORS
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.functional import Promise
from django.views import defaults
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler, set_rollback

from apps.core.editing import VersionConflict

# The code when only input fields are wrong: the code beside each field says what is wrong with it.
INVALID = "invalid"


@dataclass(frozen=True)
class _Problem:
    # One thing wrong with a request. `name`: the input field it belongs to (dotted inside a list), or
    # None when it is about the whole request.
    name: str | None
    code: str
    message: str
    params: Mapping[str, Any] = field(default_factory=dict)


def handle_error(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Give a refusal the one error shape; leave anything else, a bug, to Django's 500."""
    if isinstance(exc, DjangoValidationError):
        # How the services refuse (03 §5.2), and what full_clean raises. DRF's own handler doesn't know
        # Django's ValidationError, and would leave it to become a 500.
        # set_rollback() as DRF's handler does it: if the visit runs in one transaction, its writes are
        # undone, so a refused request leaves nothing half written.
        set_rollback()
        return Response(_shape(_problems_from_django(exc)), status=400)
    if isinstance(exc, VersionConflict):
        # 409 Conflict: the request is fine, but it was made on an old copy of the row. The app reloads the
        # row and lets the person try again.
        set_rollback()
        return Response(_shape([_Problem(None, "version_conflict", str(exc))]), status=409)

    # DRF's own handler first. It turns Django's Http404 and PermissionDenied into DRF's refusals, picks the
    # status, keeps the WWW-Authenticate and Retry-After headers, and returns None for anything else.
    response = exception_handler(exc, context)
    if response is None:
        # A bug. Answered here, it would vanish from the logs; Django answers 500 and logs it with its
        # traceback (03 §5.17).
        return None
    # Django's Http404 and PermissionDenied are not DRF's: DRF has just turned them into its own refusal,
    # and wrapped its one message as {"detail": ...}.
    detail = exc.detail if isinstance(exc, exceptions.APIException) else response.data["detail"]
    body = _shape(_problems_from_drf(detail))
    # The seconds until the next try, for "try again in 30 seconds". DRF's Throttled sets `wait`, but its
    # type stubs leave it out, hence getattr.
    wait = getattr(exc, "wait", None)
    if isinstance(exc, exceptions.Throttled) and wait is not None:
        body["params"] = {"wait": wait}
    response.data = body
    return response


def _problems_from_django(exc: DjangoValidationError) -> list[_Problem]:
    # full_clean files each problem under a field's name, or under "__all__" for the whole record. A
    # service's refusal names no field at all: it has only a list of messages.
    groups = exc.error_dict.items() if hasattr(exc, "error_dict") else [(NON_FIELD_ERRORS, exc.error_list)]
    return [
        _Problem(
            name=None if name == NON_FIELD_ERRORS else name,
            # A ValidationError raised with no code is a bug in the raising code, but still a refusal.
            code=error.code or INVALID,
            # Django's own way to fill in a message: "%(limit_value)d" and the like, from its params.
            message=str(error.message) % error.params if error.params else str(error.message),
            params=error.params or {},
        )
        for name, errors in groups
        for error in errors
    ]


def _problems_from_drf(detail: Any, name: str | None = None) -> list[_Problem]:
    # DRF's refusals come as one message, a list of messages, or a dict of them by field, nested as deep
    # as the request itself.
    if isinstance(detail, Mapping):
        # By field. DRF files a problem with the whole record under "non_field_errors", Django under
        # "__all__": either way it belongs to `name` itself, not to a field inside it.
        whole_record = {api_settings.NON_FIELD_ERRORS_KEY, NON_FIELD_ERRORS}
        return [
            problem
            for key, inner in detail.items()
            for problem in _problems_from_drf(inner, name if key in whole_record else _dotted(name, key))
        ]
    if isinstance(detail, list):
        problems: list[_Problem] = []
        for index, inner in enumerate(detail):
            # A list of messages all belong to `name`. A list of dicts (or lists) has one entry per item of
            # a list field, in order, with {} for an item that is fine: each item gets its number.
            inner_name = _dotted(name, index) if isinstance(inner, Mapping | list) else name
            problems.extend(_problems_from_drf(inner, inner_name))
        return problems
    # One message: DRF's ErrorDetail, a str that also carries its code.
    return [_Problem(name, getattr(detail, "code", None) or INVALID, str(detail))]


def _dotted(name: str | None, key: object) -> str:
    # `lines` and 1 → "lines.1"; at the top of the request, the key alone.
    return str(key) if name is None else f"{name}.{key}"


def _shape(problems: list[_Problem]) -> dict[str, Any]:
    whole_request = [problem for problem in problems if problem.name is None]
    top = whole_request[0] if whole_request else None
    fields: dict[str, list[str]] = {}
    for problem in problems:
        if problem.name is not None:
            fields.setdefault(problem.name, []).append(problem.code)
    return {
        # The first problem with the whole request, which the app shows as the screen's message. When only
        # fields are wrong, `invalid`, and the codes beside each box say what.
        "code": top.code if top else INVALID,
        # Every problem, so the log keeps a second one that the code can't name.
        "message": " ".join(
            problem.message if problem.name is None else f"{problem.name}: {problem.message}" for problem in problems
        ),
        "fields": fields,
        "params": _json_safe(top.params) if top else {},
    }


def _json_safe(params: Mapping[str, Any]) -> dict[str, Any]:
    # Only values an app's message can use, in a form JSON carries exactly. Django's own params can hold
    # anything, such as a model class or a tuple of field names: those are left out.
    safe: dict[str, Any] = {}
    for key, value in params.items():
        if value is None or isinstance(value, bool | int | str):
            safe[key] = value
        elif isinstance(value, Decimal | uuid.UUID | Promise):
            # Exact numbers as strings, never floats (ADR-0024); a translatable text as plain text.
            safe[key] = str(value)
        elif isinstance(value, date | time):
            # A datetime is a date too. ISO 8601, as everywhere in the API (03 §5.10).
            safe[key] = value.isoformat()
    return safe


def not_found_page(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Django's answer for an address no route matches (handler404 in config/urls.py). Under /api/, the one
    error shape; anywhere else, Django's own page, for a person's browser."""
    if _is_api(request):
        return JsonResponse(_shape([_Problem(None, "not_found", "No route at this address.")]), status=404)
    return defaults.page_not_found(request, exception)


def server_error_page(request: HttpRequest) -> HttpResponse:
    """Django's answer for a crash (handler500 in config/urls.py), called after Django has logged it with its
    traceback (03 §5.17). Under /api/, the one error shape, with nothing of the bug in it; anywhere else,
    Django's own page."""
    if _is_api(request):
        return JsonResponse(_shape([_Problem(None, "server_error", "Server error.")]), status=500)
    return defaults.server_error(request)


def _is_api(request: HttpRequest) -> bool:
    # Every route the app calls lives under /api/ (03 §5.10).
    return request.path.startswith("/api/")
