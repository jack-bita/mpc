"""apps/shops/admin.py — the Django admin page for shops: the creator's back room.

Only the superuser opens it, to look after shops before any office screen exists (02 §4). It owns the
list and edit pages for a Shop and the page's rules: the id is shown but never typed in, a shop's kind
and currency are fixed, its status waits for the audit trail, and nothing is added or deleted here.

No shop is added here: a form for the Shop row alone would make a shop with no sides, stock places,
cash drawers or roles, where nobody could work (SHOP-2). A shop is opened on the server with
`manage.py open_shop` (apps/people/management/commands/open_shop.py, PPL-13), which makes all of it,
all or nothing, through set_up_shop. Editing a shop stays: its name, code, timezone and language.
"""

from django.contrib import admin
from django.http import HttpRequest

from apps.shops.models import Shop

# The shop's fields, in the order its page shows them, after its id. Some are shown but can't be typed
# in: `readonly_fields` below says which, and why.
SHOP_FIELDS = ("name", "code", "timezone", "currency", "default_language", "kind", "practice_of", "status")


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin[Shop]):
    list_display = ("name", "code", "kind", "status")
    list_filter = ("kind", "status")
    search_fields = ("name", "code")
    ordering = ("name",)

    # Every page here edits a shop that exists, so the id and when it was made are always shown. There is
    # no add page (has_add_permission), whose empty form would have needed its own lists.
    fields = ("id", *SHOP_FIELDS, "created_at")
    # Shown but never typed in:
    # - `id`: it stays editable in the model, so DRF keeps the id a device sends (ADR-0007, CORE-1);
    #   changed here, it would save a copy of the shop instead.
    # - `kind` and `practice_of`: fixed. A live shop turned into a demo one would be open to the demo's
    #   fake data and resets (ADR-0029).
    # - `currency`: fixed. A sale stores only the number and the shop gives its currency, so TZS turned
    #   into KES would relabel every old amount (Jack, 27 Oct 2026).
    # - `status`: a suspension needs who, when and why, which only the audit trail (CTRL-2) can record
    #   (rule 7). Until a service does that, nothing here changes it.
    # `code` stays editable: nothing is deleted, so a typo (MCP for MPC) must be fixable. Lock it once
    # receipts or a web address use it. `timezone` stays editable too: each record keeps its own business
    # date, so only the days after a change follow the new zone.
    readonly_fields = ("id", "created_at", "kind", "practice_of", "currency", "status")

    def has_add_permission(self, request: HttpRequest) -> bool:
        # No add page, and no add button on the list (parking lot item 16, Jack: A). It saved the Shop row
        # alone, with no sides, stock places, cash drawers or roles: a shop where nobody could work
        # (SHOP-2). `manage.py open_shop` opens one with all of it (PPL-13).
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Shop | None = None) -> bool:
        # Nothing is deleted (rule 7): a shop that stops is suspended, and everything it did stays.
        return False
