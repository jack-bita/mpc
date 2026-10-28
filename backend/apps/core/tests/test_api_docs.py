"""apps/core/tests/test_api_docs.py — the API's description, /api/schema/, and its docs page, /api/docs/
(03 §5.10, ADR-0025).

drf-spectacular reads every route and writes the OpenAPI schema: each address, what it takes and what it
answers. The app's TypeScript types will be generated from it (UI-2), so it must build with no guesses.
The docs page shows the same description to people: open to every visitor on the demo, and only for the
superuser on the real server (API_DOCS_PUBLIC, config/settings/).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client
from drf_spectacular.drainage import reset_generator_stats
from pytest_django import Settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

# The description itself, and the page that shows it.
DOCS_ROUTES = ["/api/schema/", "/api/docs/"]


@pytest.mark.parametrize("route", DOCS_ROUTES)
def test_docs_hidden_in_production(
    superuser_client: Client, staff_client_a: APIClient, settings: Settings, route: str
) -> None:
    # On the real server the routes are no secret, but nobody else needs them: only the superuser, logged in
    # at /admin/, sees them. Not a shop's staff, who use the app, and not a stranger.
    settings.API_DOCS_PUBLIC = False

    assert Client().get(route).status_code == 403
    assert staff_client_a.get(route).status_code == 403
    assert superuser_client.get(route).status_code == 200


@pytest.mark.parametrize("route", DOCS_ROUTES)
def test_docs_public_on_the_demo(settings: Settings, route: str) -> None:
    # The demo shows recruiters and visitors how the API is built: no login needed (ADR-0029).
    settings.API_DOCS_PUBLIC = True

    assert Client().get(route).status_code == 200


def _schema(folder: Path) -> dict[str, Any]:
    # The description, written the way UI-2's `pnpm gen:api` will read it. --fail-on-warn turns every
    # warning into a failure; --validate checks the result against the OpenAPI standard. drf-spectacular
    # keeps its warnings for the whole test run, so they are cleared first: this build is judged on its own.
    reset_generator_stats()
    target = folder / "schema.json"
    call_command("spectacular", "--validate", "--fail-on-warn", "--format", "openapi-json", "--file", str(target))
    schema: dict[str, Any] = json.loads(target.read_text())
    return schema


def test_schema_builds_without_warnings(tmp_path: Path) -> None:
    # The card's Done line. A warning means drf-spectacular had to guess: a route whose answer it can't
    # see, an id whose type it can't tell. Each guess would become a wrong TypeScript type in the app.
    _schema(tmp_path)


def test_schema_says_what_each_route_takes(tmp_path: Path) -> None:
    # A create and an edit take their own fields and answer with the whole row (apps/core/api/base.py).
    # The description must say so, or the app's types would send the wrong fields.
    schema = _schema(tmp_path)
    sides = schema["paths"]["/api/v1/shops/sides/"]
    side = schema["paths"]["/api/v1/shops/sides/{id}/"]
    shapes = schema["components"]["schemas"]

    def sent(operation: dict[str, Any]) -> str:
        return str(operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]).rsplit("/", 1)[-1]

    # A create sends the id the client made (ADR-0007); an edit sends the version it read.
    assert sent(sides["post"]) == "SideCreateRequest"
    assert set(shapes["SideCreateRequest"]["required"]) == {"id", "code", "name"}
    assert sent(side["patch"]) == "SideEditRequest"
    assert set(shapes["SideEditRequest"]["required"]) == {"name", "version"}
    # The id in the address is a UUID, as every id is.
    assert side["get"]["parameters"][0]["schema"] == {"type": "string", "format": "uuid"}
    # And a side can be read and changed, never replaced whole (PUT) or deleted: nothing is deleted (T3).
    assert set(side) == {"get", "patch"}
