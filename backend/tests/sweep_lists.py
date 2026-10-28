"""backend/tests/sweep_lists.py — the tenancy sweep's allowed lists: the tables and routes that may break one
of its rules, each one on purpose and with its reason (backend/tests/test_tenancy_sweep.py).

The sweep's checks never change; these lists change instead, and only by a decision written on a card, as
a table with no `shop` changes rule T1 (02 §16). Each entry carries its reason, and the card that put it
there. A list kept apart from the checks lets the rule hold as written: the sweep's own file is never edited
(backend rules).
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
    # history in it (Jack, CORE-7, 28 Oct 2026).
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
