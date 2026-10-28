"""apps/core/api/pagination.py — how long lists come in pages: CursorPage, the default for every list
(REST_FRAMEWORK in config/settings/base.py, 03 §5.10).

Its own module, apart from the base views in base.py: DRF reads the default pagination class while it
loads its generic views, which base.py imports, so a page class kept in base.py would be asked for before
it exists.
"""

from rest_framework.pagination import CursorPagination


class CursorPage(CursorPagination):
    # Each page comes with the address of the next one. A cursor, not page numbers: a page number moves
    # when rows are added in between (each new sale pushes the older ones down a place, so page 2 shows
    # a row twice), while a cursor marks a place in the order that stays put.
    # Newest first, by the server's clock: `created_at` is set by the server when the row is saved. The id
    # would not do: the client makes it (ADR-0007), and a phone's clock may be wrong. `-id` settles rows
    # saved in the same microsecond, so every row keeps one place in the order.
    ordering = ("-created_at", "-id")
