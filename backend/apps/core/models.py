"""apps/core/models.py — the abstract base models every table builds on, the tenancy guard on reads, and
the append-only guard on ledgers.

UUIDModel gives a table its `id` (UUIDv7, ADR-0007); TimeStamped gives it `created_at`. ShopScoped builds
on both and adds the shop a row belongs to and the staff member who made it, with a default manager that
shows only the current shop's rows (ADR-0022; the current shop lives in apps/core/tenancy.py). AppendOnly
builds on ShopScoped for ledgers: it refuses, in Python, to save a row again or to delete one, and
PostgreSQL's trigger backs it up (apps/core/operations.py, ADR-0021). All four are abstract: they make no
table of their own, they only pass their columns on to the models that inherit them. PPL-1's User builds
on the first two, every shop's table builds on ShopScoped, and every ledger on AppendOnly.
"""

import uuid
from typing import Any, NoReturn

from django.db import models

from apps.core.tenancy import ALL_SHOPS, current_shop


class UUIDModel(models.Model):
    # ADR-0007: ids are time-ordered UUIDv7, so each new row goes at the end of the primary-key index,
    # not at a random place in it, and devices can make ids offline with no server to ask.
    # Python makes the id, not the database: the server knows a sale's id before it saves the sale,
    # so it can link the lines to it. A device sends its own id instead, and Django keeps that one.
    # No editable=False: DRF would make `id` read-only and throw away the id a device sends, so a sale
    # sent twice would be saved twice. Admin pages list `id` in readonly_fields instead.
    id = models.UUIDField(primary_key=True, default=uuid.uuid7)

    class Meta:
        # No table for UUIDModel itself: it is a base for other models, not a table.
        abstract = True


class TimeStamped(models.Model):
    # When the server saved the row, in UTC (settings: USE_TZ). auto_now_add: on insert, Django sets the
    # server's time and replaces any value passed in, so a device can't set it. (Code can still change it
    # later, with update().) A device's own clock is not trusted: counter records keep it apart, in
    # `client_time` (03 §5.3).
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class ShopScopedManager[M: models.Model](models.Manager[M]):
    # The guard (ADR-0022, 03 §5.4): `objects` on every ShopScoped table.

    def get_queryset(self) -> models.QuerySet[M]:
        # Django starts every read from `objects` here: all(), filter(), get(), count()... So the shop is
        # checked when a read is built, before it reaches the database. A built read keeps its filter:
        # built inside shop_context(A) and run after the block, it still returns A's rows, so a built read
        # is never kept from one visit to the next. Reaching the manager alone (`Note.objects`) asks
        # nothing yet, so a module that only names the manager, such as an API field given it, still
        # loads; `Note.objects.all()` at the top of a module would raise as the module loads.
        shop = current_shop()  # raises NoShopSelected when no shop was chosen
        rows = super().get_queryset()
        if shop is ALL_SHOPS:
            return rows  # system_context(): every shop's rows
        return rows.filter(shop_id=shop)


class ShopScoped(UUIDModel, TimeStamped):
    # The base of every shop's table (03 §5.3): `id` and `created_at` from the two bases, plus the shop
    # each row belongs to, who made it, and the guard on reads.

    # T1: every row belongs to one shop. Named as "shops.Shop", not imported: `core` is layer 0 and may
    # not import `shops` (ADR-0035), and a name is not an import (03 §5.1).
    # PROTECT: nothing is deleted (T3), so a shop that has rows can't vanish from under them.
    # related_name="+": no `shop.note_set`. A shop's rows are read through their own guarded `objects`.
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="+")
    # Who made the row (02 §1): the staff member acting. Empty for rows the system makes: a nightly
    # job, the demo seed, the superuser, who is nobody's staff. Named, not imported: `core` is layer 0
    # (ADR-0035). PROTECT: nothing is deleted (rule 7). editable=False: the services set it from who is
    # acting; no form or API field takes it. db_index=False: indexes lead with `shop`, and nothing is
    # deleted, so PROTECT never has to search this column.
    created_by = models.ForeignKey(
        "people.StaffMember",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        db_index=False,
    )

    # Every shop's rows, with no guard: for the superuser's admin pages only. A page answers a visit, and
    # system_context() is for system jobs only (03 §5.4), so the admin gets its own way in, with a name
    # as easy to search for: `grep all_shops` finds every use. It covers the admin's list only: an add or
    # change page also checks and fills its form through `objects`, so that page still needs a shop.
    all_shops = models.Manager()
    # The guarded manager. Django, the admin's forms and DRF read through it too, as the default manager
    # (Meta below). Declared second (ruff's Django style check reads `models.Manager()` above as a field,
    # and fields come first), but still the default.
    # Writes: save() goes through Django's plain base manager, so it needs no current shop; create(),
    # get_or_create(), update() and full_clean() go through `objects`, so they do. And inside
    # shop_context(A), nothing stops a row being written for shop B: the guard is on reads, and services
    # must check every row they write (T1).
    # Links: following one shop table's link to another (`line.sale`) also goes through the plain base
    # manager, with no guard. Only T1, checked when the link is written, keeps both rows in one shop,
    # until row-level security comes (ADR-0022).
    # Migrations get a plain manager instead: this one keeps Django's use_in_migrations=False, because a
    # migration runs as a system job, with no visit.
    objects = ShopScopedManager()

    class Meta(UUIDModel.Meta, TimeStamped.Meta):
        # Both bases' Meta, so ShopScoped keeps any option either gains later (CORE-1).
        abstract = True
        # The default manager is the one Django, the admin's forms and DRF read through. Without this
        # line it would be the first one declared: `all_shops`, with no guard, or a manager a table adds
        # of its own. This keeps `objects` the default for every table built on ShopScoped: one with no
        # Meta of its own, one whose Meta builds on ShopScoped.Meta, and even one that writes a fresh
        # Meta, because Django then takes the name from the table's first parent. The guard is lost in
        # two ways: an abstract base built on ShopScoped that writes a fresh Meta (its tables get
        # `all_shops`; AppendOnly builds its Meta on this one for that reason), and a table that declares
        # managers of its own: its own `objects`, or any manager beside a fresh Meta. CORE-7's sweep is
        # to catch both.
        default_manager_name = "objects"


class AppendOnlyError(Exception):
    # A bug, not a user's mistake: the code tried to change or delete a ledger row. Like NoShopSelected,
    # it becomes a server error and a log line, never a message on a screen, so it carries no error code
    # (ADR-0032).
    pass


class AppendOnly(ShopScoped):
    # The base of every ledger table (03 §5.3; the list is 03 §5.6): stock movements, balance entries,
    # allocations, payments, money movements, attendance events, audit events, the change log, and the
    # dated rules: prices, product costs, settings and pay rates. A ledger is ShopScoped plus this: its
    # rows are written once, and never changed or deleted (T2). Its migration adds the trigger that
    # refuses the same in PostgreSQL (apps/core/operations.py), whatever sends the change; this class
    # only stops the commonest mistake earlier, with a clear message, before the database is asked.
    # A base built on ShopScoped, not a mixin listed beside it, because a mixin can be listed wrong: a
    # plain Python mixin listed after ShopScoped never runs (Django's own save() comes first), and a
    # model mixin listed before it, with a Meta of its own, drops the shop guard (CORE-1). A base can't
    # be listed wrong: a ledger is simply `class StockMovement(AppendOnly)`.

    class Meta(ShopScoped.Meta):
        # abstract: a base, not a table. Without it, Django would make a real `core_appendonly` table and
        # join every ledger to it. Built on ShopScoped.Meta, so a ledger keeps `default_manager_name`:
        # the shop guard stays its default manager (ADR-0022).
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        # `_state.adding` is Django's own flag on every row object: True for a new one that was never
        # saved, False once it is saved or when it was read from the database. A new row goes on to
        # Django's save(), with the same arguments; saving an old row again would rewrite it.
        # To void a row (payments, money movements, attendance events), a service fills the stamp with
        # one update() on a query, which skips save(): the trigger checks that change.
        # A fix is a new row. One copied from a loaded row (`row.pk = None`) still has `adding` False
        # and is refused here: set `row._state.adding = True` too, as Django's docs say for copying any
        # row, or build the new row fresh, which reads more clearly.
        if not self._state.adding:
            raise AppendOnlyError(f"{type(self).__name__} rows are append-only: write a new row instead (ADR-0021).")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        # Always refused, so there is nothing to check. NoReturn: this never returns normally, it always
        # raises. A bulk delete() on a query skips this method; the trigger refuses that one.
        raise AppendOnlyError(
            f"{type(self).__name__} rows are never deleted: fix a mistake with a new row (T3, ADR-0021)."
        )
