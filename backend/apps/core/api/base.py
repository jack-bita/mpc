"""apps/core/api/base.py — the base of every office route: one shop per visit, rows built per visit, a place
for the per-side permission check (03 §5.4, §5.10).

An office route builds on ShopViewSet: `class SideViewSet(ShopViewSet[Side])`.

- The shop. Login names the shop a visit works for: it leaves the person acting in `request.auth`, and that
  person belongs to one shop (`shop_id`). Right after login, before any check reads a table, the view opens
  that shop (shop_context, apps/core/tenancy.py) and keeps it open for the whole visit, the error answer
  included. It closes it however the visit ends, so the next visit on the same server worker starts with
  no shop. A visit whose login names no shop is refused.
- The rows. get_queryset() builds them from the guarded manager on each visit, inside the open shop, so
  the guard filters them to that shop (ADR-0022). A table's rows can't be named in the class body, as DRF
  allows (`queryset = Side.objects.all()`): that would ask for a shop while the module loads, and raise.
- The per-side check: check_side_permission(), called for every row the view hands out. PPL-3 fills it in.

Long lists come in pages through CursorPage (apps/core/api/pagination.py), the default for every list.
"""

import uuid
from contextlib import ExitStack
from typing import Any, cast

from django.db import models
from django.http import HttpRequest, HttpResponseBase
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.viewsets import GenericViewSet

from apps.core.models import ShopScoped
from apps.core.tenancy import shop_context


class ShopViewSet[M: ShopScoped](GenericViewSet[M]):
    # The table whose rows the route shows, read per visit in get_queryset().
    model: type[M]
    # The visit's stack of things to close when it ends: the open shop. Set in dispatch(), once per visit;
    # DRF makes a new view object for every visit, so two visits never share it.
    _visit: ExitStack

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        # DRF's whole visit runs inside this `with`: login, checks, the action, and the error answer if
        # one is raised. perform_authentication() below opens the shop on the stack; leaving the `with`
        # closes it, however the visit ends. (DRF turns the answer into bytes only after this returns.
        # By then its data is already built, so nothing reads a table with the shop closed.)
        with ExitStack() as self._visit:
            return super().dispatch(request, *args, **kwargs)

    def perform_authentication(self, request: Request) -> None:
        # DRF calls this early in every visit, right before the permission and throttle checks, which may
        # read tables too: so the shop opens here, and not later.
        super().perform_authentication(request)  # runs the login: request.user and request.auth
        shop_id = getattr(request.auth, "shop_id", None)
        if not isinstance(shop_id, uuid.UUID):
            # Nobody logged in, or a login that names no shop, like the superuser's admin session: the
            # superuser is nobody's staff. Request code never reads across shops (03 §5.4), so the visit
            # stops here, before any table is read.
            raise exceptions.NotAuthenticated("This route needs a login at a shop.")
        self._visit.enter_context(shop_context(shop_id))

    def get_queryset(self) -> models.QuerySet[M]:
        # Built on each visit, inside the visit's shop. The default manager is the guarded `objects`, which
        # ShopScoped makes the default of every shop's table (CORE-2); CORE-7's sweep checks they all keep it.
        # cast: mypy reads the manager of `type[M]` as ShopScoped's, though the rows are this route's table's.
        return cast("models.QuerySet[M]", self.model._default_manager.all())

    def side_of(self, row: M) -> uuid.UUID | None:
        """The side a row belongs to, for the per-side check: its `side`, or None for a row of the whole shop,
        such as a product. A route whose rows are sides themselves says so (SideViewSet)."""
        return getattr(row, "side_id", None)

    def check_side_permission(self, request: Request, side_id: uuid.UUID | None) -> None:
        """The per-side check (03 §5.4): may the person acting do this action on this side, or on the whole
        shop when `side_id` is None? Refuses with PermissionDenied. PPL-3 fills it in with its permission
        codes; until then, anyone logged in at the open shop may."""

    def check_object_permissions(self, request: Request, obj: Any) -> None:
        # DRF calls this for every row get_object() hands out, to read it or to change it: the usual
        # checks, then the side's.
        super().check_object_permissions(request, obj)
        self.check_side_permission(request, self.side_of(obj))
