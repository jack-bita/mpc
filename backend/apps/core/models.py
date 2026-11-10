"""apps/core/models.py — the abstract base models every table builds on, the tenancy guard on reads, the
version that keeps two edits apart, and the append-only guard on ledgers.

UUIDModel gives a table its `id` (UUIDv7, ADR-0007); TimeStamped gives it `created_at`. ShopScoped builds
on both and adds the shop a row belongs to and the staff member who made it, with a default manager that
shows only the current shop's rows (ADR-0022; the current shop lives in apps/core/tenancy.py). Editable
builds on ShopScoped for the office records people change: it adds when and by whom a row was last
edited, and its version, so that two people editing at once can't overwrite each other
(apps/core/editing.py). CounterRecord builds on ShopScoped for the records made at a shop's counter, on a
device, and pushed later: it adds the device, the device's own number for the record, and both clocks
(SYNC-4). AppendOnly builds on ShopScoped for ledgers: it refuses, in Python, to save a row
again or to delete one, and PostgreSQL's trigger backs it up (apps/core/operations.py, ADR-0021). All six
are abstract: they make no table of their own, they only pass their columns on to the models that
inherit them. PPL-1's User builds on the first two, every shop's table on ShopScoped, every office record
people edit on Editable, every counter record on CounterRecord, and every ledger on AppendOnly.

Two real tables live here too, because every app needs them and `core` is the layer all may import:
ShopSequence, a shop's named counters, such as the one that gives each new device its code (AUTH-1), moved
only by next_number (apps/core/sequences.py); and Change, a shop's change log, the numbered list of changed
records that devices pull (SYNC-1, 03 §6.4), written only by recording_changes (apps/core/changes.py).
"""

import uuid
from typing import Any, NoReturn

from django.db import models

from apps.core.tenancy import ALL_SHOPS, current_shop
from apps.core.type_codes import TYPE_CODE_MAX_LENGTH, TYPE_CODE_SHAPE


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


class Editable(ShopScoped):
    # The base of every office record people change (02 §1, 03 §5.3): a side's name now, products, prices
    # and contacts later. ShopScoped plus what makes an edit safe when two people edit the same row at once.
    # Only apps/core/editing.py writes these three columns: editable=False keeps them out of every form and
    # every API field.

    # When the last edit was saved, by the server's clock, and who made it. Empty until the first edit: the
    # creation is already in `created_at` and `created_by`. Named, not imported: `core` is layer 0
    # (ADR-0035). PROTECT, no index of its own: as for `created_by` above.
    updated_at = models.DateTimeField(null=True, blank=True, editable=False)
    updated_by = models.ForeignKey(
        "people.StaffMember",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        db_index=False,
    )
    # 1 when the row is made, and 1 more at each edit. A screen reads the row with its version and sends the
    # version back with its edit: if the row has moved on since, someone else saved in between, and the
    # edit is refused instead of undoing theirs (409 version_conflict).
    version = models.PositiveIntegerField(default=1, editable=False)

    class Meta(ShopScoped.Meta):
        # abstract: a base, not a table. Built on ShopScoped.Meta, so an editable table keeps the shop
        # guard as its default manager (ADR-0022), as AppendOnly's tables do.
        abstract = True


class CounterRecord(ShopScoped):
    # The base of every record made at a shop's counter, on a device, and pushed later (02 §1, 03 §5.3): a sale, a
    # repayment, a clock-in. ShopScoped plus four facts only the push can give it, and it fills all four (SYNC-4):
    # editable=False keeps them out of every form and every API field, as created_by is.

    # The device that made it, the one whose key sent the push. Named, not imported: `core` is layer 0 (ADR-0041).
    # PROTECT: nothing is deleted (rule 7), so every record keeps naming the laptop it came from. No index of its own:
    # indexes lead with `shop`, and nothing is deleted, so PROTECT never has to search this column.
    device = models.ForeignKey(
        "people.Device", on_delete=models.PROTECT, related_name="+", editable=False, db_index=False
    )
    # Its number on that device: 1, 2, 3... in the order the device made its records, whatever their type. The push
    # posts a batch in this order (SYNC-4), and a jump means a record still missing (device_gap, SYNC-5).
    device_seq = models.PositiveBigIntegerField(editable=False)
    # The time the device's clock showed when it was made: kept, never trusted, as a device's clock can be wrong
    # (02 §12). And the server's own clock when the push arrived: the time that can be trusted.
    client_time = models.DateTimeField(editable=False)
    received_at = models.DateTimeField(editable=False)

    class Meta(ShopScoped.Meta):
        # abstract: a base, not a table. Built on ShopScoped.Meta, so a counter table keeps the shop guard as its
        # default manager (ADR-0042), as Editable's and AppendOnly's tables do. A counter ledger, such as a clock-in,
        # builds on both: `class AttendanceEvent(AppendOnly, CounterRecord)`, its Meta from both.
        abstract = True


class AppendOnlyError(Exception):
    # A bug, not a user's mistake: the code tried to change or delete a ledger row. Like NoShopSelected,
    # it becomes a server error and a log line, never a message on a screen, so it carries no error code
    # (ADR-0032).
    pass


class AppendOnly(ShopScoped):
    # The base of every ledger table (03 §5.3; the list is 03 §5.6): stock movements, balance entries,
    # allocations, payments, money movements, attendance events, audit events, a flag's notes and the
    # people it names, the change log, the push's answer log (sync.PushedDocument), and the dated rules:
    # prices, product costs, settings and pay rates. A ledger is ShopScoped plus this: its rows are written
    # once, and never changed or deleted (T2). Its migration adds the trigger that refuses the same in
    # PostgreSQL (apps/core/operations.py), whatever sends the change; this class only stops the commonest
    # mistake earlier, with a clear message, before the database is asked.
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


class SequenceName(models.TextChoices):
    # The counters a shop keeps, one row each (03 §5.1). A fixed list, checked by the database too, because a typo
    # must never start a second counter: "devcie" would count again from 1 and hand out device codes already in use,
    # so two devices would print the same receipt numbers (D7). A new counter is a new line here and a migration
    # that rebuilds the rule below, as a new permission code is (apps/core/permissions.py).
    DEVICE = "device", "Device codes"
    # The change log's numbers (Change, below; SYNC-1): one per changed record, in the order the changes commit.
    CHANGE = "change", "Change-log numbers"


class ShopSequence(ShopScoped):
    # One named counter of one shop: MPC's "device" counter gave 1 to the first laptop and 2 to the phone after it.
    # ShopScoped (CORE-2) gives `id`, `shop`, `created_at`, `created_by` (always empty: only the system makes a
    # counter) and the guard on reads. Moved only by next_number (apps/core/sequences.py), which locks the row
    # until its transaction ends, so two numbers are never given at once. No edit history (Jack, AUTH-1;
    # NO_EDIT_HISTORY in backend/tests/sweep_lists.py): only the system moves a counter, and each number it gives
    # is kept on the row that took it, a device's code.

    name = models.CharField(max_length=20, choices=SequenceName)
    # The last number given; 0 before the first. A big integer: from SYNC-1, a counter numbers every change a shop
    # makes, every sale included, and must never run out.
    value = models.PositiveBigIntegerField(default=0)

    class Meta(ShopScoped.Meta):
        # Builds on ShopScoped.Meta, so `objects`, with the guard, stays the default manager (CORE-2). No error
        # codes on these rules: no form or API ever writes a counter, so a broken rule here is a bug in our code,
        # a server error and a log line, never a message on a screen (ADR-0032).
        constraints = [
            # One counter of each name per shop: two "device" rows would each count from 1, and give the same code
            # twice. It also lets next_number make the row on first use safely (INSERT ... ON CONFLICT DO NOTHING).
            # Leads with `shop`, as every index does.
            models.UniqueConstraint(fields=["shop", "name"], name="core_shopsequence_one_per_name"),
            models.CheckConstraint(
                condition=models.Q(name__in=SequenceName.values), name="core_shopsequence_name_known"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name}: {self.value}"


class ChangeOp(models.TextChoices):
    # What a device does with a changed record when it pulls it (03 §6.4). Upsert ("update or insert"): save the
    # record as it is now, new or changed. Archive: take it off the device's lists. Nothing is ever deleted (rule 7),
    # so a record that leaves, such as a person who left the shop, is archived, never removed.
    UPSERT = "upsert", "Added or changed"
    ARCHIVE = "archive", "Archived"


class Change(AppendOnly):
    # One line of a shop's change log (03 §6.4): "record X of table Y changed, and this is change number N". A device
    # remembers the last number it read and asks for the lines after it (SYNC-3), then reads each record as it is now
    # from its own table. A line names the record and holds none of its data, so the log stays small and holds
    # nothing secret. Written only by recording_changes (apps/core/changes.py), as the last step of the transaction
    # that changed the record, so the numbers follow the order the transactions commit.
    # ShopScoped (CORE-2) gives `id`, `shop`, `created_at` and `created_by`, which stays empty: who changed a record is
    # in its edit history and the audit trail, and a device needs only to know that it changed. AppendOnly (CORE-3)
    # refuses a second save() and any delete() in Python, and the trigger in the migration refuses the same in
    # PostgreSQL (ADR-0021): a device that read line 41 must never find it rewritten.

    # The shop, as ShopScoped has it, but with no index of its own: the one-line-per-number rule below is an index that
    # leads with `shop`, so a second one, on `shop` alone, would cost one more write for every line on the busiest table
    # there is, and serve no read (from the review). PROTECT never searches it either: no shop is ever deleted.
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="+", db_index=False)
    # The change's number in its shop: 1, 2, 3..., from the shop's "change" counter (apps/core/sequences.py). A big
    # integer: a shop numbers every change it ever makes, every sale included.
    seq = models.PositiveBigIntegerField()
    # Which table: its link type code (apps/core/links.py), such as "side" or "staff", the code an audit line or a
    # flag names that table by. SYNC-2's list of what devices may pull goes by these codes.
    entity = models.CharField(max_length=TYPE_CODE_MAX_LENGTH)
    # Which record of that table. No foreign key: one column can't point at rows of many tables.
    record_id = models.UUIDField()
    op = models.CharField(max_length=10, choices=ChangeOp)

    class Meta(AppendOnly.Meta):
        # Built on AppendOnly.Meta, so `objects`, with the shop guard, stays the default manager (CORE-2). No error
        # codes on these rules: only recording_changes writes this table, never a form or an API, so a broken rule
        # is a bug in our code, a server error and a log line (ADR-0032).
        constraints = [
            # One line per number in a shop: with two lines numbered 42, a device that read up to 42 might have read
            # only one of them, and could never learn it missed the other. Also the index every pull reads by (shop,
            # then the numbers after the device's cursor, in order), leading with `shop` as every index does.
            models.UniqueConstraint(fields=["shop", "seq"], name="core_change_one_per_seq"),
            # Numbers start at 1. A cursor of 0 means "nothing read yet", so a line numbered 0 would never be pulled.
            models.CheckConstraint(condition=models.Q(seq__gte=1), name="core_change_seq_from_one"),
            models.CheckConstraint(condition=models.Q(op__in=ChangeOp.values), name="core_change_op_known"),
            # The list of type codes lives in code, where the database can't see it, but a code's shape it can check,
            # as for an audit line's subject (control.AuditEvent).
            models.CheckConstraint(condition=models.Q(entity__regex=TYPE_CODE_SHAPE), name="core_change_entity_shape"),
        ]

    def __str__(self) -> str:
        return f"{self.seq}: {self.op} {self.entity}"
