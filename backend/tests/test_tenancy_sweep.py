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

It also reads our code, as test_no_floats.py does, for every way past the guard it can name, each of which
must stay in its own place (tests may use them all): the two doors, `all_shops` for the superuser's admin
pages and `system_context()` for system jobs (03 §5.4); Django's plain base manager (`_base_manager`,
`_meta.base_manager`); and, found as calls, which the parser tells from a type or a plain name, raw SQL
(`.raw()`, `connection.cursor()`) and a query built by hand (`models.QuerySet(Side)`). Until now only a search
by hand found them. Code can still get past a scan, by a name made up at run time for one; review watches for
that, and row-level security, before a second real shop, closes every way past the guard (ADR-0022).

And it walks the address list for every route of the office API, the routes built on ShopViewSet
(apps/core/api/base.py):

- called by a staff member of shop A, each route shows A's own rows: otherwise what it shows shop B would
  prove nothing;
- called by a staff member of shop B, no route shows or touches any row of shop A: a list shows none of
  them, a create sent an id of A's hands nothing of A's back, and a detail route answers about each one, to
  a read, an edit, a POST (a void) and a delete alike, exactly as about an id no shop has (03 §5.4). Both
  shops are filled in backend/tests/conftest.py;
- each route names where its table keeps a row's side (`side_field`), for the per-side hooks (PPL-3);
- no route under api/ escapes the sweep by being built on something else.

A new table, file or route is checked with no change here. The checks are never loosened, nor edited, to let
something pass: what grows instead lives beside them, the two shops' data in backend/tests/conftest.py, and the
tables, routes and files allowed to break a rule, each with its reason, in backend/tests/sweep_lists.py.
Teaching the sweep something new, such as calling the sync routes with a device's key, is a new check, added
in a reviewed change (backend rules).

Each check is a function that returns what breaks its rule, as in test_no_floats.py. The tests of the checks
hand them tables, code and routes built to break the rule (the tables made in a throwaway registry of their
own, so they never join the real list; the routes in the test-only probe app), and a few tests make sure the
real lists are not empty, so the sweep can't pass by looking at nothing.
"""

import ast
import csv
import io
import json
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.apps import apps
from django.apps.registry import Apps
from django.core.exceptions import FieldDoesNotExist, MultipleObjectsReturned
from django.db import connection, models
from django.http import HttpResponseBase
from django.test.utils import isolate_apps
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone
from pytest_django import Settings
from rest_framework.test import APIClient

from apps.core.api.base import ShopViewSet
from apps.core.models import ShopScoped, ShopScopedManager, UUIDModel
from apps.core.tenancy import NoShopSelected, shop_context
from apps.shops.models import PaymentAccount, PaymentAccountKind, Shop, Side, StockLocation
from tests.probe.models import Note, VoidableEntry
from tests.sweep_lists import HAND_BUILT_QUERIES, INFRASTRUCTURE, NO_SHOP, NOT_SHOP_ROUTES, OWN_LEAK_TESTS

BACKEND = Path(__file__).resolve().parents[1]
APPS = BACKEND / "apps"
CONFIG = BACKEND / "config"
TESTS = BACKEND / "tests"

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
        # The database's views, as PostgreSQL lists them ("v", a view or a materialized view): a report may read
        # through one, and a view has no primary key of its own, and no create writes to it. Only views are
        # skipped: a table Django doesn't manage (`managed = False`) but which is a real table, such as a ledger
        # split in parts by hand, still takes creates, so its key is checked like any other.
        views = {info.name for info in connection.introspection.get_table_list(cursor) if info.type == "v"}
        for table in tables:
            if table._meta.db_table in views:
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
    # Django's plain base manager, `_base_manager` or `_meta.base_manager`, reads every shop with no name to
    # give it away, so app code never reads through it by hand: following a link (`location.side`) and save()
    # use it already, the way Django means (apps/core/models.py). Tests may, to look past the guard on purpose.
    return in_tests(path)


def may_use_raw_sql(path: Path) -> bool:
    # Raw SQL, `.raw(...)` or `connection.cursor()`, skips the guard's filter whatever manager it starts from:
    # `Side.objects.raw("SELECT ...")` reads every shop's sides even inside one shop's visit. Migrations run as
    # system jobs, with no visit; system jobs may read every shop anyway; tests may.
    folders = path.relative_to(BACKEND).parts[:-1]
    return "migrations" in folders or may_use_system_context(path)


def may_build_queries(path: Path) -> bool:
    # A query built by hand, `models.QuerySet(Side)`, starts from no manager, so from no guard. Tests may; app
    # code only in a file HAND_BUILT_QUERIES lists, with its reason (backend/tests/sweep_lists.py).
    return in_tests(path) or str(path.relative_to(BACKEND)) in HAND_BUILT_QUERIES


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


def calls_of(name: str, source: str) -> list[int]:
    # The lines where the code calls `name`: as a method (Side.objects.raw(...), connection.cursor()) or by
    # itself (QuerySet(Side)). Only a call counts: the parser tells it from a type (`models.QuerySet[Side]`) and
    # from a word that only names something, such as a sync pull's `cursor`.
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            called = node.func
            if (isinstance(called, ast.Attribute) and called.attr == name) or (
                isinstance(called, ast.Name) and called.id == name
            ):
                lines.append(node.lineno)
    return sorted(lines)


def uses_in_our_code(name: str, finder: Callable[[str, str], list[int]] = uses_of) -> dict[str, list[int]]:
    # Every Python file of our apps and of the settings, tests and migrations included: a migration that
    # opened every shop would be worth a look too. `finder`: uses_of, any use of the name, or calls_of, calls only.
    found = {}
    for path in sorted([*APPS.rglob("*.py"), *CONFIG.rglob("*.py")]):
        lines = finder(name, path.read_text(encoding="utf-8"))
        if lines:
            found[str(path.relative_to(BACKEND))] = lines
    return found


def misplaced_uses(
    name: str, may_use: Callable[[Path], bool], finder: Callable[[str, str], list[int]] = uses_of
) -> dict[str, list[int]]:
    return {path: lines for path, lines in uses_in_our_code(name, finder).items() if not may_use(BACKEND / path)}


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
    # The texts and amounts a shop's rows of one table hold, those that could tell one shop from another. Left
    # out, as they can't:
    # - a field's fixed choices ("cash_drawer", "mobile_money"): the same words in every shop, so a summary of
    #   shop B's own by kind would hold them too;
    # - a zero amount ("0.00"): any shop's total may be zero;
    # - dates and times: JSON writes them in a form of its own, and the rows' ids give every row away already.
    fields = [
        field.attname
        for field in table._meta.concrete_fields
        if isinstance(field, models.CharField | models.TextField | models.DecimalField) and not field.choices
    ]
    if not fields:
        return set()
    return {
        str(value)
        for row in rows_of(table, shop).values_list(*fields)
        for value in row
        if value not in (None, "") and not (isinstance(value, Decimal) and value == 0)
    }


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


@dataclass(frozen=True)
class Reply:
    # One answer as the sweep reads it: its status, its kind, and its body in bytes. Read once, right after the
    # request, because an answer sent in pieces can be read only once.
    status: int
    content_type: str
    body: bytes

    @property
    def kind(self) -> str:
        # The kind alone, without what follows it: "application/json" of "application/json; charset=utf-8".
        return self.content_type.split(";")[0].strip().lower()

    @property
    def is_json(self) -> bool:
        # JSON, or a kind built on it, such as "application/problem+json".
        return self.kind == "application/json" or self.kind.endswith("+json")

    @property
    def readable(self) -> bool:
        # What a search of the bytes can see into: JSON, text (a CSV, a page), and an empty answer. A PDF, an
        # Excel sheet or a ZIP squeezes its text (compression), and a picture holds none, so a search would find
        # nothing in them, shop A's rows or not.
        return not self.body or self.is_json or self.kind.startswith("text/")


def read(response: HttpResponseBase) -> Reply:
    # getvalue() reads either kind of answer whole: one made all at once (HttpResponse), and one sent in pieces
    # (StreamingHttpResponse, FileResponse), the usual way to send a file, which has no `.content`.
    return Reply(response.status_code, response.headers.get("Content-Type", ""), response.getvalue())


def leaks(reply: Reply, marks: Marks) -> list[str]:
    # Shop A's marks found anywhere in a readable answer: in a row of the route's own table, in a row of another
    # table nested in it, or in a link. Looked for in the answer's bytes as they were sent, so more than one kind
    # of answer can be read: JSON, a CSV download, a download sent in pieces, a page.
    # - An id, as it is: long and unique, it can't turn up by chance.
    # - A text, in a JSON answer: as JSON writes it, quotes and all ("Vyakula"), so a short one matches only a
    #   whole value: "F", A's side letter, never the F of "Fanta". The cost: a name inside a longer text, such
    #   as a label "Mbegu (MFANO)", is not found; the row's id, if the answer shows it, still is. Both ways of
    #   writing a letter such as é are looked for: as itself, as DRF writes it (its UNICODE_JSON setting), and
    #   as an escape code (\u00e9), as Django's own JsonResponse does.
    # - A text, in a CSV: as a whole cell, as the csv module reads the file, since a CSV writes its texts with
    #   no quotes. So A's amount "5000" is never found inside B's own "15000".
    # - A text, in any other answer (a page, plain text): as it is, but only when it is long enough, 4 characters
    #   or more, not to turn up by chance. So there a side's letter goes unseen; its id and its name don't.
    found = [row_id for row_id in marks.ids if row_id.encode() in reply.body]
    if reply.is_json:
        for text in marks.texts:
            found += [
                needle
                for needle in {json.dumps(text, ensure_ascii=False), json.dumps(text)}
                if needle.encode() in reply.body
            ]
    elif reply.kind == "text/csv":
        cells = {cell for line in csv.reader(io.StringIO(reply.body.decode(errors="replace"))) for cell in line}
        found += [text for text in marks.texts if text in cells]
    else:
        found += [text for text in marks.texts if len(text) >= 4 and text.encode() in reply.body]
    return sorted(found)


def shown(reply: Reply, marks: Marks) -> list[str]:
    # What an answer to shop B gives away of shop A's. An answer the sweep can't read, such as a PDF, is reported
    # instead: a search of it would pass whatever it holds.
    if not reply.readable:
        where = "give the route a leak test of its own, and name it in OWN_LEAK_TESTS (backend/tests/sweep_lists.py)"
        return [f"answers {reply.kind}, which the sweep can't read: {where}"]
    found = leaks(reply, marks)
    return [f"shows what only shop A has: {', '.join(found)}"] if found else []


def send(client: APIClient, method: str, url: str, params: Mapping[str, str] | None = None) -> Reply:
    # One request as the sweep sends it: a read with the route's query parameters, or a change sent empty.
    if method == "get":
        return read(client.get(url, params))
    change: Callable[..., HttpResponseBase] = getattr(client, method)
    return read(change(url, {}, format="json"))


def walk(client: APIClient, url: str, params: Mapping[str, str] | None) -> tuple[list[Reply], bool]:
    # A list's pages, read one after another: the answers, and whether the walk stopped at MAX_PAGES with more
    # to read. A page that doesn't answer 200 ends the walk. The route's own parameters go with the first page
    # only: DRF builds the next page's address from the one it answered, so that address carries them already.
    replies: list[Reply] = []
    next_url: str | None = url
    while next_url:
        if len(replies) == MAX_PAGES:
            return replies, True
        reply = send(client, "get", next_url, params)
        params = None
        replies.append(reply)
        if reply.status != 200:
            break
        # The next page's address, from the cursor pages (apps/core/api/pagination.py); None on the last, and on
        # an answer that is not JSON, such as a CSV download, which comes whole.
        body = json.loads(reply.body) if reply.is_json else None
        next_url = body.get("next") if isinstance(body, dict) else None
    return replies, False


def answer(reply: Reply, key: str) -> tuple[int, bytes]:
    # What an answer tells the one who asked: its status and its body, with the key that was asked for taken
    # out, so that an answer that only repeats the key ("No note 0199… here") reads the same for every key.
    return reply.status, reply.body.replace(key.encode(), b"<key>")


def own_problems(
    client_a: APIClient, url: str, params: Mapping[str, str] | None, marks: Marks, *, pages: bool
) -> list[str]:
    # Shop A's own staff must see A's rows through the route, before anything is asked of shop B. A route that
    # shows nothing to anyone, a broken one or a day's report asked for a day with no rows, shows shop B nothing
    # of A's too, and would pass every check below while proving nothing. A is only read, never changed: an edit
    # would change A's row. An answer the sweep can't read is left to shop B's check, which reports it.
    replies = walk(client_a, url, params)[0] if pages else [send(client_a, "get", url, params)]
    last = replies[-1]
    if last.status == 400 and len(replies) == 1:
        # The usual answer of a route that needs a parameter it wasn't given.
        return [
            "shop A's own staff got 400 here: if it needs query parameters, give them in sweep_queries"
            " (backend/tests/conftest.py)"
        ]
    if last.status != 200:
        return [f"shop A's own staff got {last.status} here, so shop B's answers would prove nothing"]
    if any(not reply.readable or leaks(reply, marks) for reply in replies):
        return []
    return [
        "shop A's own staff sees nothing of A's here, so shop B's answers would prove nothing: give the route"
        " rows of A's to show, and the query parameters it needs (backend/tests/conftest.py)"
    ]


def detail_problems(
    client_b: APIClient,
    route: Route,
    name: str,
    sends: list[str],
    keys: tuple[list[str], set[str]],
    params: Mapping[str, str] | None,
    marks: Marks,
) -> list[str]:
    # Shop B's requests about each of A's rows, each answered exactly as the same request about an id no shop
    # has. `keys`: A's rows' keys, and the keys B's own rows have. A route may find a row by a key of each shop's
    # own instead of its id, as a side could be found by its letter: then shop B, asking for A's "D", rightly
    # gets its own side D. Only a read is sent for such a key, and only A's marks are looked for in the answer:
    # a change would change B's own row. A leaky route that crashes on such a key, having found both shops'
    # rows, still turns CI red: the test client raises the crash in the test.
    found: list[str] = []
    rows, b_keys = keys
    takes_changes = any(method != "get" for method in sends)
    if takes_changes and all(row in b_keys for row in rows):
        # Only reads for shared keys: with every key of A's shared, no change by key is ever tried, a void as
        # much as an edit, and a leaky one would pass unseen. (A route that only reads needs nothing more.)
        found.append(
            "every key of shop A's rows is shop B's too, so no change could be tried: give shop A a row with a key"
            " of its own (backend/tests/conftest.py)"
        )
    for row in rows:
        row_url = reverse(name, kwargs={route.lookup: row})
        if row in b_keys:
            if "get" in sends:
                found += shown(send(client_b, "get", row_url, params), marks)
            continue
        for method in sends:
            reply = send(client_b, method, row_url, params)
            # The same request about a row no shop has: an id made just now, which nothing can have.
            nobody = str(uuid.uuid7())
            control = send(client_b, method, reverse(name, kwargs={route.lookup: nobody}), params)
            if reply.status != control.status:
                found.append(
                    f"shop A's row {row}: {method.upper()} answered {reply.status}, but {control.status} for an id"
                    " no shop has"
                )
            elif answer(reply, row) != answer(control, nobody):
                found.append(
                    f"shop A's row {row}: {method.upper()} answered {reply.status}, as for an id no shop has, but"
                    " with another body"
                )
            found += shown(reply, marks)
    return found


def list_problems(
    client_b: APIClient, name: str, sends: list[str], a_ids: list[str], params: Mapping[str, str] | None, marks: Marks
) -> list[str]:
    # Shop B's requests to a list: a read, page after page, each page answering 200 and showing none of A's
    # marks; and a create sent nothing but an id of A's, which must hand nothing of A's back. The create's status
    # is not asked: one that needs no more than an id may make a row for an id no shop has, and refuse A's with
    # `id.taken` (CORE-6), which reveals nothing about A's row.
    found: list[str] = []
    if "get" in sends:
        replies, cut = walk(client_b, reverse(name), params)
        for reply in replies:
            if reply.status != 200:
                found.append(f"answered {reply.status}, not 200")
            else:
                found += shown(reply, marks)
        if cut:
            found.append(f"more than {MAX_PAGES} pages: does its cursor ever end?")
    if "post" in sends:
        for row_id in a_ids:
            reply = read(client_b.post(reverse(name), {"id": row_id}, format="json"))
            found += [f"POST with shop A's id {row_id}: {problem}" for problem in shown(reply, marks)]
    return found


def route_problems(
    client_a: APIClient,
    client_b: APIClient,
    shop_a: Shop,
    shop_b: Shop,
    queries: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, list[str]]:
    # 03 §5.4: no route, called as shop B, returns shop A's rows. `client_b` is logged in as a staff member of
    # shop B, and `client_a` as one of shop A, whose own look comes first: A must see its own rows through the
    # route (own_problems), or B's answers prove nothing. Then shop B: a list must answer 200 and show none of
    # A's marks, on every page. A detail route, asked about each of A's rows, must answer exactly as it answers
    # about an id no shop has, the same status and the same body, so the answer tells shop B nothing: usually a
    # 404, "not found" (a 403 would tell B that the row exists), or a 400 from a route that checks what was sent
    # before it looks for the row. It must show none of A's marks either.
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
        if route.name in OWN_LEAK_TESTS:
            # A route whose answers the sweep can't read, such as a PDF: its own test proves it shows nothing of
            # another shop's (backend/tests/sweep_lists.py), and test_every_route_left_to_its_own_test_has_one
            # checks that the test exists.
            continue
        # What the sweep sends:
        # - to a detail route, each request it takes, about each of A's rows: a read (GET), an edit (PATCH,
        #   PUT), a POST, which is how a void or a cancel will come, since nothing is deleted or replaced (03
        #   §5.10), and a DELETE, last, so that a leaky one can't hide what the requests before it would show.
        #   A change goes empty: one that finds no row answers the same whatever came with it, and one that
        #   checks what was sent first refuses an empty one alike for every row;
        # - to a list, a read (GET), and a create (POST) sent nothing but the id of one of A's rows: a create
        #   hands back the row it made before for an id it is sent again (CORE-6), so a leaky one hands A's.
        # A route may take a request the sweep has none of, such as a DELETE on a whole list: it says so, rather
        # than pass the route by.
        sends: list[str]
        if route.takes_row:
            sends = [method for method in ("get", "patch", "put", "post", "delete") if method in route.methods]
        else:
            sends = [method for method in ("get", "post") if method in route.methods]
        found: list[str] = []
        # HEAD is a GET with no body: DRF answers it with the GET's action, adding it to the route's actions at
        # its first GET, and the sweep's GET covers it.
        unsent = ", ".join(method.upper() for method in sorted(route.methods - set(sends) - {"head"}))
        if unsent:
            found.append(f"answers {unsent}, which the sweep doesn't send here: teach it, in a reviewed change")
        table = route.view.model
        rows = [str(value) for value in rows_of(table, shop_a).values_list(route.view.lookup_field, flat=True)]
        if not sends:
            pass  # nothing the sweep can send: only what is reported above
        elif route.name is None or route.takes - {route.lookup}:
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
        else:
            params = queries.get(route.name)
            own: list[str] = []
            if "get" in sends:
                # A detail route is looked at through A's first row; a list, page after page.
                own_url = (
                    reverse(route.name, kwargs={route.lookup: rows[0]}) if route.takes_row else reverse(route.name)
                )
                own = own_problems(client_a, own_url, params, marks, pages=not route.takes_row)
            found += own
            if own:
                pass  # shop A's own look failed: shop B's answers would prove nothing
            elif route.takes_row:
                b_keys = {
                    str(value) for value in rows_of(table, shop_b).values_list(route.view.lookup_field, flat=True)
                }
                found += detail_problems(client_b, route, route.name, sends, (rows, b_keys), params, marks)
            else:
                a_ids = [str(pk) for pk in rows_of(table, shop_a).values_list("pk", flat=True)]
                found += list_problems(client_b, route.name, sends, a_ids, params, marks)
        if found:
            # Each problem once: a detail route's rows can give the same one several times.
            problems[route.name or "(no name)"] = list(dict.fromkeys(found))
    return problems


def names_of_tests() -> set[str]:
    # The name of every test function in our tests: the apps' tests/ folders and backend/tests/.
    names = set()
    for path in [*APPS.rglob("test_*.py"), *TESTS.rglob("test_*.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names |= {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    return {name for name in names if name.startswith("test_")}


def own_leak_test_problems() -> list[str]:
    # A route left to a leak test of its own (OWN_LEAK_TESTS) must still exist, and so must its test: a stale
    # name on either side would leave a route that nothing checks.
    routes = {route.name for route in shop_routes()}
    tests = names_of_tests()
    problems = []
    for route_name, test_name in sorted(OWN_LEAK_TESTS.items()):
        if route_name not in routes:
            problems.append(f"{route_name}: no office route has this name")
        if test_name not in tests:
            problems.append(f"{route_name}: no test is named {test_name}")
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
def test_primary_key_check_skips_database_views_only() -> None:
    # Two tables Django doesn't manage (managed = False), each made here by hand, inside the test's transaction,
    # which PostgreSQL takes back at its end. A view, which a report could read through, has no primary key of
    # its own, and no create writes to it: skipped. A real table made by hand, as a ledger split in parts could
    # be, still takes creates, so its key is checked like any other.
    with connection.cursor() as cursor:
        cursor.execute("CREATE VIEW probe_reportrow AS SELECT id, shop_id, created_at, created_by_id FROM probe_note")
        cursor.execute("CREATE TABLE probe_ledgerpart (id uuid CONSTRAINT probe_ledger_key PRIMARY KEY)")

    with throwaway_tables():

        class ReportRow(ShopScoped):
            class Meta:
                app_label = "probe"
                managed = False

        class LedgerPart(UUIDModel):
            class Meta:
                app_label = "probe"
                managed = False

        assert primary_key_problems([ReportRow, LedgerPart]) == [
            "probe.LedgerPart: primary key named ['probe_ledger_key'], not probe_ledgerpart_pkey"
        ]


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
        # The same door under another name.
        ("base_manager", "sides = Side._meta.base_manager.filter(code='D')"),
    ],
)
def test_door_check_finds_every_use(name: str, code: str) -> None:
    assert uses_of(name, code) != []


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("raw", "sides = Side.objects.raw('SELECT * FROM shops_side')"),
        ("cursor", "with connection.cursor() as cursor:\n    cursor.execute('SELECT 1')"),
        ("QuerySet", "sides = models.QuerySet(Side)"),
    ],
)
def test_call_check_finds_every_call(name: str, code: str) -> None:
    assert calls_of(name, code) != []


def test_call_check_skips_types_and_plain_names() -> None:
    # A type is not a call, and neither is a word that only names something, such as a sync pull's cursor.
    code = """
def visible(rows: models.QuerySet[Side]) -> models.QuerySet[Side]:
    cursor = request.query_params["cursor"]
    return rows.filter(code=cursor)
"""
    assert calls_of("QuerySet", code) == []
    assert calls_of("cursor", code) == []


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
    # Raw SQL: migrations, system jobs and tests, never code that answers a visit.
    assert may_use_raw_sql(APPS / "shops" / "migrations" / "0006_fill_codes.py")
    assert may_use_raw_sql(APPS / "control" / "management" / "commands" / "check_balances.py")
    assert not may_use_raw_sql(APPS / "shops" / "selectors.py")
    # A query built by hand: tests, and the files HAND_BUILT_QUERIES lists with their reason.
    assert may_build_queries(APPS / "core" / "api" / "base.py")
    assert not may_build_queries(APPS / "shops" / "api" / "views.py")


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
def test_marks_leave_out_choice_words_and_zero_amounts(shop_a: Shop, shop_b: Shop) -> None:
    # A word from a field's fixed choices ("mobile_money") is the same in every shop, and any shop's amount can be
    # zero: neither can give shop A away, and either, taken as A's, would fail a summary of B's own that held it.
    PaymentAccount(
        shop=shop_a, kind=PaymentAccountKind.MOBILE_MONEY, name="Lipa Namba", provider="Pesa Demo", number="000111"
    ).save()
    VoidableEntry(shop_id=shop_a.pk, amount=Decimal("1500.00")).save()

    texts = marks_of(shop_a, shop_b).texts

    assert {"Lipa Namba", "Pesa Demo", "000111", "1500.00"} <= texts
    assert not texts & {"mobile_money", "0.00"}


@pytest.mark.django_db
def test_sweep_reads_shop_a_rows_past_every_manager(monkeypatch: pytest.MonkeyPatch, shop_a: Shop) -> None:
    # The sweep finds shop A's rows with no shop open, through no manager of the table's: the guard is what it
    # checks, so no manager may decide what counts as A's. Even a table whose plain base manager was made the
    # guarded one (Meta.base_manager_name = "objects") is read. Note is made such a table for this test only.
    # Django works the base manager out once and keeps it in the table's options, so the guarded one is put there
    # directly: setitem puts back what was kept before, or takes it away if nothing was, and Note is left as the
    # test found it, whatever ran before it. (Taking the kept one away instead left the guarded one behind for
    # the rest of the run, when nothing had been kept yet.)
    Note(shop=shop_a, text="Note of shop A").save()
    monkeypatch.setattr(Note._meta, "base_manager_name", "objects")
    monkeypatch.setitem(vars(Note._meta), "base_manager", Note._meta.managers_map["objects"])
    with pytest.raises(NoShopSelected):
        Note._base_manager.all()

    assert [note.text for note in rows_of(Note, shop_a)] == ["Note of shop A"]


@pytest.mark.django_db
def test_route_check_finds_a_route_that_leaks(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's address list (tests/probe/urls.py): notes read through the guard, and the same notes read
    # past it. One note in each shop.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    # The leaky routes, and not the guarded ones: the list shows shop A's note, and the detail route hands it
    # over. (The probe's other routes are mounted awkwardly on purpose, for the tests below.)
    assert {"leaky-note-list", "leaky-note-detail"} <= problems.keys()
    assert not problems.keys() & {"note-list", "note-detail"}
    assert problems["leaky-note-detail"][0].endswith("GET answered 200, but 404 for an id no shop has")


@pytest.mark.django_db
def test_route_check_needs_rows_to_look_for(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # With no note in shop A, even the leaky routes would show nothing of A's: a pass that proves nothing, so
    # the check refuses it.
    settings.ROOT_URLCONF = "tests.probe.urls"

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    for name in ["leaky-note-detail", "leaky-note-list", "note-detail", "note-list"]:
        assert problems[name] == ["shop A has no probe.Note rows to look for: add some in backend/tests/conftest.py"]


@pytest.mark.django_db
def test_route_check_tells_every_route_apart(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's twin routes share one name, and Django finds a name's last route only: a sweep that called
    # routes by name alone would call the guarded twin twice and the leaky one never, and pass.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    twins = ["2 routes have this name, and Django finds only one of them by it: give each its own"]
    assert problems["twin-note-list"] == twins
    assert problems["twin-note-detail"] == twins
    # A list nested under another row, and a route with no name: the sweep can't build their addresses.
    no_address = ["no address the sweep can build: it needs a name, and no part but the row's id"]
    assert problems["nested-note-list"] == no_address
    assert problems["(no name)"] == no_address


@pytest.mark.django_db
def test_route_check_finds_a_leak_that_shows_no_ids(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's text-only leaky list shows every shop's notes with no ids, as a report of names and totals
    # would. Shop A's text, which no row of shop B holds, gives it away.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    # Its list's read shows A's text with no id. (Its create, sent A's id, hands the note back too.)
    assert 'shows what only shop A has: "Note of shop A"' in problems["leaky-note-text-list"]


@pytest.mark.django_db
def test_route_check_reads_answers_that_are_not_json(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's leaky export answers in CSV, as a report's download would: no JSON to read, and no quotes
    # around its texts. Shop A's text, as it is, gives it away.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert problems["leaky-note-export"] == ["shows what only shop A has: Note of shop A"]


@pytest.mark.django_db
def test_route_check_reads_json_written_with_escape_codes(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's leaky plain-JSON route answers through Django's JsonResponse, which writes the é of shop A's
    # note as an escape code. The sweep reads a text in either form.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Café of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert problems["leaky-note-plain"] == ['shows what only shop A has: "Caf\\u00e9 of shop A"']


@pytest.mark.django_db
def test_route_check_reads_a_csv_cell_by_cell(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # Shop A's amount "5000" sits inside shop B's own "15000". In a CSV, the sweep compares whole cells, so the
    # probe's guarded export, which shows B only its own "15000", is not taken for a leak.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="5000").save()
    Note(shop=shop_b, text="15000").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert "note-export" not in problems
    # The leaky export, which shows B both, still gives A's away.
    assert problems["leaky-note-export"][0].startswith("shows what only shop A has: 5000")


@pytest.mark.django_db
def test_route_check_reads_a_download_sent_in_pieces(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # A file usually goes out in pieces (StreamingHttpResponse, FileResponse), an answer with no `.content`. The
    # sweep reads it all the same: the probe's guarded download passes, and the leaky one shows A's note.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert "note-stream" not in problems
    assert problems["leaky-note-stream"] == ["shows what only shop A has: Note of shop A"]


@pytest.mark.django_db
def test_route_check_reports_an_answer_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    shop_a: Shop,
    shop_b: Shop,
    staff_client_a: APIClient,
    staff_client_b: APIClient,
) -> None:
    # The probe's report answers a PDF: its text is squeezed, so no search finds shop A's names in it, and a pass
    # would prove nothing. The sweep says so, and names the way out.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert problems["note-report-pdf"] == [
        "answers application/pdf, which the sweep can't read: give the route a leak test of its own, and name it"
        " in OWN_LEAK_TESTS (backend/tests/sweep_lists.py)"
    ]
    # Named there, with its own leak test, the route is left to that test. (This test stands in for it.)
    monkeypatch.setitem(OWN_LEAK_TESTS, "note-report-pdf", "test_route_check_reports_an_answer_it_cannot_read")
    assert "note-report-pdf" not in route_problems(staff_client_a, staff_client_b, shop_a, shop_b)


def test_own_leak_test_check_finds_stale_names(monkeypatch: pytest.MonkeyPatch) -> None:
    # A route left to a test nobody wrote, and a test named for a route that is gone: either way, nothing checks.
    monkeypatch.setitem(OWN_LEAK_TESTS, "side-list", "test_that_nobody_wrote")
    monkeypatch.setitem(OWN_LEAK_TESTS, "gone-list", "test_no_route_leaks_across_shops")

    assert own_leak_test_problems() == [
        "gone-list: no office route has this name",
        "side-list: no test is named test_that_nobody_wrote",
    ]


@pytest.mark.django_db
def test_route_check_sends_the_parameters_a_route_needs(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's leaky search needs ?text=, as a day's report would need its date. Without it the route
    # answers 400 and shows nothing, even to shop A's own staff, so the sweep can't look, and says where to give
    # the parameter.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Note of shop B").save()

    bare = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)
    given = route_problems(
        staff_client_a, staff_client_b, shop_a, shop_b, queries={"leaky-note-search": {"text": "Note"}}
    )

    assert bare["leaky-note-search"] == [
        "shop A's own staff got 400 here: if it needs query parameters, give them in sweep_queries"
        " (backend/tests/conftest.py)"
    ]
    # Given the parameter, the route answers, and its leak shows.
    assert given["leaky-note-search"][0].startswith('shows what only shop A has: "Note of shop A"')


@pytest.mark.django_db
def test_route_check_needs_shop_a_to_see_its_own_rows(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's diary shows the notes of one day, as a day's report will. Asked for a day with no notes, it
    # shows shop B nothing of A's, but shows A nothing either: a pass that proves nothing, so the sweep, whose
    # first look is as shop A's own staff, reports it. Asked for the day the notes were made, today, it passes.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    wrong_day = route_problems(staff_client_a, staff_client_b, shop_a, shop_b, {"diary-day": {"date": "2026-01-01"}})
    today = route_problems(
        staff_client_a, staff_client_b, shop_a, shop_b, {"diary-day": {"date": str(timezone.localdate())}}
    )

    assert wrong_day["diary-day"] == [
        "shop A's own staff sees nothing of A's here, so shop B's answers would prove nothing: give the route rows"
        " of A's to show, and the query parameters it needs (backend/tests/conftest.py)"
    ]
    assert "diary-day" not in today


@pytest.mark.django_db
def test_route_check_reports_a_list_it_cannot_look_in(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's closed list refuses shop B's staff member, as a list they had no permission for would. A
    # refusal shows nothing, so no leak shows either: a pass that proves nothing, so the sweep reports it.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert problems["closed-note-list"] == ["answered 403, not 200"]


@pytest.mark.django_db
def test_route_check_tries_edits_of_shop_a_rows(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # Shop B's edit of shop A's note must be answered as an edit of a note no shop has. The leaky route's edits
    # find it: its PATCH changes nothing and answers 200, and its PUT, sent with no text, is refused with a 400,
    # where a note no shop has gets a 404: either way B learns that A's note exists. The guarded route's edits
    # find nothing, A's note or not.
    settings.ROOT_URLCONF = "tests.probe.urls"
    note = Note(shop=shop_a, text="Note of shop A")
    note.save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert f"shop A's row {note.pk}: PATCH answered 200, but 404 for an id no shop has" in problems["leaky-note-detail"]
    assert f"shop A's row {note.pk}: PUT answered 400, but 404 for an id no shop has" in problems["leaky-note-detail"]
    assert "note-detail" not in problems


@pytest.mark.django_db
def test_route_check_sends_a_delete_last(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's delete routes, in an address list of their own (tests/probe/urls_delete.py). Through the guard,
    # shop B's DELETE finds no note of A's; past it, it deletes A's note, answering 204 where a note no shop has
    # gets a 404. The DELETE goes last of the route's requests, so the read and the edits before it found the
    # note still there, and were caught too.
    settings.ROOT_URLCONF = "tests.probe.urls_delete"
    note = Note(shop=shop_a, text="Note of shop A")
    note.save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    leaky = problems["leaky-deletable-note-detail"]
    assert f"shop A's row {note.pk}: DELETE answered 204, but 404 for an id no shop has" in leaky
    assert f"shop A's row {note.pk}: GET answered 200, but 404 for an id no shop has" in leaky
    assert "deletable-note-detail" not in problems


@pytest.mark.django_db
def test_a_crash_on_a_shared_key_turns_the_sweep_red(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's leaky route finds a note by its text past the guard (tests/probe/urls_crash.py). Both shops have
    # a note "Shared", so it finds two, and crashes. The sweep doesn't catch the crash: the test client raises
    # it in the test, so CI goes red, in Django's words rather than the sweep's.
    settings.ROOT_URLCONF = "tests.probe.urls_crash"
    Note(shop=shop_a, text="Shared").save()
    Note(shop=shop_b, text="Shared").save()

    with pytest.raises(MultipleObjectsReturned):
        route_problems(staff_client_a, staff_client_b, shop_a, shop_b)


@pytest.mark.django_db
def test_route_check_takes_an_edit_that_checks_what_was_sent_first(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's form-first route refuses an empty edit with the same 400 whichever note it names, shop A's
    # or one that doesn't exist. That tells shop B nothing, though it is not a 404, so the route passes.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert "note-form-first-detail" not in problems


@pytest.mark.django_db
def test_route_check_sends_posts_too(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # A void or a cancel will be a POST on one row, since nothing is deleted or replaced (03 §5.10), and a create
    # hands back the row it made before for an id it is sent again (CORE-6). The probe's leaky void acts on shop
    # A's note, and its leaky create hands that note to shop B, who sent nothing but its id.
    settings.ROOT_URLCONF = "tests.probe.urls"
    note = Note(shop=shop_a, text="Note of shop A")
    note.save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert f"shop A's row {note.pk}: POST answered 200, but 404 for an id no shop has" in problems["leaky-note-void"]
    assert any(
        found.startswith(f"POST with shop A's id {note.pk}: shows what") for found in problems["leaky-note-list"]
    )
    # The guarded routes give nothing away: the void finds no note, and the create, sent an id alone, makes none.
    assert not problems.keys() & {"note-void", "note-list"}
    # A request the sweep has none of, such as a DELETE sent to a whole list, is reported, not passed by.
    assert problems["note-bulk-clear"] == [
        "answers DELETE, which the sweep doesn't send here: teach it, in a reviewed change"
    ]


@pytest.mark.django_db
def test_route_check_lets_a_shared_key_answer_with_shop_b_row(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # The probe's notes-by-text route finds a note by its text, a key of each shop's own. Both shops have a
    # note "Shared": asked for it, shop B rightly gets its own, a 200 that gives nothing of A's away. Shop A's
    # other note is "not found", as it must be.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Shared").save()
    Note(shop=shop_a, text="Note of shop A").save()
    Note(shop=shop_b, text="Shared").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    assert "note-by-text-detail" not in problems


@pytest.mark.django_db
def test_route_check_needs_a_key_only_shop_a_has(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # If every key of shop A's rows is shop B's too, the sweep only reads, and never tries a change by key: a
    # change would land on B's own row. A leaky edit by key would then pass unseen, so the sweep says so.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Shared").save()
    Note(shop=shop_b, text="Shared").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

    every_key_shared = [
        "every key of shop A's rows is shop B's too, so no change could be tried: give shop A a row with a key of"
        " its own (backend/tests/conftest.py)"
    ]
    assert problems["note-by-text-detail"] == every_key_shared
    # And a route whose only change is a POST on one row, a void by key.
    assert problems["note-by-text-void"] == every_key_shared


@pytest.mark.django_db
def test_route_check_reads_every_page_and_stops(
    settings: Settings, shop_a: Shop, shop_b: Shop, staff_client_a: APIClient, staff_client_b: APIClient
) -> None:
    # Shop A's note is the oldest, and a full page of shop B's notes comes after it, so on the leaky list,
    # newest first, A's note is on the second page only.
    settings.ROOT_URLCONF = "tests.probe.urls"
    Note(shop=shop_a, text="Note of shop A").save()
    for number in range(settings.REST_FRAMEWORK["PAGE_SIZE"]):
        Note(shop=shop_b, text=f"Note {number} of shop B").save()

    problems = route_problems(staff_client_a, staff_client_b, shop_a, shop_b)

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
    assert misplaced_uses("base_manager", may_use_base_manager) == {}


def test_raw_sql_only_in_migrations_and_system_code() -> None:
    assert misplaced_uses("raw", may_use_raw_sql, calls_of) == {}
    assert misplaced_uses("cursor", may_use_raw_sql, calls_of) == {}


def test_hand_built_queries_only_where_listed() -> None:
    assert misplaced_uses("QuerySet", may_build_queries, calls_of) == {}
    # And no file is listed that builds none any more: a stale entry would let a new one in unseen.
    assert set(HAND_BUILT_QUERIES) <= set(uses_in_our_code("QuerySet", calls_of))


@pytest.mark.django_db
def test_no_route_leaks_across_shops(
    sweep_shops: tuple[Shop, Shop],
    sweep_queries: dict[str, dict[str, str]],
    staff_client_a: APIClient,
    staff_client_b: APIClient,
) -> None:
    shop_a, shop_b = sweep_shops
    # The visitor really is shop B's: its side list shows shop B's own side. A login that failed on every
    # route would find nothing of shop A's anywhere, and pass.
    with shop_context(shop_b):
        own = {str(pk) for pk in Side.objects.values_list("pk", flat=True)}
    response = staff_client_b.get(reverse("side-list"))
    assert {row["id"] for row in response.json()["results"]} == own

    assert route_problems(staff_client_a, staff_client_b, shop_a, shop_b, sweep_queries) == {}


def test_every_side_link_is_named_on_its_route() -> None:
    assert side_field_problems(route.view for route in shop_routes()) == []


def test_every_api_route_is_swept() -> None:
    assert api_route_problems() == []


def test_every_route_left_to_its_own_test_has_one() -> None:
    assert own_leak_test_problems() == []
