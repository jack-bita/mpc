"""apps/core/tests/test_health.py — the health check that the uptime monitor and smoke tests call (03 §5.17)."""

from django.test import Client


# No @pytest.mark.django_db on purpose: pytest-django then blocks the database for this test, so it also
# proves the health check never queries it — it stays cheap enough to call every minute.
def test_health_returns_ok(client: Client) -> None:
    # The path is written out, not looked up by name: the monitor, Caddy and the deploy smoke tests
    # all call this exact address, so changing it must break this test.
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
