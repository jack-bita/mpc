"""apps/shops/admin.py — the Django admin page for shops: the creator's back room.

Only the superuser opens it, to look after shops before any office screen exists (02 §4). It owns the
add and edit forms for a Shop and the page's rules: the id is shown but never typed in, a shop's kind
and currency are fixed once it exists, its status waits for the audit trail, and nothing is deleted.

Its add page saves the Shop row alone: no sides, stock locations or cash drawers. A shop that can work
is made by create_shop (apps/shops/services.py, SHOP-2); making the admin use it is a later task (Jack,
27 Oct 2026). No shop exists yet, so none is missing its sides.
"""

from django.contrib import admin
from django.http import HttpRequest

from apps.shops.models import Shop

# The shop's fields, in the order both pages show them. Some are shown but can't be typed in (status
# always, more once the shop exists): get_readonly_fields below says which, and why.
SHOP_FIELDS = ("name", "code", "timezone", "currency", "default_language", "kind", "practice_of", "status")


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin[Shop]):
    list_display = ("name", "code", "kind", "status")
    list_filter = ("kind", "status")
    search_fields = ("name", "code")
    ordering = ("name",)

    def get_fields(self, request: HttpRequest, obj: Shop | None = None) -> tuple[str, ...]:
        # The edit page also shows the id and when the shop was made. The add page doesn't: its id would
        # be a fresh one made for the empty form, not the one the saved shop gets.
        if obj is None:
            return SHOP_FIELDS
        return ("id", *SHOP_FIELDS, "created_at")

    def get_readonly_fields(self, request: HttpRequest, obj: Shop | None = None) -> tuple[str, ...]:
        # Status, always: a suspension needs who, when and why, which only the audit trail (CTRL-2) can
        # record (rule 7). Until a service does that, nothing here changes it.
        if obj is None:
            return ("status",)
        # Once the shop exists:
        # - `id`: shown but can't be typed in. It stays editable in the model, so DRF keeps the id a
        #   device sends (ADR-0007, CORE-1); changed here, it would save a copy of the shop instead.
        # - `kind` and `practice_of`: fixed. A live shop turned into a demo one would be open to the
        #   demo's fake data and resets (ADR-0029).
        # - `currency`: fixed. A sale stores only the number and the shop gives its currency, so TZS
        #   turned into KES would relabel every old amount (Jack, 27 Oct 2026).
        # `code` stays editable: nothing is deleted, so a typo (MCP for MPC) must be fixable. Lock it once
        # receipts or a web address use it. `timezone` stays editable too: each record keeps its own
        # business date, so only the days after a change follow the new zone.
        return ("id", "created_at", "kind", "practice_of", "currency", "status")

    def has_delete_permission(self, request: HttpRequest, obj: Shop | None = None) -> bool:
        # Nothing is deleted (rule 7): a shop that stops is suspended, and everything it did stays.
        return False
