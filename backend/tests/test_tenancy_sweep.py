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

It also reads our code, as test_no_floats.py does, for the named ways to read every shop at once: the two
doors, `all_shops` for the superuser's admin pages and `system_context()` for system jobs (03 §5.4), and
Django's plain base manager, `_base_manager`. Each must stay in its own place; tests may use all three.
Until now only a search by hand found them. Raw SQL (`.raw()`, `connection.cursor()`) and a query built by
hand (`models.QuerySet(Side)`) read past the guard too, but a scan by name can't tell them from harmless
code, such as a sync cursor or a type: review watches for them, and row-level security, before a second
real shop, closes every way past the guard (ADR-0022).

And it walks the address list for every route of the office API, the routes built on ShopViewSet
(apps/core/api/base.py):

- called by a staff member of shop B, no route shows or touches any row of shop A: a list shows none of
  them, and a detail route answers about each one, to a read and to an edit alike, exactly as about an id
  no shop has (03 §5.4). Both shops are filled in backend/tests/conftest.py;
- each route names where its table keeps a row's side (`side_field`), for the per-side hooks (PPL-3);
- no route under api/ escapes the sweep by being built on something else.

A new table, file or route is checked with no change here, and this file must stay green without being edited
(backend rules). What changes instead lives beside it: the two shops' data, in backend/tests/conftest.py, and
the tables and routes allowed to break a rule, each with its reason, in backend/tests/sweep_lists.py. Each
check is a function that returns what breaks its rule, as in test_no_floats.py. The
tests of the checks hand them tables and code built to break the rule (the tables made in a throwaway
registry of their own, so they never join the real list), and a few tests make sure the real lists are not
empty, so the sweep can't pass by looking at nothing.
"""

import ast
import json
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
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
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.api.base import ShopViewSet
from apps.core.models import ShopScoped, ShopScopedManager, UUIDModel
from apps.core.tenancy import NoShopSelected, shop_context
from apps.shops.models import PaymentAccount, Shop, Side, StockLocation
from tests.probe.models import Note
from tests.sweep_lists import INFRASTRUCTURE, NO_SHOP, NOT_SHOP_ROUTES

BACKEND = Path(__file__).resolve().parents[1]
APPS = BACKEND / "apps"
CONFIG = BACKEND / "config"

# The most pages of one list the route sweep reads. A list that goes on longer has a cursor that never ends,
# and the sweep says so instead of hanging CI. The sweep's shops hold a few rows of each table, so each of
# their lists fits on its first page of 50 (REST_FRAMEWORK's PAGE_SIZE).
MAX_PAGES = 20


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
            # A table Django doesn't manage (`managed = False`), such as a view of the database a report reads
            # through, has no primary key of its own, and no create writes to it.
            if not table._meta.managed:
                continue
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


def in_module(path: Path, name: str) -> bool:
    # A module of an app, written as one file (admin.py) or as a package of files (admin/).
    return path.name == f"{name}.py" or name in path.relative_to(BACKEND).parts[:-1]


def may_use_all_shops(path: Path) -> bool:
    # The superuser's admin pages. A page answers a visit, and system_context() is for system jobs only, so
    # the admin has its own door, for its lists (apps/core/models.py).
    return in_module(path, "admin") or in_tests(path)


def may_use_system_context(path: Path) -> bool:
    # System jobs, which answer no visit: management commands (the nightly checks the scheduler runs, and
    # the demo seed, DATA-1) and background tasks (tasks, 03 §5.11). Never code that answers a visit, the
    # admin's pages included: a visit works for one shop (03 §5.4).
    folders = path.relative_to(BACKEND).parts[:-1]
    return folders[-2:] == ("management", "commands") or in_module(path, "tasks") or in_tests(path)


def may_use_base_manager(path: Path) -> bool:
    # Django's plain base manager reads every shop with no name to give it away, so app code never reads
    # through it by hand: following a link (`location.side`) and save() use it already, the way Django
    # means (apps/core/models.py). Tests may, to look past the guard on purpose.
    return in_tests(path)


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
    # One route of an office view, as the leak check calls it.
    name: str | None
    view: type[ShopViewSet[Any]]
    takes: frozenset[str]
    # The HTTP methods it answers, in small letters, as DRF notes them: {"get", "patch"}.
    methods: frozenset[str]

    @property
    def lookup(self) -> str:
        # The part of a detail route's address that names the row: "pk" unless the view says otherwise.
        return self.view.lookup_url_kwarg or self.view.lookup_field

    @property
    def takes_row(self) -> bool:
        # A detail route takes one row's id; a list takes none.
        return self.lookup in self.takes


def shop_routes() -> list[Route]:
    # Every route of every office view: its list, its detail route, and any other route it adds (DRF's
    # @action). DRF's routers give a view one address for each, and note on it which action answers which
    # method (`actions`: {"get": "list", "post": "create"}).
    routes = []
    for address in addresses():
        view = getattr(address.view, "cls", None)
        actions = getattr(address.view, "actions", None) or {}
        if isinstance(view, type) and issubclass(view, ShopViewSet) and actions:
            routes.append(Route(address.name, view, address.takes, frozenset(actions)))
    return routes


def shop_tables() -> list[type[models.Model]]:
    # Every table that holds a shop's rows: Shop, for the shop's own row, and every shop table installed, the
    # probe's included.
    return [Shop, *(table for table in apps.get_models() if issubclass(table, ShopScoped))]


def rows_of(table: type[models.Model], shop: Shop) -> models.QuerySet[Any]:
    # A shop's rows of one table, read past the guard on purpose, with a filter by shop: the guard is what is
    # being checked, so it must not decide what counts as shop A's. A query of its own, built on no manager of
    # the table's: even Django's base manager, plain by default, could be made a guarded one by a table's Meta
    # (base_manager_name), and the sweep, which opens no shop, would then crash.
    rows: models.QuerySet[Any] = models.QuerySet(table)
    if table is Shop:
        return rows.filter(pk=shop.pk)
    return rows.filter(shop_id=shop.pk)


def texts_of(table: type[models.Model], shop: Shop) -> set[str]:
    # The texts and amounts a shop's rows of one table hold. Dates and times are left out: JSON writes them in
    # a form of its own, and the rows' ids give every row away already.
    fields = [
        field.attname
        for field in table._meta.concrete_fields
        if isinstance(field, models.CharField | models.TextField | models.DecimalField)
    ]
    if not fields:
        return set()
    return {str(value) for row in rows_of(table, shop).values_list(*fields) for value in row if value not in (None, "")}


@dataclass(frozen=True)
class Marks:
    # What would give shop A away in an answer to shop B (03 §5.4).
    # The id of each of A's rows, and of A itself.
    ids: frozenset[str]
    # Each text or amount that A's rows hold and no row of B holds: a side's name ("Vyakula") today, a
    # customer's name or a debt's amount later. A leak with no ids, like a report of names and totals, still
    # shows those. An amount is a text in JSON too (ADR-0024).
    texts: frozenset[str]


def marks_of(shop_a: Shop, shop_b: Shop) -> Marks:
    # The two shops' data must give A values of its own (backend/tests/conftest.py).
    tables = shop_tables()
    ids = {str(pk) for table in tables for pk in rows_of(table, shop_a).values_list("pk", flat=True)}
    only_a = {text for table in tables for text in texts_of(table, shop_a)}
    only_a -= {text for table in tables for text in texts_of(table, shop_b)}
    return Marks(frozenset(ids), frozenset(only_a))


def is_json(response: HttpResponse) -> bool:
    return response.headers.get("Content-Type", "").startswith("application/json")


def shown(response: HttpResponse, marks: Marks) -> list[str]:
    # Any of shop A's marks anywhere in the answer: in a row of the route's own table, in a row of another table
    # nested in it, or in a link. Looked for in the answer's bytes as they were sent, so an answer of any kind
    # can be read: JSON, a CSV download, a PDF.
    # - An id, as it is: long and unique, it can't turn up by chance.
    # - A text, in a JSON answer: as JSON writes it, quotes and all ("Vyakula"), so a short one matches only a
    #   whole value: "F", A's side letter, never the F of "Fanta". ensure_ascii=False: the API writes a letter
    #   such as é as itself, not as an escape code (DRF's UNICODE_JSON setting).
    # - A text, in any other answer: as it is, since a CSV writes its texts with no quotes, but only when it is
    #   long enough, 4 characters or more, not to turn up by chance. So in a CSV, a side's letter goes unseen;
    #   its id and its name don't.
    in_json = is_json(response)
    needles = list(marks.ids)
    for text in marks.texts:
        if in_json:
            needles.append(json.dumps(text, ensure_ascii=False))
        elif len(text) >= 4:
            needles.append(text)
    leaked = sorted(needle for needle in needles if needle.encode() in response.content)
    return [f"shows what only shop A has: {', '.join(leaked)}"] if leaked else []


def send(client: APIClient, method: str, url: str, params: Mapping[str, str] | None = None) -> HttpResponse:
    # One request as the sweep sends it: a read with the route's query parameters, or a change sent empty.
    if method == "get":
        return client.get(url, params)
    change: Callable[..., HttpResponse] = getattr(client, method)
    return change(url, {}, format="json")


def answer(response: HttpResponse, key: str) -> tuple[int, bytes]:
    # What an answer tells the one who asked: its status and its body, with the key that was asked for taken
    # out, so that an answer that only repeats the key ("No note 0199… here") reads the same for every key.
    return response.status_code, response.content.replace(key.encode(), b"<key>")


def route_problems(
    client: APIClient, shop_a: Shop, shop_b: Shop, queries: Mapping[str, Mapping[str, str]] | None = None
) -> dict[str, list[str]]:
    # 03 §5.4: no route, called as shop B, returns shop A's rows. `client` is logged in as a staff member of
    # shop B. A list must answer 200 and show none of A's marks, on every page. A detail route, asked about
    # each of A's rows, must answer exactly as it answers about an id no shop has, the same status and the same
    # body, so the answer tells shop B nothing: usually a 404, "not found" (a 403 would tell B that the row
    # exists), or a 400 from a route that checks what was sent before it looks for the row. It must show none
    # of A's marks either.
    # `queries`: the query parameters some routes can't answer without, by route name, such as a day's report
    # and its date. They live with the two shops' data (sweep_queries, backend/tests/conftest.py), so that a
    # card adding such a route gives them there and leaves this file as it is.
    queries = queries or {}
    marks = marks_of(shop_a, shop_b)
    # How many routes carry each name, across the whole address list. The sweep builds a route's address from
    # its name (reverse()), and Django finds a name's last route only, so two routes with one name would be
    # one route called twice and one never called. config/urls.py mounts each app with no namespace, so two
    # apps' routers that pick the same basename meet.
    names = Counter(address.name for address in addresses() if address.name)
    problems: dict[str, list[str]] = {}
    for route in shop_routes():
        # What the sweep sends: a read (GET) to any route, and to a detail route each edit it takes as well. An
        # edit goes empty: an edit that finds no row answers the same whatever came with it, and one that checks
        # what was sent first refuses an empty one alike for every row. A delete goes last, so that a leaky one
        # can't hide what the edits before it would show. A route that only makes rows (POST) has nothing of
        # A's to ask for: CORE-6 already refuses an id another shop has (`id.taken`).
        writes = ("patch", "put", "delete") if route.takes_row else ()
        sends = [method for method in ("get", *writes) if method in route.methods]
        if not sends:
            continue
        found: list[str] = []
        table = route.view.model
        rows = [str(value) for value in rows_of(table, shop_a).values_list(route.view.lookup_field, flat=True)]
        if route.name is None or route.takes - {route.lookup}:
            # Every route DRF's routers make has a name and takes at most the row's id. A route nested under
            # another row would need that row too, which the sweep can't guess.
            found.append("no address the sweep can build: it needs a name, and no part but the row's id")
        elif names[route.name] > 1:
            found.append(
                f"{names[route.name]} routes have this name, and Django finds only one of them by it: give each its own"
            )
        elif not rows:
            # With no row of shop A in its own table, the route could leak and still pass.
            found.append(f"shop A has no {table._meta.label} rows to look for: add some in backend/tests/conftest.py")
        elif route.takes_row:
            # The keys shop B's own rows have. A route may find a row by a key of each shop's own instead of its
            # id, as a side could be found by its letter: then shop B, asking for A's "D", rightly gets its own
            # side D. Only a read is sent for such a key, and only A's marks are looked for in the answer: an
            # edit would change B's own row. A leaky route that crashes on such a key, having found both shops'
            # rows, still turns CI red: the test client raises the crash in the test.
            b_keys = {str(value) for value in rows_of(table, shop_b).values_list(route.view.lookup_field, flat=True)}
            for row in rows:
                row_url = reverse(route.name, kwargs={route.lookup: row})
                if row in b_keys:
                    found += shown(client.get(row_url, queries.get(route.name)), marks)
                    continue
                for method in sends:
                    response = send(client, method, row_url, queries.get(route.name))
                    # The same request about a row no shop has: an id made just now, which nothing can have.
                    nobody = str(uuid.uuid7())
                    control = send(
                        client, method, reverse(route.name, kwargs={route.lookup: nobody}), queries.get(route.name)
                    )
                    if response.status_code != control.status_code:
                        found.append(
                            f"shop A's row {row}: {method.upper()} answered {response.status_code}, but"
                            f" {control.status_code} for an id no shop has"
                        )
                    elif answer(response, row) != answer(control, nobody):
                        found.append(
                            f"shop A's row {row}: {method.upper()} answered {response.status_code}, as for an id"
                            " no shop has, but with another body"
                        )
                    found += shown(response, marks)
        else:
            url: str | None = reverse(route.name)
            # The route's own parameters go with the first page only: DRF builds the next page's address from
            # the one it answered, so that address carries them already.
            sent = queries.get(route.name)
            pages = 0
            while url:
                pages += 1
                if pages > MAX_PAGES:
                    found.append(f"more than {MAX_PAGES} pages: does its cursor ever end?")
                    break
                response = client.get(url, sent)
                sent = None
                if response.status_code == 400:
                    # The usual answer of a route that needs a parameter it wasn't given.
                    where = "give them in sweep_queries (backend/tests/conftest.py)"
                    found.append(f"answered 400, not 200: if it needs query parameters, {where}")
                    break
                if response.status_code != 200:
                    found.append(f"answered {response.status_code}, not 200")
                    break
                found += shown(response, marks)
                # The next page's address, from the cursor pages (apps/core/api/pagination.py); None on the last,
                # and on an answer that is not JSON, such as a CSV download, which comes whole.
                body = response.json() if is_json(response) else None
                url = body.get("next") if isinstance(body, dict) else None
        if found:
            problems[route.name or "(no name)"] = found
    return problems


def side_field_problems(views: Iterable[type[ShopViewSet[Any]]]) -> list[str]:
    # The two side hooks of every office route (apps/core/api/base.py, PPL-3) find a row's side through
    # `side_field`: visible_sides() narrows every read by it, and check_side_permission() asks about the side it
    # names. A wrong field mostly fails quietly:
    # - None on a table that links a side: once PPL-3 hides sides, the route would still hand every side's rows
    #   to anyone of the shop, and let anyone make rows on any side;
    # - a name the table doesn't have, on a create: side_of_new() looks for it in what was sent, finds nothing,
    #   and checks the new row as one of the whole shop. (On a read or an edit, side_of() fails loudly instead.)
    # So each route names its table's link: "pk" for the sides themselves, the link's own name on a table with
    # one, and None on a table of the whole shop. Every office view is checked, one that only makes rows too
    # (shop_routes() lists every route, whatever it answers). The hooks read the link's id (`<side_field>_id`),
    # so only a direct link counts: a many-to-many one, like PaymentAccount.sides, has no id of its own.
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
    # checked. So it must read no shop's table, and be on NOT_SHOP_ROUTES (backend/tests/sweep_lists.py) with
    # its reason; a route that reads one, such as sync's pull, is taught to the sweep instead. Outside api/,
    # the Django admin (/admin/) is the superuser's alone, and reads through its own door (all_shops).
    problems = []
    for address in addresses():
        # An address mounted the older way, with re_path(), is written as a regular expression and starts with
        # ^ ("^api/v1/…"), which marks its start: without the ^ it is an address like any other.
        if not address.path.lstrip("^").startswith("api/"):
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


@pytest.mark.django_db
def test_primary_key_check_skips_tables_django_does_not_manage() -> None:
    with throwaway_tables():

        class ReportRow(ShopScoped):
            # A view of the database, as a report could read through: Django makes no table for it, and it has
            # no primary key of its own. It still has `shop` and the guard, which the other checks ask for.
            class Meta:
                app_label = "probe"
                managed = False

        assert primary_key_problems([ReportRow]) == []


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

        class SkipsTheCheck(ShopScopedManager[Any]):
            # Built on the guard's own class, so it passes for the guard by its class alone, but it leaves out
            # the guard's check and reads every shop: only asking it to read with no shop open finds it out.
            def get_queryset(self) -> models.QuerySet[Any]:
                return models.QuerySet(self.model, using=self._db)

        class GuardThatSkips(ShopScoped):
            objects = SkipsTheCheck()

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
            "probe.GuardThatSkips.objects: no guard (the default)",
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
        ("_base_manager", "sides = Side._base_manager.filter(code='D')"),
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
    # A module may be a package of files too.
    assert may_use_all_shops(APPS / "shops" / "admin" / "sides.py")
    assert may_use_system_context(APPS / "control" / "tasks" / "nightly.py")
    # Django's plain base manager: tests only, not even the admin.
    assert not may_use_base_manager(APPS / "shops" / "selectors.py")
    assert not may_use_base_manager(APPS / "shops" / "admin.py")
    # Tests may use all three.
    assert may_use_all_shops(APPS / "core" / "tests" / "test_shop_scoped.py")
    assert may_use_system_context(APPS / "shops" / "tests" / "test_create_shop.py")
    assert may_use_base_manager(APPS / "core" / "tests" / "test_shop_scoped.py")


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
def test_sweep_reads_shop_a_rows_past_every_manager(monkeypatch: pytest.MonkeyPatch, shop_a: Shop) -> None:
    # The sweep finds shop A's rows with no shop open, through no manager of the table's: the guard is what it
    # checks, so no manager may decide what counts as A's. Even a table whose plain base manager was made the
    # guarded one (Meta.base_manager_name = "objects") is read. Note is made such a table for this test only:
    # monkeypatch puts its options back afterwards, the cached base manager too.
    Note(shop=shop_a, text="Note of shop A").save()
    monkeypatch.setattr(Note._meta, "base_manager_name", "objects")
    monkeypatch.delitem(Note._meta.__dict__, "base_manager", raising=False)
    with pytest.raises(NoShopSelected):
        Note._base_manager.all()

    assert [note.text for note in rows_of(Note, shop_a)] == ["Note of shop A"]


@pytest.mark.django_db
def test_route_check_finds_a_route_that_leaks(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's address list (tests/probe/urls.py): notes read through the guard, and the same notes read
    # past it. One note in each shop.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    # The leaky routes, and not the guarded ones: the list shows shop A's note, and the detail route hands it
    # over. (The probe's other routes are mounted awkwardly on purpose, for the tests below.)
    assert {"leaky-note-list", "leaky-note-detail"} <= problems.keys()
    assert not problems.keys() & {"note-list", "note-detail"}
    assert problems["leaky-note-detail"][0].endswith("GET answered 200, but 404 for an id no shop has")


@pytest.mark.django_db
def test_route_check_needs_rows_to_look_for(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # With no note in shop A, even the leaky routes would show nothing of A's: a pass that proves nothing, so
    # the check refuses it.
    settings.ROOT_URLCONF = "tests.probe.urls"

    problems = route_problems(staff_client_b, shop_a, shop_b)

    for name in ["leaky-note-detail", "leaky-note-list", "note-detail", "note-list"]:
        assert problems[name] == ["shop A has no probe.Note rows to look for: add some in backend/tests/conftest.py"]


@pytest.mark.django_db
def test_route_check_tells_every_route_apart(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's twin routes share one name, and Django finds a name's last route only: a sweep that called
    # routes by name alone would call the guarded twin twice and the leaky one never, and pass.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    twins = ["2 routes have this name, and Django finds only one of them by it: give each its own"]
    assert problems["twin-note-list"] == twins
    assert problems["twin-note-detail"] == twins
    # A list nested under another row, and a route with no name: the sweep can't build their addresses.
    no_address = ["no address the sweep can build: it needs a name, and no part but the row's id"]
    assert problems["nested-note-list"] == no_address
    assert problems["(no name)"] == no_address


@pytest.mark.django_db
def test_route_check_finds_a_leak_that_shows_no_ids(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's text-only leaky list shows every shop's notes with no ids, as a report of names and totals
    # would. Shop A's text, which no row of shop B holds, gives it away.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    assert problems["leaky-note-text-list"] == ['shows what only shop A has: "Note of shop A"']


@pytest.mark.django_db
def test_route_check_reads_answers_that_are_not_json(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's leaky export answers in CSV, as a report's download would: no JSON to read, and no quotes
    # around its texts. Shop A's text, as it is, gives it away.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    assert problems["leaky-note-export"] == ["shows what only shop A has: Note of shop A"]


@pytest.mark.django_db
def test_route_check_sends_the_parameters_a_route_needs(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's leaky search needs ?text=, as a day's report would need its date. Without it the route
    # answers 400 and shows nothing, so the sweep can't look, and says where to give the parameter.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    bare = route_problems(staff_client_b, shop_a, shop_b)
    given = route_problems(staff_client_b, shop_a, shop_b, queries={"leaky-note-search": {"text": "Note"}})

    assert bare["leaky-note-search"] == [
        "answered 400, not 200: if it needs query parameters, give them in sweep_queries (backend/tests/conftest.py)"
    ]
    # Given the parameter, the route answers, and its leak shows.
    assert given["leaky-note-search"][0].startswith('shows what only shop A has: "Note of shop A"')


@pytest.mark.django_db
def test_route_check_reports_a_list_it_cannot_look_in(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's closed list refuses shop B's staff member, as a list they had no permission for would. A
    # refusal shows nothing, so no leak shows either: a pass that proves nothing, so the sweep reports it.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    assert problems["closed-note-list"] == ["answered 403, not 200"]


@pytest.mark.django_db
def test_route_check_tries_edits_of_shop_a_rows(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # Shop B's edit of shop A's note must be answered as an edit of a note no shop has. The leaky route's edits
    # find it: its PATCH changes nothing and answers 200, and its PUT, sent with no text, is refused with a 400,
    # where a note no shop has gets a 404: either way B learns that A's note exists. The guarded route's edits
    # find nothing, A's note or not.
    settings.ROOT_URLCONF = "tests.probe.urls"
    note = Note(shop=shop_a, text="Note of shop A")
    note.save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    assert f"shop A's row {note.pk}: PATCH answered 200, but 404 for an id no shop has" in problems["leaky-note-detail"]
    assert f"shop A's row {note.pk}: PUT answered 400, but 404 for an id no shop has" in problems["leaky-note-detail"]
    assert "note-detail" not in problems


@pytest.mark.django_db
def test_route_check_takes_an_edit_that_checks_what_was_sent_first(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's form-first route refuses an empty edit with the same 400 whichever note it names, shop A's
    # or one that doesn't exist. That tells shop B nothing, though it is not a 404, so the route passes.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    assert "note-form-first-detail" not in problems


@pytest.mark.django_db
def test_route_check_lets_a_shared_key_answer_with_shop_b_row(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # The probe's notes-by-text route finds a note by its text, a key of each shop's own. Both shops have a
    # note "Shared": asked for it, shop B rightly gets its own, a 200 that gives nothing of A's away. Shop A's
    # other note is "not found", as it must be.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Shared").save()
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Shared").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    assert "note-by-text-detail" not in problems


@pytest.mark.django_db
def test_route_check_reads_every_page_and_stops(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_b: APIClient
) -> None:
    # Shop A's note is the oldest, and a full page of shop B's notes comes after it, so on the leaky list,
    # newest first, A's note is on the second page only.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    for number in range(settings.REST_FRAMEWORK["PAGE_SIZE"]):
        Note(shop=shop_b, text=f"Note {number} of shop B").save()

    problems = route_problems(staff_client_b, shop_a, shop_b)

    assert problems["leaky-note-list"][0].startswith('shows what only shop A has: "Note of shop A"')
    # The probe's endless list names itself as its next page, again and again: the sweep stops, and says so.
    assert problems["endless-note-list"] == [f"more than {MAX_PAGES} pages: does its cursor ever end?"]


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


def test_side_check_sees_routes_that_only_make_rows(settings: Settings) -> None:
    # The probe's note-makers route only makes notes, with no read at all, and names a side link a note doesn't
    # have. Found by itself among the probe's routes, it is checked like any other.
    settings.ROOT_URLCONF = "tests.probe.urls"

    problems = side_field_problems(route.view for route in shop_routes())

    assert problems == ["NoteMakerViewSet: side_field 'side', but probe.Note needs [None]"]


def test_api_route_check_finds_a_route_off_the_base(settings: Settings) -> None:
    # The probe's plain view, mounted twice: as a path, and the older way, as a regular expression from ^.
    settings.ROOT_URLCONF = "tests.probe.urls"

    assert api_route_problems() == [
        "api/v1/probe/count/: a plain Django view, not a ShopViewSet",
        "^api/v1/probe/raw-count/$: a plain Django view, not a ShopViewSet",
    ]


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


def test_base_manager_only_in_tests() -> None:
    assert misplaced_uses("_base_manager", may_use_base_manager) == {}


@pytest.mark.django_db
def test_no_route_leaks_across_shops(
    sweep_shops: tuple[Shop, Shop], sweep_queries: dict[str, dict[str, str]], staff_client_b: APIClient
) -> None:
    shop_a, shop_b = sweep_shops
    # The visitor really is shop B's: its side list shows shop B's own side. A login that failed on every
    # route would find nothing of shop A's anywhere, and pass.
    with shop_context(shop_b):
        own = {str(pk) for pk in Side.objects.values_list("pk", flat=True)}
    response = staff_client_b.get(reverse("side-list"))
    assert {row["id"] for row in response.json()["results"]} == own

    assert route_problems(staff_client_b, shop_a, shop_b, sweep_queries) == {}


def test_every_side_link_is_named_on_its_route() -> None:
    assert side_field_problems(route.view for route in shop_routes()) == []


def test_every_api_route_is_swept() -> None:
    assert api_route_problems() == []
