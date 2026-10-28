"""apps/core/tests/test_error_handler.py — the API's one error shape, made by apps/core/api/errors.py
(03 §5.10, ADR-0032).

Every refusal the API sends has the same four keys, so the app reads all of them the same way:

    {"code": "shop.no_sides", "message": "A shop needs at least one side.", "fields": {}, "params": {}}

The app translates `code`, with `params`, into Swahili or English, and shows each code in `fields` beside
its input box. `message` is English for developers and logs; the app never shows it.

Each test calls a tiny view, made here and never routed, that refuses in one way. No database: the views
read nothing, and pytest-django blocks the database for a test without the django_db mark.
"""

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.http import Http404
from rest_framework import exceptions, serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.core.editing import VersionConflict


def _refusal(refuse: Callable[[], None]) -> tuple[Response, dict[str, Any]]:
    # A throwaway view whose GET calls `refuse`, called once. Returns its answer, and the JSON body the
    # app would receive.
    class RefusingView(APIView):
        # No login and no checks: the refusal under test must be the only one.
        authentication_classes = []
        permission_classes = [AllowAny]

        def get(self, request: Request) -> Response:
            refuse()
            return Response()  # never reached: every case refuses

    response = RefusingView.as_view()(APIRequestFactory().get("/"))
    assert isinstance(response, Response)
    # Rendered into the bytes that travel, as Django does after the view: this also proves the body is
    # plain JSON, with nothing left that JSON can't hold.
    response.render()
    return response, json.loads(response.content)


class NameSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=40)


def _field_missing() -> None:
    # The app sent no name: DRF's own check of the field refuses, under the field's name.
    NameSerializer(data={}).is_valid(raise_exception=True)


def _service_refusal() -> None:
    # How a service refuses (03 §5.2): a ValidationError with a code and no field. This is create_shop's
    # own (apps/shops/services.py).
    raise ValidationError("A shop needs at least one side.", code="shop.no_sides")


def _refusal_with_a_value() -> None:
    # A refusal whose message needs a value: "below the floor price of 65,000" (SALE-5). The amount
    # travels as a string, never a float (ADR-0024).
    raise ValidationError(
        "Below the floor price of %(floor)s.", code="sale.below_floor", params={"floor": Decimal("65000.00")}
    )


def _record_refused() -> None:
    # What full_clean raises (SHOP-2): a field's own check, under the field's name, and a database rule,
    # which Django files under "__all__" because it is about the whole record.
    raise ValidationError(
        {
            "name": [ValidationError("This field cannot be blank.", code="blank")],
            "__all__": [ValidationError("Another side of this shop has this letter.", code="side.code_taken")],
        }
    )


def _not_found() -> None:
    raise Http404


def _not_logged_in() -> None:
    raise exceptions.NotAuthenticated


def _edited_meanwhile() -> None:
    # Someone else saved the row after this person read it (apps/core/editing.py).
    raise VersionConflict


@pytest.mark.parametrize(
    ("refuse", "status", "code", "fields", "params"),
    [
        # When only fields are wrong, the code is `invalid` and each field names its own problem.
        pytest.param(_field_missing, 400, "invalid", {"name": ["required"]}, {}, id="a field is wrong"),
        pytest.param(_service_refusal, 400, "shop.no_sides", {}, {}, id="a service refuses"),
        pytest.param(_refusal_with_a_value, 400, "sale.below_floor", {}, {"floor": "65000.00"}, id="with a value"),
        # The problem with the whole record is the code; the field's problem stays beside its box.
        pytest.param(_record_refused, 400, "side.code_taken", {"name": ["blank"]}, {}, id="full_clean"),
        pytest.param(_not_found, 404, "not_found", {}, {}, id="not found"),
        # 403, not 401: DRF answers 401 only when a login method can name itself in a WWW-Authenticate
        # header, and the app's session login has no such name.
        pytest.param(_not_logged_in, 403, "not_authenticated", {}, {}, id="not logged in"),
        # 409 Conflict: not a wrong input, but an edit made on an old copy. The app reloads the row.
        pytest.param(_edited_meanwhile, 409, "version_conflict", {}, {}, id="edited meanwhile"),
    ],
)
def test_error_shape(
    refuse: Callable[[], None], status: int, code: str, fields: dict[str, list[str]], params: dict[str, str]
) -> None:
    response, body = _refusal(refuse)

    assert response.status_code == status
    # Always the same four keys, so the app reads every refusal the same way.
    assert set(body) == {"code", "message", "fields", "params"}
    assert body["code"] == code
    assert body["fields"] == fields
    assert body["params"] == params
    # There for developers and logs, never shown on a screen (ADR-0032).
    assert body["message"]


def test_every_problem_is_in_the_message() -> None:
    # The code names only the first problem with the whole record. The English message keeps all of
    # them, so a log never loses one.
    _, body = _refusal(_record_refused)

    assert body["message"] == "name: This field cannot be blank. Another side of this shop has this letter."


class LineSerializer(serializers.Serializer[Any]):
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)


class SaleSerializer(serializers.Serializer[Any]):
    lines = LineSerializer(many=True)


def test_nested_field_errors_get_dotted_names() -> None:
    # A sale's lines are a list inside the request. DRF answers a wrong second line with one entry per
    # line; the app gets one flat name per box instead, counted from 0: "lines.1.quantity".
    def wrong_second_line() -> None:
        SaleSerializer(data={"lines": [{"quantity": "1.500"}, {"quantity": "many"}]}).is_valid(raise_exception=True)

    _, body = _refusal(wrong_second_line)

    assert body["code"] == "invalid"
    assert body["fields"] == {"lines.1.quantity": ["invalid"]}


def test_throttled_error_says_how_long_to_wait() -> None:
    # Too many tries, as with PINs and pairing codes (AUTH-2, AUTH-4): the app says "try again in 30
    # seconds".
    def too_many_tries() -> None:
        raise exceptions.Throttled(wait=30)

    response, body = _refusal(too_many_tries)

    assert response.status_code == 429
    assert body["code"] == "throttled"
    assert body["params"] == {"wait": 30}
    # DRF's own header stays too, for any client that reads it.
    assert response.headers["Retry-After"] == "30"


def test_unexpected_error_left_to_django() -> None:
    # A bug is not a refusal. The handler leaves it alone, so Django answers 500 and logs it with its
    # traceback (03 §5.17). Turned into an error shape here, it would vanish from the logs.
    def bug() -> None:
        raise RuntimeError("a bug")

    with pytest.raises(RuntimeError, match="a bug"):
        _refusal(bug)
