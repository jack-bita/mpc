"""backend/conftest.py — test fixtures that every app's tests can use.

pytest reads this file before any test under backend/ and offers its fixtures to all of them, by name.
It sits outside `apps` on purpose: the layer contract (ADR-0035) is checked on every module inside
`apps`, tests included, as the import-linter comment in backend/pyproject.toml explains. So the tests of
a lower app (shops) may not import a higher one (people). This file is not part of any app, so a
fixture here may build on any app and still serve the tests of every app.
"""

from collections.abc import Callable

import pytest
from django.conf import settings
from django.core.cache import caches
from django.test import Client
from rest_framework.test import APIClient

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Device, Role, RoleAssignment, StaffMember, User
from apps.people.services import add_staff, assign_role, copy_role_templates
from apps.shops.models import Shop, Side
from apps.shops.services import add_side

# Fake data only: the repo is public (03 §10).
SUPERUSER_PASSWORD = "a-long-test-password"


@pytest.fixture(autouse=True)
def empty_caches(request: pytest.FixtureRequest) -> None:
    # Every test that uses the database starts with empty caches (backend/tests/test_caches.py). The pairing limits
    # count in cache tables, which createcachetable makes, not models (CACHES, config/settings/base.py): a test marked
    # transaction=True really commits, Django's clean-up after it empties the models' tables only, and a count it left
    # would make a later test's limit come early. A test with no database has no caches, and may not open one.
    if request.node.get_closest_marker("django_db") is None:
        return
    for name in settings.CACHES:
        caches[name].clear()


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
def staff_a(shop_a: Shop) -> StaffMember:
    # A fake staff member at shop A, for tests that record who did something (a void stamp's
    # `voided_by`). Made the way the app makes one: create_user, then the people service, inside the
    # shop, because the service's checks read through the guard (PPL-2).
    user = User.objects.create_user(full_name="Staff Demo")
    with shop_context(shop_a):
        return add_staff(shop=shop_a, user=user, display_name="Staff A", by=None)


@pytest.fixture
def staff_a2(shop_a: Shop) -> StaffMember:
    # A second staff member at shop A, for a flag that names two people who each explain it (CTRL-1).
    user = User.objects.create_user(full_name="Staff Demo Two")
    with shop_context(shop_a):
        return add_staff(shop=shop_a, user=user, display_name="Staff A2", by=None)


@pytest.fixture
def side_a(shop_a: Shop) -> Side:
    # A side of shop A, made the way the app makes one: with its stock location and its cash drawer (SHOP-2).
    with shop_context(shop_a):
        return add_side(shop=shop_a, code="D", name="Dawa", by=None)


@pytest.fixture
def side_b(shop_b: Shop) -> Side:
    # A side of shop B, for tests that check a row of one shop can't link to another shop's side (T1).
    with shop_context(shop_b):
        return add_side(shop=shop_b, code="P", name="Pembejeo", by=None)


@pytest.fixture
def staff_b(shop_b: Shop) -> StaffMember:
    # A fake staff member at shop B, for tests that check a person of one shop can't act in another (T1).
    user = User.objects.create_user(full_name="Staff Demo B")
    with shop_context(shop_b):
        return add_staff(shop=shop_b, user=user, display_name="Staff B", by=None)


@pytest.fixture
def device_a(shop_a: Shop, side_a: Side) -> Device:
    # A device of shop A, for the tests of a row that names one (X3). Only the row: its key's hash is made up, so it
    # opens nothing. A test that logs in with a key pairs a device the way the app does (confirm_pairing).
    with shop_context(shop_a):
        return Device.objects.create(shop=shop_a, home_side=side_a, name="Laptop ya Dawa", code=1, key_hash="a" * 64)


@pytest.fixture
def give_role() -> Callable[[StaffMember, RoleTemplate, Side | None], None]:
    # Gives a person one of their shop's six roles, on one side or on every side (side=None), the way the app
    # does (assign_role, PPL-3). shop_a and shop_b are bare Shop rows with no roles, so the first role asked for
    # copies the six templates in; later ones reuse that copy, as a shop never has two (role.template_taken).
    # Given by the system (by=None), as a shop's first owner is: the giver's own check is PPL-3's to test. Given once:
    # a test may ask again for a role a fixture already gave, as the sweep's devices and the staff clients both give
    # their shop's owner the Owner role (AUTH-2); a second assign_role would be refused (role.already_given).
    def give(staff: StaffMember, template: RoleTemplate, side: Side | None) -> None:
        with shop_context(staff.shop_id):
            role = Role.objects.filter(template=template).first() or copy_role_templates(staff.shop)[template]
            if not RoleAssignment.objects.filter(staff=staff, role=role, side=side).exists():
                assign_role(staff, role, side=side, by=None)

    return give


@pytest.fixture
def staff_client_a(
    staff_a: StaffMember, give_role: Callable[[StaffMember, RoleTemplate, Side | None], None]
) -> APIClient:
    # DRF's test client, logged in as a staff member of shop A, the way the office screens are. A login, AUTH-3's
    # password or AUTH-4's PIN (apps/people/api/staff_session.py), leaves the person acting in
    # `request.auth`, which names the shop the visit works for (apps/core/api/base.py). force_authenticate skips the
    # login and puts the staff member there directly; apps/people/tests/test_staff_session.py goes through the real
    # one. DRF's type stubs expect its own Token model there; DRF itself takes any object, and ours is the staff member.
    # The owner of their shop, on every side (PPL-5): the routes ask for each action's permission, so a person
    # with none would see nothing and do nothing. Tests that check who may do what give their own people their
    # own roles (backend/tests/test_route_permissions.py); these clients test everything else a route does.
    give_role(staff_a, RoleTemplate.OWNER, None)
    client = APIClient()
    client.force_authenticate(user=staff_a.user, token=staff_a)  # type: ignore[arg-type]
    return client


@pytest.fixture
def staff_client_b(
    staff_b: StaffMember, give_role: Callable[[StaffMember, RoleTemplate, Side | None], None]
) -> APIClient:
    # The same, as a staff member of shop B: the visitor the tenancy sweep sends to every route, to look
    # for shop A's rows (backend/tests/test_tenancy_sweep.py). The owner of shop B, on every side, so that the
    # only thing hiding shop A's rows from them is the shop guard, which the sweep is there to check: with no
    # permission at all, every route would show them nothing, and the sweep would pass without looking (PPL-5).
    give_role(staff_b, RoleTemplate.OWNER, None)
    client = APIClient()
    client.force_authenticate(user=staff_b.user, token=staff_b)  # type: ignore[arg-type]
    return client


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
