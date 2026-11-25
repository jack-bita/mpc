"""apps/people/tests/test_meals_key.py — the key to the day's meal money reaches the shops that already have their roles
(WAGE-7, 03 §5.8): people's 0023, the first migration that writes rows.

A new shop copies the role templates as they are now (copy_role_templates), so its Owner holds `meals.record` from the
start. A shop made before has its own copy, with no such code: its owner would hold everything but this, and as whoever
gives a key must hold it (02 §5), nobody there could ever be given it. So the migration adds it to each shop's Owner,
and to no other role: the owner gives it to whoever he chooses (Jack, 15 Nov 2026).

The migration's own two functions are called here, on the tables as they were at that migration (its "state"), just as
`migrate` calls them; on rows made through the services, then put back as an old shop kept them.
"""

import importlib
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from apps.control.models import EditEvent
from apps.core.permissions import Permission, RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Role
from apps.people.services import copy_role_templates
from apps.shops.models import Shop

pytestmark = pytest.mark.django_db

KEY = Permission.MEALS_RECORD


@pytest.fixture(scope="module")
def tables_then() -> Any:
    # The apps as they were once the migration had run: plain tables with plain managers, as `migrate` hands them to it.
    # Built once for the file, as building them reads every migration there is.
    return (
        MigrationLoader(None, ignore_no_migrations=True)
        .project_state([("people", "0023_owners_hold_meals_record")])
        .apps
    )


def run(step: str, tables: Any) -> None:
    # One of the migration's two functions, by name, with what `migrate` gives it: the tables, and the connection's
    # schema editor, of which it reads the connection alone.
    migration = importlib.import_module("apps.people.migrations.0023_owners_hold_meals_record")
    with connection.schema_editor(atomic=False) as editor:
        getattr(migration, step)(tables, editor)


def without_the_key(shop: Shop) -> dict[str, Role]:
    # A shop as it was before the code existed: its six roles, none with the key. update(), as no service takes a code
    # out of a role yet; each update writes one line of history, counted below.
    with shop_context(shop):
        roles = copy_role_templates(shop)
        for role in roles.values():
            Role.objects.filter(pk=role.pk).update(permissions=[code for code in role.permissions if code != KEY])
            role.refresh_from_db()
    return roles


def lines_of(role: Role) -> list[EditEvent]:
    with shop_context(role.shop_id):
        return list(EditEvent.objects.filter(subject_type="role", subject_id=role.pk).order_by("created_at", "id"))


def test_an_old_shops_owner_gets_the_key_and_nobody_else(shop_a: Shop, shop_b: Shop, tables_then: Any) -> None:
    # Both shops, in one run: a migration is a system job, with no shop open.
    old_a, old_b = without_the_key(shop_a), without_the_key(shop_b)
    run("give_the_owners_the_key", tables_then)
    for shop, old in ((shop_a, old_a), (shop_b, old_b)):
        with shop_context(shop):
            now = {role.template: role for role in Role.objects.all()}
        # As a new shop's Owner holds them: every code, in the same sorted order.
        assert now[RoleTemplate.OWNER].permissions == sorted(Permission)
        # The Manager, whom the owner may give it to, and everyone else: as they were.
        for template in set(RoleTemplate) - {RoleTemplate.OWNER}:
            assert now[template].permissions == old[template].permissions
            assert KEY not in now[template].permissions


def test_the_owners_history_says_so(shop_a: Shop, tables_then: Any) -> None:
    # The role's version moves, so a page that read the Owner before can't save over it, and its history keeps the
    # change, made by nobody: the system (ADR-0036). And `updated_by` agrees: nobody (02 §1).
    owner = without_the_key(shop_a)[RoleTemplate.OWNER]
    before = len(lines_of(owner))
    run("give_the_owners_the_key", tables_then)
    with shop_context(shop_a):
        now = Role.objects.get(pk=owner.pk)
    assert now.version == owner.version + 1
    assert now.updated_at is not None and now.updated_by is None
    lines = lines_of(owner)
    assert len(lines) == before + 1
    assert KEY in lines[-1].after["permissions"] and KEY not in lines[-1].before["permissions"]
    assert lines[-1].created_by is None and lines[-1].device is None


def test_a_shop_that_has_it_already_is_left_alone(shop_a: Shop, tables_then: Any) -> None:
    # A shop set up after the code, or the migration run again: its Owner holds the key, so nothing is written.
    with shop_context(shop_a):
        owner = copy_role_templates(shop_a)[RoleTemplate.OWNER]
    run("give_the_owners_the_key", tables_then)
    with shop_context(shop_a):
        now = Role.objects.get(pk=owner.pk)
    assert now.version == owner.version == 1
    assert now.permissions == owner.permissions
    assert lines_of(owner) == []


def test_a_role_the_owner_made_himself_gets_nothing(shop_a: Shop, tables_then: Any) -> None:
    # Only the Owner's own copy of the template: a role with a name of the owner's own, however much it holds, was never
    # given this, so nobody in it may type the meal money until the owner says so.
    without_the_key(shop_a)
    with shop_context(shop_a):
        made = Role(shop=shop_a, name="Msaidizi wa Baba", permissions=[Permission.STAFF_MANAGE])
        made.save()
    run("give_the_owners_the_key", tables_then)
    with shop_context(shop_a):
        made.refresh_from_db()
    assert made.permissions == [Permission.STAFF_MANAGE]


def test_undone_the_key_is_taken_back_from_every_role(shop_a: Shop, tables_then: Any) -> None:
    # Undone, before the rule of known codes forgets the code: every role that holds it lets it go, a shop's made after
    # the code included, or the old rule would refuse their rows and stop the undoing half way.
    with shop_context(shop_a):
        roles = copy_role_templates(shop_a)
    run("take_the_key_back", tables_then)
    with shop_context(shop_a):
        for role in Role.objects.all():
            assert KEY not in role.permissions
            # Nothing else was taken.
            assert role.permissions == [code for code in roles[role.template].permissions if code != KEY]
