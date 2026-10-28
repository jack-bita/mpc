"""backend/tests/test_tenancy_sweep.py — the tenancy sweep: every table and every route of our apps keeps
each shop's rows apart, checked by itself (03 §5.4, ADR-0022).

Many shops keep their rows side by side in the same tables, and the guard (CORE-2) shows each visit only its
own shop's rows. That holds only while every table and every route is built the way the guard expects, and
nothing stops a new one from being built another way. So this module asks Django for every table of our
apps (the ones under backend/apps/) and checks each one, with no list of tables to keep up to date:

- it has `shop`, through ShopScoped, unless it belongs to no one shop (T1);
- every link it holds to another table uses PROTECT, so deleting a row never takes other rows with it (T3);
- its primary key keeps the name PostgreSQL gave it, which the API's creates rely on (CORE-6);
- it keeps the guard: every manager it has, except the admin's `all_shops`, refuses to build a read while no
  shop is open (CORE-2).

It also reads our code, as test_no_floats.py does, for the only two doors that open every shop at once:
`all_shops`, for the superuser's admin pages, and `system_context()`, for system jobs (03 §5.4). Each must
stay in its own place, and tests may use both. Until now only a search by hand found them.

And it walks the address list for every route of the office API, the routes built on ShopViewSet
(apps/core/api/base.py):

- called by a staff member of shop B, no route shows any row of shop A: a list shows none of them, and a
  detail route answers "not found" for each one (03 §5.4). Both shops are filled in backend/tests/conftest.py;
- each route names where its table keeps a row's side (`side_field`), for the per-side hooks (PPL-3);
- no route under api/ escapes the sweep by being built on something else.

A new table, file or route is checked with no change here, and this file must stay green without being edited
(backend rules). Each check is a function that returns what breaks its rule, as in test_no_floats.py. The
tests of the checks hand them tables and code built to break the rule (the tables made in a throwaway
registry of their own, so they never join the real list), and a few tests make sure the real lists are not
empty, so the sweep can't pass by looking at nothing.
"""

import ast
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from django.apps import apps
from django.apps.registry import Apps
from django.core.exceptions import FieldDoesNotExist
from django.db import connection, models
from django.http import HttpResponse
from django.test.utils import isolate_apps
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.api.base import ShopViewSet
from apps.core.api.views import HealthView
from apps.core.models import ShopScoped, ShopScopedManager, UUIDModel
from apps.core.tenancy import NoShopSelected, shop_context
from apps.shops.models import PaymentAccount, Shop, Side, StockLocation
from tests.probe.models import Note

BACKEND = Path(__file__).resolve().parents[1]
APPS = BACKEND / "apps"
CONFIG = BACKEND / "config"

# T1's exceptions (02 §1, 03 §5.4): tables that belong to no one shop, so they have no `shop`.
NO_SHOP = {
    # A person, who may work in several shops. Their job at each one is a StaffMember, which has a shop (D12).
    "people.User",
    # The tenant itself.
    "shops.Shop",
    # kg, L, pcs: the same in every shop (CAT-1, still to come).
    "catalog.Unit",
}

# Tables Django makes by itself, for its own machinery. They break T1 and T3 by Django's design, so the
# checks of those two rules skip them. Each one is listed on purpose, with its reason.
INFRASTRUCTURE = {
    # The Django admin's permissions for a person, from PermissionsMixin on User: their groups and their own
    # permissions. Only the superuser's admin uses them; shop permissions are our own codes (PPL-3). Their
    # links CASCADE, Django's choice, but a User is never deleted, only switched off (`is_active`), so the
    # CASCADE never runs (Jack, CORE-7's plan, 28 Oct 2026).
    "people.User_groups",
    "people.User_user_permissions",
}

# Routes under api/ that may be built on something other than ShopViewSet, because none of them reads a
# shop's table. Each one is listed on purpose, with its reason.
NOT_SHOP_ROUTES: set[type] = {
    # The uptime check: no login, and no table at all (apps/core/api/views.py).
    HealthView,
    # The API's description, and the same as a page: its routes and fields, never a row (CORE-6).
    SpectacularAPIView,
    SpectacularSwaggerView,
}


def our_tables() -> list[type[models.Model]]:
    # Every table of our apps, as Django lists them. include_auto_created: also the link table Django makes
    # by itself for a many-to-many field with no `through` table of ours. Such a table has no `shop` and its
    # links CASCADE (SHOP-2's review), so it is swept like any other.
    # Ours are the apps under backend/apps/. Django's own tables and the libraries' are not, and neither is
    # the test-only probe app, which exists only in the test settings.
    return [
        table for table in apps.get_models(include_auto_created=True) if table._meta.app_config.name.startswith("apps.")
    ]


def label_of(table: type[models.Model] | str) -> str:
    # A link names its table as a class once Django has found it, and as "app.Model" text until then. In the
    # throwaway registries below, shops.Shop is never found, so the text is all there is.
    return table if isinstance(table, str) else table._meta.label


def shop_problems(tables: Iterable[type[models.Model]]) -> list[str]:
    # T1: every row belongs to one shop. ShopScoped gives a table its `shop` and the guard on reads
    # (ADR-0022), so a table with a `shop` link of its own but not built on ShopScoped would have no guard.
    # A table built on it can still take the field away (`shop = None`: Django allows it for a field from an
    # abstract base) or make it optional, so the field itself is checked too.
    problems = []
    for table in tables:
        label = table._meta.label
        if label in NO_SHOP or label in INFRASTRUCTURE:
            continue
        if not issubclass(table, ShopScoped):
            problems.append(f"{label}: not built on ShopScoped")
            continue
        try:
            shop = table._meta.get_field("shop")
        except FieldDoesNotExist:
            problems.append(f"{label}: has no `shop`")
            continue
        if not isinstance(shop, models.ForeignKey) or shop.null or label_of(shop.remote_field.model) != "shops.Shop":
            problems.append(f"{label}: `shop` is not a required link to shops.Shop")
    return problems


def link_problems(tables: Iterable[type[models.Model]]) -> list[str]:
    # T3 and rule 7: nothing is deleted, so a link must never act when the row it points at is deleted.
    # PROTECT refuses that delete. CASCADE would follow it (a customer deleted, and their debts with them),
    # and SET_NULL would quietly forget whose a row was.
    # A many-to-many field has no `on_delete` of its own, and no column, so it is not among the concrete
    # fields read here: its link table holds the two links, and that table is swept like any other.
    problems = []
    for table in tables:
        if table._meta.label in INFRASTRUCTURE:
            continue
        for field in table._meta.concrete_fields:
            # ForeignKey covers OneToOneField too, which is built on it.
            if isinstance(field, models.ForeignKey) and field.remote_field.on_delete is not models.PROTECT:
                rule = getattr(field.remote_field.on_delete, "__name__", "no rule")
                problems.append(f"{table._meta.label}.{field.name}: {rule}, not PROTECT")
    return problems


def primary_key_problems(tables: Iterable[type[models.Model]]) -> list[str]:
    # CORE-6's create tells an id already taken by another shop's row from every other clash by the name of the
    # rule it broke: "<table>_pkey", the name PostgreSQL gives a table's primary key when it makes the table
    # (_id_taken() in apps/core/api/base.py). A renamed table keeps its key's old name, because PostgreSQL
    # renames the table and not its rules; and on a table name over 58 characters, PostgreSQL cuts the key's
    # name short, to fit its limit of 63. Either way, a taken id would get a 500 instead of `id.taken`.
    problems = []
    with connection.cursor() as cursor:
        for table in tables:
            name = table._meta.db_table
            rules = connection.introspection.get_constraints(cursor, name)
            keys = sorted(rule_name for rule_name, rule in rules.items() if rule["primary_key"])
            if keys != [f"{name}_pkey"]:
                problems.append(f"{table._meta.label}: primary key named {keys}, not {name}_pkey")
    return problems


def guarded(manager: models.Manager[Any]) -> bool:
    # The guard is ShopScopedManager (apps/core/models.py), and it shows itself by refusing to build a read
    # while no shop is open: it fails closed (ADR-0022). Both are asked, because a manager of another class,
    # or one built on this class that skips its check, reads every shop. Asked with no shop open, as every
    # test starts; refusing costs no query, so no database is needed.
    if not isinstance(manager, ShopScopedManager):
        return False
    try:
        manager.all()
    except NoShopSelected:
        return True
    return False


def guard_problems(tables: Iterable[type[models.Model]]) -> list[str]:
    # CORE-2: a shop's table loses its guard with no error in two ways (apps/core/models.py, ShopScoped.Meta):
    # - an abstract base built on ShopScoped that writes a Meta of its own, not built on ShopScoped.Meta: its
    #   tables lose `default_manager_name`, and the first manager ShopScoped declares, `all_shops`, becomes
    #   their default, the one Django, the admin's forms and DRF read through;
    # - a table that declares managers of its own: its own `objects`, which replaces the guarded one, or any
    #   other manager, a second door that reads every shop.
    # So every manager a table has is asked, the default above all. The one exception is `all_shops`, the
    # superuser's admin door (CORE-2), as long as it is not the default. A table whose only change is a Meta
    # of its own keeps the guard: with no manager of its own, Django takes the default's name from its first
    # parent (CORE-3's review). Tables not built on ShopScoped are the shop check's to report.
    problems = []
    for table in tables:
        if not issubclass(table, ShopScoped):
            continue
        # Django always gives a table a default manager; its type stubs allow None.
        default = getattr(table._meta.default_manager, "name", None)
        for manager in table._meta.managers:
            if manager.name == "all_shops" and manager.name != default:
                continue
            if not guarded(manager):
                which = " (the default)" if manager.name == default else ""
                problems.append(f"{table._meta.label}.{manager.name}: no guard{which}")
    return problems


def in_tests(path: Path) -> bool:
    # Tests may open every shop: to count every shop's rows after a write (test_create_shop_all_or_nothing,
    # SHOP-2), or to test the doors themselves (apps/core/tests/test_shop_scoped.py, CORE-2).
    return "tests" in path.relative_to(BACKEND).parts[:-1] or path.name in {"tests.py", "conftest.py"}


def may_use_all_shops(path: Path) -> bool:
    # The superuser's admin pages. A page answers a visit, and system_context() is for system jobs only, so
    # the admin has its own door, for its lists (apps/core/models.py).
    return path.name == "admin.py" or in_tests(path)


def may_use_system_context(path: Path) -> bool:
    # System jobs, which answer no visit: management commands (the nightly checks the scheduler runs, and
    # the demo seed, DATA-1) and background tasks (tasks.py, 03 §5.11). Never code that answers a visit, the
    # admin's pages included: a visit works for one shop (03 §5.4).
    folders = path.relative_to(BACKEND).parts[:-1]
    return folders[-2:] == ("management", "commands") or path.name == "tasks.py" or in_tests(path)


def uses_of(name: str, source: str) -> list[int]:
    # The lines where the code uses `name`: by itself (system_context()), as an attribute (Side.all_shops,
    # tenancy.system_context), or imported. Python's own parser reads the code (the `ast` module), so
    # comments and strings never count, and neither does the line that stores the name: `all_shops =
    # models.Manager()` in apps/core/models.py defines the door, it doesn't open it.
    lines = []
    for node in ast.walk(ast.parse(source)):
        if (
            (isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load))
            or (isinstance(node, ast.Attribute) and node.attr == name and isinstance(node.ctx, ast.Load))
            or (isinstance(node, ast.alias) and node.name.split(".")[-1] == name)
        ):
            lines.append(node.lineno)
    return sorted(lines)


def uses_in_our_code(name: str) -> dict[str, list[int]]:
    # Every Python file of our apps and of the settings, tests and migrations included: a migration that
    # opened every shop would be worth a look too.
    found = {}
    for path in sorted([*APPS.rglob("*.py"), *CONFIG.rglob("*.py")]):
        lines = uses_of(name, path.read_text(encoding="utf-8"))
        if lines:
            found[str(path.relative_to(BACKEND))] = lines
    return found


def misplaced_uses(name: str, may_use: Callable[[Path], bool]) -> dict[str, list[int]]:
    return {path: lines for path, lines in uses_in_our_code(name).items() if not may_use(BACKEND / path)}


@dataclass(frozen=True)
class Address:
    # One route of the address list, as Django holds it.
    path: str  # its address, as written in the lists: "api/v1/shops/^sides/(?P<pk>[^/.]+)/$"
    name: str | None  # its name, which reverse() turns back into an address: "side-detail"
    view: Callable[..., Any]  # what Django calls for it
    takes: frozenset[str]  # the parts its address takes: {"pk"}


def addresses(
    entries: Iterable[URLPattern | URLResolver] | None = None,
    prefix: str = "",
    namespace: str = "",
    takes: frozenset[str] = frozenset(),
) -> Iterator[Address]:
    # Every route of the address list in use (config/urls.py, unless a test switched ROOT_URLCONF), found by
    # walking it, through each include() into the lists it mounts, so a new app's routes are found with no
    # change here.
    for entry in get_resolver().url_patterns if entries is None else entries:
        parts = takes | frozenset(entry.pattern.regex.groupindex)
        if isinstance(entry, URLResolver):
            inner = f"{namespace}{entry.namespace}:" if entry.namespace else namespace
            yield from addresses(entry.url_patterns, prefix + str(entry.pattern), inner, parts)
        else:
            name = f"{namespace}{entry.name}" if entry.name else None
            yield Address(prefix + str(entry.pattern), name, entry.callback, parts)


@dataclass(frozen=True)
class Route:
    # One GET route of an office view, as the leak check calls it.
    name: str | None
    view: type[ShopViewSet[Any]]
    takes: frozenset[str]

    @property
    def lookup(self) -> str:
        # The part of a detail route's address that names the row: "pk" unless the view says otherwise.
        return self.view.lookup_url_kwarg or self.view.lookup_field

    @property
    def takes_row(self) -> bool:
        # A detail route takes one row's id; a list takes none.
        return self.lookup in self.takes


def shop_routes() -> list[Route]:
    # Every GET route of every office view: its list, its detail route, and any other GET route it adds
    # (DRF's @action). DRF's routers give a view one address for each, and note on it which action answers
    # which method (`actions`: {"get": "list", "post": "create"}).
    routes = []
    for address in addresses():
        view = getattr(address.view, "cls", None)
        actions = getattr(address.view, "actions", None) or {}
        if isinstance(view, type) and issubclass(view, ShopViewSet) and "get" in actions:
            routes.append(Route(address.name, view, address.takes))
    return routes


def ids_of(shop: Shop) -> set[str]:
    # Every id shop A has: its own, and every row's in every shop table installed, the probe's included. Read
    # past the guard on purpose, through Django's plain base manager with a filter by shop: the guard is what
    # is being checked, so it must not decide what counts as shop A's.
    ids = {str(shop.pk)}
    for table in apps.get_models():
        if issubclass(table, ShopScoped):
            ids |= {str(pk) for pk in table._base_manager.filter(shop_id=shop.pk).values_list("pk", flat=True)}
    return ids


def shown(response: HttpResponse, ids: set[str]) -> list[str]:
    # Any of shop A's ids anywhere in the answer: a row of the route's own table, a row of another table nested
    # in it, or a link's id. JSON writes a UUID just as str() does.
    text = response.content.decode()
    leaked = sorted(row_id for row_id in ids if row_id in text)
    return [f"shows shop A's ids {leaked}"] if leaked else []


def route_problems(client: APIClient, shop: Shop) -> dict[str, list[str]]:
    # 03 §5.4: no route, called as shop B, returns shop A's rows. `client` is logged in as a staff member of
    # shop B, and `shop` is shop A. A list must answer 200 and show none of A's ids, on every page. A detail
    # route, asked for each of A's rows by its id, must answer 404, "not found", as if the row didn't exist
    # (a 403 would tell shop B that it does), and show none of A's ids either.
    theirs = ids_of(shop)
    problems: dict[str, list[str]] = {}
    for route in shop_routes():
        found: list[str] = []
        table = route.view.model
        rows = [
            str(value)
            for value in table._base_manager.filter(shop_id=shop.pk).values_list(route.view.lookup_field, flat=True)
        ]
        if route.name is None or route.takes - {route.lookup}:
            # Every route DRF's routers make has a name and takes at most the row's id. A route nested under
            # another row would need that row too, which the sweep can't guess.
            found.append("no address the sweep can build: it needs a name, and no part but the row's id")
        elif not rows:
            # With no row of shop A in its own table, the route could leak and still pass.
            found.append(f"shop A has no {table._meta.label} rows to look for: add some in backend/tests/conftest.py")
        elif route.takes_row:
            for row in rows:
                response = client.get(reverse(route.name, kwargs={route.lookup: row}))
                if response.status_code != 404:
                    found.append(f"shop A's row {row}: answered {response.status_code}, not 404")
                found += shown(response, theirs)
        else:
            url: str | None = reverse(route.name)
            while url:
                response = client.get(url)
                if response.status_code != 200:
                    found.append(f"answered {response.status_code}, not 200")
                    break
                found += shown(response, theirs)
                # The next page's address, from the cursor pages (apps/core/api/pagination.py); None on the last.
                body = response.json()
                url = body.get("next") if isinstance(body, dict) else None
        if found:
            problems[route.name or "(no name)"] = found
    return problems


def side_field_problems(views: Iterable[type[ShopViewSet[Any]]]) -> list[str]:
    # The two side hooks of every office route (apps/core/api/base.py, PPL-3) find a row's side through
    # `side_field`: visible_sides() narrows every read by it, and check_side_permission() asks about the side it
    # names. A name the table doesn't have fails loudly, but None on a table that links a side fails quietly:
    # once PPL-3 hides sides, the route would still hand every side's rows to anyone of the shop. So each route
    # names its table's link: "pk" for the sides themselves, the link's own name on a table with one, and None
    # on a table of the whole shop. The hooks read the link's id (`<side_field>_id`), so only a direct link
    # counts: a many-to-many one, like PaymentAccount.sides, has no id of its own.
    problems = []
    # Each view once, though its list and its detail route both name it.
    for view in dict.fromkeys(views):
        table = view.model
        links = sorted(
            field.name
            for field in table._meta.concrete_fields
            if isinstance(field, models.ForeignKey) and label_of(field.remote_field.model) == "shops.Side"
        )
        expected: list[str | None]
        if table._meta.label == "shops.Side":
            expected = ["pk"]
        elif links:
            expected = list(links)
        else:
            expected = [None]
        if view.side_field not in expected:
            problems.append(
                f"{view.__name__}: side_field {view.side_field!r}, but {table._meta.label} needs {expected}"
            )
    return problems


def api_route_problems() -> list[str]:
    # The leak check can only call routes built on ShopViewSet: they name their table, and open the visit's
    # shop. A route under api/, where the app's routes live (03 §5.10), built on anything else would never be
    # checked, so it must be on NOT_SHOP_ROUTES, with its reason. Outside api/, the Django admin (/admin/) is
    # the superuser's alone, and reads through its own door (all_shops).
    problems = []
    for address in addresses():
        if not address.path.startswith("api/"):
            continue
        view = getattr(address.view, "cls", None)
        if not (isinstance(view, type) and (issubclass(view, ShopViewSet) or view in NOT_SHOP_ROUTES)):
            built_on = view.__name__ if isinstance(view, type) else "a plain Django view"
            problems.append(f"{address.path}: {built_on}, not a ShopViewSet")
    return problems


@contextmanager
def throwaway_tables() -> Iterator[Apps]:
    # A registry of its own for the tables a test builds to break a rule, so they never join the real list
    # that our_tables() reads, and vanish when the test ends. They are filed under the test-only probe app.
    with isolate_apps("tests.probe") as registry:
        assert registry is not None  # isolate_apps always hands one over; its type stubs allow None
        yield registry


# --- the checks find what they must -------------------------------------------------------------------------


def test_sweep_lists_every_kind_of_table() -> None:
    # Never passes on nothing: if our_tables() found no table, or missed the link tables Django makes by
    # itself, every check below would pass with nothing to look at.
    labels = {table._meta.label for table in our_tables()}

    assert {"shops.Shop", "shops.Side", "shops.Setting", "people.User", "people.StaffMember"} <= labels
    # The link tables Django makes for User. This also keeps INFRASTRUCTURE true: a name that no longer
    # exists would fail here.
    assert labels >= INFRASTRUCTURE
    # Not ours: Django's own tables, and the test-only probe app.
    assert not labels & {"auth.Group", "probe.Note"}


def test_shop_check_finds_tables_without_shop() -> None:
    with throwaway_tables() as registry:

        class Loose(UUIDModel):
            # Not built on ShopScoped: no shop, and no guard.
            class Meta:
                app_label = "probe"

        class ShopTakenAway(ShopScoped):
            shop = None  # type: ignore[assignment]  # removes the field ShopScoped gives

            class Meta:
                app_label = "probe"

        class ShopOptional(ShopScoped):
            # A row with no shop would belong to nobody, and no visit's guard would ever show it.
            shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, null=True, related_name="+")

            class Meta:
                app_label = "probe"

        class Kept(ShopScoped):
            # A table built the usual way passes.
            class Meta:
                app_label = "probe"

        assert shop_problems(registry.get_models()) == [
            "probe.Loose: not built on ShopScoped",
            "probe.ShopTakenAway: has no `shop`",
            "probe.ShopOptional: `shop` is not a required link to shops.Shop",
        ]


def test_link_check_finds_links_that_act_on_delete() -> None:
    with throwaway_tables() as registry:

        class Customer(ShopScoped):
            class Meta:
                app_label = "probe"

        class Debt(ShopScoped):
            # Deleting the customer would delete their debts too.
            customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="+")
            # Deleting the customer would leave the debts with nobody's name on them.
            guarantor = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, related_name="+")

            class Meta:
                app_label = "probe"

        class Tag(ShopScoped):
            class Meta:
                app_label = "probe"

        class Product(ShopScoped):
            # No `through` table of ours: Django makes one by itself, Product_tags, with two links that CASCADE.
            tags = models.ManyToManyField(Tag, related_name="+")

            class Meta:
                app_label = "probe"

        tables = registry.get_models(include_auto_created=True)

        assert sorted(link_problems(tables)) == [
            "probe.Debt.customer: CASCADE, not PROTECT",
            "probe.Debt.guarantor: SET_NULL, not PROTECT",
            "probe.Product_tags.product: CASCADE, not PROTECT",
            "probe.Product_tags.tag: CASCADE, not PROTECT",
        ]
        # And Django's link table has no shop: one table, two broken rules, both found.
        assert shop_problems(tables) == ["probe.Product_tags: not built on ShopScoped"]


@pytest.mark.django_db
def test_primary_key_check_finds_a_key_with_another_name() -> None:
    # As if the table had been renamed from probe_memo: the key keeps its old name. The rename happens inside
    # the test's own transaction, so PostgreSQL takes it back when the test ends, as it does any other change.
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE probe_note RENAME CONSTRAINT probe_note_pkey TO probe_memo_pkey")

    assert primary_key_problems([Note]) == ["probe.Note: primary key named ['probe_memo_pkey'], not probe_note_pkey"]


def test_guard_check_finds_tables_that_lose_the_guard() -> None:
    with throwaway_tables() as registry:

        class FreshBase(ShopScoped):
            # An abstract base whose Meta is not built on ShopScoped.Meta, as AppendOnly's must be.
            class Meta:
                abstract = True

        class OnFreshBase(FreshBase):
            # Gets `all_shops` as its default manager: every read through Django, the admin or DRF, unguarded.
            class Meta:
                app_label = "probe"

        class OwnObjects(ShopScoped):
            # A plain `objects` of its own, which replaces the guarded one under the same name. mypy refuses
            # this one too, as a type error; it can't see the other two ways, so the sweep checks all three.
            objects = models.Manager()  # type: ignore[assignment]

            class Meta(ShopScoped.Meta):
                app_label = "probe"

        class SecondDoor(ShopScoped):
            # The guard stays the default, but a plain manager beside it reads every shop.
            everything = models.Manager()

            class Meta(ShopScoped.Meta):
                app_label = "probe"

        class OnlyOwnMeta(ShopScoped):
            # Keeps the guard: a Meta of its own and no manager of its own (CORE-3's review).
            class Meta:
                app_label = "probe"

        assert guard_problems(registry.get_models()) == [
            "probe.OnFreshBase.all_shops: no guard (the default)",
            "probe.OwnObjects.objects: no guard (the default)",
            "probe.SecondDoor.everything: no guard",
        ]


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("all_shops", "sides = Side.all_shops.filter(code='D')"),
        ("system_context", "with system_context():\n    debts = Debt.objects.all()"),
        ("system_context", "from apps.core.tenancy import system_context"),
        # Under another name, the import still gives it away.
        ("system_context", "from apps.core.tenancy import system_context as open_all"),
        ("system_context", "from apps.core import tenancy\nopen_all = tenancy.system_context"),
    ],
)
def test_door_check_finds_every_use(name: str, code: str) -> None:
    assert uses_of(name, code) != []


def test_door_check_skips_comments_strings_and_the_definition() -> None:
    code = '''
"""A docstring may name system_context() and Side.all_shops."""
# So may a comment: system_context(), Side.all_shops.
all_shops = models.Manager()
'''
    assert uses_of("all_shops", code) == []
    assert uses_of("system_context", code) == []


def test_doors_are_allowed_only_in_their_places() -> None:
    assert may_use_all_shops(APPS / "shops" / "admin.py")
    assert not may_use_all_shops(APPS / "shops" / "api" / "views.py")
    assert may_use_system_context(APPS / "control" / "management" / "commands" / "check_balances.py")
    assert may_use_system_context(APPS / "control" / "tasks.py")
    assert not may_use_system_context(APPS / "shops" / "services.py")
    # An admin page answers a visit too: it has its own door, and never needs this one.
    assert not may_use_system_context(APPS / "shops" / "admin.py")
    # Tests may use both.
    assert may_use_all_shops(APPS / "core" / "tests" / "test_shop_scoped.py")
    assert may_use_system_context(APPS / "shops" / "tests" / "test_create_shop.py")


def test_door_check_reads_our_code() -> None:
    # Never passes on nothing: the scan reads our files, and finds both doors where CORE-2's own tests of them
    # use them today.
    assert "apps/core/tests/test_shop_scoped.py" in uses_in_our_code("all_shops")
    assert "apps/core/tests/test_shop_scoped.py" in uses_in_our_code("system_context")


def test_route_sweep_finds_the_side_routes() -> None:
    # Never passes on nothing: the sweep finds CORE-6's side routes by itself, the list and the detail.
    routes = {(route.name, route.takes_row) for route in shop_routes()}

    assert {("side-list", False), ("side-detail", True)} <= routes


@pytest.mark.django_db
def test_route_check_finds_a_route_that_leaks(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's address list (tests/probe/urls.py): notes read through the guard, and the same notes read
    # past it. One note in each shop.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_b, shop_a)

    # Only the leaky routes: the list shows shop A's note, and the detail route hands it over.
    assert sorted(problems) == ["leaky-note-detail", "leaky-note-list"]
    assert problems["leaky-note-detail"][0].endswith("answered 200, not 404")


@pytest.mark.django_db
def test_route_check_needs_rows_to_look_for(settings: Settings, shop_a: Shop, staff_client_b: APIClient) -> None:
    # With no note in shop A, even the leaky routes would show nothing of A's: a pass that proves nothing, so
    # the check refuses it.
    settings.ROOT_URLCONF = "tests.probe.urls"

    problems = route_problems(staff_client_b, shop_a)

    assert sorted(problems) == ["leaky-note-detail", "leaky-note-list", "note-detail", "note-list"]
    assert all("no probe.Note rows" in found[0] for found in problems.values())


def test_side_check_finds_routes_that_misname_the_side() -> None:
    class Locations(ShopViewSet[StockLocation]):
        # A location keeps its side in `side`, ShopViewSet's default: right.
        model = StockLocation

    class LocationsOfNoSide(ShopViewSet[StockLocation]):
        # Every side's stock to anyone of the shop, once PPL-3 hides sides.
        model = StockLocation
        side_field = None

    class AccountsBySide(ShopViewSet[PaymentAccount]):
        # An account has no direct link to a side (its sides are a many-to-many), so the default is wrong.
        model = PaymentAccount

    class Sides(ShopViewSet[Side]):
        model = Side
        side_field = "pk"

    class SidesBySide(ShopViewSet[Side]):
        # A side is its own side: it has no `side` link.
        model = Side

    assert side_field_problems([Locations, LocationsOfNoSide, AccountsBySide, Sides, SidesBySide]) == [
        "LocationsOfNoSide: side_field None, but shops.StockLocation needs ['side']",
        "AccountsBySide: side_field 'side', but shops.PaymentAccount needs [None]",
        "SidesBySide: side_field 'side', but shops.Side needs ['pk']",
    ]


def test_api_route_check_finds_a_route_off_the_base(settings: Settings) -> None:
    settings.ROOT_URLCONF = "tests.probe.urls"

    assert api_route_problems() == ["api/v1/probe/count/: a plain Django view, not a ShopViewSet"]


# --- the sweep ------------------------------------------------------------------------------------------------


def test_every_model_has_shop() -> None:
    assert shop_problems(our_tables()) == []


def test_every_foreign_key_protects() -> None:
    assert link_problems(our_tables()) == []


@pytest.mark.django_db
def test_every_primary_key_keeps_its_postgres_name() -> None:
    assert primary_key_problems(our_tables()) == []


def test_every_shop_table_keeps_the_guard() -> None:
    assert guard_problems(our_tables()) == []


def test_all_shops_only_in_admin() -> None:
    assert misplaced_uses("all_shops", may_use_all_shops) == {}


def test_system_context_only_in_system_code() -> None:
    assert misplaced_uses("system_context", may_use_system_context) == {}


@pytest.mark.django_db
def test_no_route_leaks_across_shops(sweep_shops: tuple[Shop, Shop], staff_client_b: APIClient) -> None:
    shop_a, shop_b = sweep_shops
    # The visitor really is shop B's: its side list shows shop B's own side. A login that failed on every
    # route would find nothing of shop A's anywhere, and pass.
    with shop_context(shop_b):
        own = {str(pk) for pk in Side.objects.values_list("pk", flat=True)}
    response = staff_client_b.get(reverse("side-list"))
    assert {row["id"] for row in response.json()["results"]} == own

    assert route_problems(staff_client_b, shop_a) == {}


def test_every_side_link_is_named_on_its_route() -> None:
    assert side_field_problems(route.view for route in shop_routes()) == []


def test_every_api_route_is_swept() -> None:
    assert api_route_problems() == []
