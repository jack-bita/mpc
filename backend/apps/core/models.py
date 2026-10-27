"""apps/core/models.py — the abstract base models every table builds on, and the tenancy guard on reads.

UUIDModel gives a table its `id` (UUIDv7, ADR-0007); TimeStamped gives it `created_at`. ShopScoped builds
on both and adds the shop a row belongs to, with a default manager that shows only the current shop's
rows (ADR-0022; the current shop lives in apps/core/tenancy.py). All three are abstract: they make no
table of their own, they only pass their columns on to the models that inherit them. PPL-1's User builds
on the first two, and every shop's table builds on ShopScoped.
"""

import uuid

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
        # checked when a read is built, before it reaches the database. Reaching the manager alone
        # (`Note.objects`) asks nothing yet, so code loaded before any visit, such as an API field given
        # the manager, still loads.
        shop = current_shop()  # raises NoShopSelected when no shop was chosen
        rows = super().get_queryset()
        if shop is ALL_SHOPS:
            return rows  # system_context(): every shop's rows
        return rows.filter(shop_id=shop)


class ShopScoped(UUIDModel, TimeStamped):
    # The base of every shop's table (03 §5.3): `id` and `created_at` from the two bases, plus the shop
    # each row belongs to and the guard on reads. `created_by` joins in PPL-2, once staff exist.

    # T1: every row belongs to one shop. Named as "shops.Shop", not imported: `core` is layer 0 and may
    # not import `shops` (ADR-0035), and a name is not an import (03 §5.1).
    # PROTECT: nothing is deleted (T3), so a shop that has rows can't vanish from under them.
    # related_name="+": no `shop.note_set`. A shop's rows are read through their own guarded `objects`.
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="+")

    # Every shop's rows, with no guard: for the superuser's admin pages only. The admin builds its list
    # in one step and reads it later, while drawing the page, so a `with` block can't cover it.
    # `grep all_shops` finds every use.
    all_shops = models.Manager()
    # The guarded manager: what our code, the admin's forms and DRF use to read a table. Declared second
    # (ruff's Django style check reads `models.Manager()` above as a field, and fields come first), but
    # still the default: Meta's default_manager_name says so.
    # Django's base manager, which save(), refresh_from_db() and `row.shop` use, stays the plain one:
    # writing a row or following a link needs no current shop. The guard is on reads; services check
    # every row they write (T1). Not used in migrations: those run as system jobs, with no visit.
    objects = ShopScopedManager()

    class Meta(UUIDModel.Meta, TimeStamped.Meta):
        # Both bases' Meta, so ShopScoped keeps any option either gains later (CORE-1).
        abstract = True
        # The default manager is the one Django, the admin's forms and DRF read through. Without this
        # line it would be the first one declared, `all_shops`, with no guard; and a table that added a
        # manager of its own would make that one the default. Named here, it is always `objects`.
        default_manager_name = "objects"
