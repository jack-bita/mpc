"""backend/tests/sweep_lists.py — the tenancy sweep's allowed lists: the tables and routes that may break one
of its rules, each one on purpose and with its reason (backend/tests/test_tenancy_sweep.py).

The sweep's checks are never loosened, nor edited, to let a table or a route pass; these lists change
instead, and only by a decision written on a card, as a table with no `shop` changes rule T1 (02 §16). Each
entry carries its reason, and the card that put it there. Teaching the sweep something new, such as calling
the sync routes with a device's key, is a new check instead, added in a reviewed change (backend rules).
"""

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.api.views import HealthView

# T1's exceptions (02 §16, 03 §5.4): tables that belong to no one shop, so they have no `shop`.
NO_SHOP = {
    # A person, who may work in several shops. Their job at each one is a StaffMember, which has a shop (D12).
    "people.User",
    # The tenant itself.
    "shops.Shop",
    # kg, L, pcs: the same in every shop (CAT-1, still to come).
    "catalog.Unit",
}

# Tables Django makes by itself, for its own machinery. They break T1 and T3 by Django's design, so the
# checks of those two rules skip them.
INFRASTRUCTURE = {
    # The Django admin's permissions for a person, from PermissionsMixin on User: their groups and their own
    # permissions. Only the superuser's admin uses them; shop permissions are our own codes (PPL-3). They are
    # Django's data, never a shop's. Their links CASCADE, Django's choice: a User is never deleted, only
    # switched off (`is_active`), but deleting an admin group, or a permission Django drops with a model that
    # is gone, takes its links here with it. That is Django's admin data tidying itself, with no shop's
    # history in it. (The decision: Jack, in CORE-7's plan, 28 Oct 2026; this reason was put right in its review.)
    "people.User_groups",
    "people.User_user_permissions",
}

# Routes under api/ that may be built on something other than ShopViewSet, because none of them reads a
# shop's table, so there is nothing of a shop's for the sweep to look for in them. A route that does read
# one, such as sync's pull with a device's key, is never listed here: the sweep is taught to call it instead,
# as a device of shop B, in a reviewed change.
NOT_SHOP_ROUTES: set[type] = {
    # The uptime check: no login, and no table at all (apps/core/api/views.py).
    HealthView,
    # The API's description, and the same as a page: its routes and fields, never a row (CORE-6).
    SpectacularAPIView,
    SpectacularSwaggerView,
}

# Office routes whose answers the sweep can't read, such as a PDF or an Excel download, which squeeze their
# text: route name → the test that proves the route shows nothing of another shop's. The sweep leaves each
# such route to its test, and checks that the test exists (test_every_route_left_to_its_own_test_has_one).
OWN_LEAK_TESTS: dict[str, str] = {}

# App files that may build a query by hand, `models.QuerySet(Table)`, which starts from no manager and so from
# no guard: file → why it reads no shop's row.
HAND_BUILT_QUERIES = {
    # A route's description for the API's schema is made with no visit, so with no shop open: the route's rows
    # come from an empty query (.none()), which reads no row at all (CORE-6).
    "apps/core/api/base.py": "an empty query, .none(), for the API's description",
}
