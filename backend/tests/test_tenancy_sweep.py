"""backend/tests/test_tenancy_sweep.py — the tenancy sweep: every table of our apps keeps each shop's rows
apart, checked by itself (03 §5.4, ADR-0022).

Many shops keep their rows side by side in the same tables, and the guard (CORE-2) shows each visit only its
own shop's rows. That holds only while every table is built the way the guard expects, and nothing stops a
new table from being built another way. So this module asks Django for every table of our apps (the ones
under backend/apps/) and checks each one, with no list of tables to keep up to date:

- it has `shop`, through ShopScoped, unless it belongs to no one shop (T1);
- every link it holds to another table uses PROTECT, so deleting a row never takes other rows with it (T3);
- its primary key keeps the name PostgreSQL gave it, which the API's creates rely on (CORE-6).

A new table is checked with no change here, and this file must stay green without being edited (backend
rules). Each check is a function that returns what breaks its rule, as in test_no_floats.py. The tests of
the checks hand them tables built to break the rule, made in a throwaway registry of their own, so those
tables never join the real list; and one test makes sure the real list is not empty, so the sweep can't
pass by looking at nothing.
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

import pytest
from django.apps import apps
from django.apps.registry import Apps
from django.core.exceptions import FieldDoesNotExist
from django.db import connection, models
from django.test.utils import isolate_apps

from apps.core.models import ShopScoped, UUIDModel
from tests.probe.models import Note

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


# --- the sweep ------------------------------------------------------------------------------------------------


def test_every_model_has_shop() -> None:
    assert shop_problems(our_tables()) == []


def test_every_foreign_key_protects() -> None:
    assert link_problems(our_tables()) == []


@pytest.mark.django_db
def test_every_primary_key_keeps_its_postgres_name() -> None:
    assert primary_key_problems(our_tables()) == []
