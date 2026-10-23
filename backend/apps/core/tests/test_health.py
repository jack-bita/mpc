"""apps/core/tests/test_health.py — the health check that the uptime monitor and smoke tests call (03 §5.17)."""

import base64

from django.test import Client
from pytest_django import Settings


# No @pytest.mark.django_db on purpose: pytest-django then blocks the database for this test, so it also
# proves the health check never queries it — it stays cheap enough to call every minute.
def test_health_returns_ok(client: Client, settings: Settings) -> None:
    # Called like a logged-in browser (a session cookie) and a script with a password (Basic login).
    # If the view ever ran DRF's login checks, they would look the session or the user up in the
    # database, and the block above would fail this test.
    client.cookies["sessionid"] = "any-session"
    basic_login = "Basic " + base64.b64encode(b"someone:secret").decode()

    # The path is written out, not looked up by name: the monitor, Caddy and the deploy smoke tests
    # all call this exact address, so changing it must break this test.
    response = client.get("/api/health/", headers={"authorization": basic_login})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": settings.APP_VERSION}


def test_health_reports_the_app_version(client: Client, settings: Settings) -> None:
    # The image's build sets APP_VERSION to the git commit (backend/Dockerfile). The demo's smoke test
    # compares the answer with the commit it just deployed (OPS-2), so the view must read the setting
    # on every request, not answer with a fixed text.
    settings.APP_VERSION = "4129684"

    response = client.get("/api/health/")

    assert response.json()["version"] == "4129684"
