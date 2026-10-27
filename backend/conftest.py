"""backend/conftest.py — test fixtures that every app's tests can use.

pytest reads this file before any test under backend/ and offers its fixtures to all of them, by name.
It sits outside `apps` on purpose: the layer contract (ADR-0035) is checked on every module inside
`apps`, tests included, as the import-linter comment in backend/pyproject.toml explains. So the tests of
a lower app (shops) may not import a higher one (people). This file is not part of any app, so a
fixture here may build on any app and still serve the tests of every app.
"""

import pytest
from django.test import Client

from apps.people.models import User
from apps.shops.models import Shop

# Fake data only: the repo is public (03 §10).
SUPERUSER_PASSWORD = "a-long-test-password"


@pytest.fixture
def shop_a() -> Shop:
    # Two fake shops for the tenancy tests: their rows sit side by side in one table, and each shop must
    # see only its own (ADR-0022). They live here, not in apps/core/tests: `core` is layer 0 and may not
    # import `shops`, not even in its tests (ADR-0035).
    return Shop.objects.create(name="Duka la Mfano", code="MFANO")


@pytest.fixture
def shop_b() -> Shop:
    return Shop.objects.create(name="Duka Jingine", code="JINGINE")


@pytest.fixture
def superuser() -> User:
    # Our own fixture, not pytest-django's `admin_user`: that one calls create_superuser without a
    # full name, which our User requires.
    return User.objects.create_superuser(full_name="Admin Demo", email="admin@example.com", password=SUPERUSER_PASSWORD)


@pytest.fixture
def superuser_client(client: Client, superuser: User) -> Client:
    # Django's test client, already logged in as the superuser: every admin page needs one.
    client.force_login(superuser)
    return client
