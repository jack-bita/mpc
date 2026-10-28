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
- Creates: a route that makes rows adds CreateOnceMixin. The client sends the new row's id (ADR-0007), so
  the same request sent twice makes one row, and an id already used in another shop is refused.
- Edits: a route that changes rows adds EditMixin. The client sends the `version` it read, so an edit made
  on an old copy is refused (409 version_conflict) instead of undoing someone else's.

Long lists come in pages through CursorPage (apps/core/api/pagination.py), the default for every list.
"""

import uuid
from contextlib import ExitStack
from typing import Any, cast

import psycopg
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.http import HttpRequest, HttpResponseBase
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.models import Editable, ShopScoped
from apps.core.tenancy import Actor, shop_context


class ShopViewSet[M: ShopScoped](GenericViewSet[M]):
    # The table whose rows the route shows, read per visit in get_queryset().
    model: type[M]
    # Who acts in this visit, from login: the services record it as who made or changed a row.
    actor: Actor
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
        # cast: DRF's type stubs know only its own Token model in `request.auth`; ours carries a shop.
        self.actor = cast(Actor, request.auth)

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


class CreateOnceMixin[M: ShopScoped](ShopViewSet[M]):
    """POST: make a row once, however many times the same request arrives (ADR-0007, 03 §5.10).

    The client makes the new row's id and sends it with the row. A phone whose answer was lost sends the
    same request again, with the same id, and gets the stored row back, with the same 201, as if the first
    answer had arrived. A route that makes rows builds on this, names what a create sends
    (`create_serializer_class`), and writes create_row(), which calls its service."""

    # What a create sends: the new row's fields, `id` among them, and required.
    create_serializer_class: type[serializers.BaseSerializer[Any]]

    def create_row(self, data: dict[str, Any]) -> M:
        """Make the new row from the checked input, through the route's service. Each route writes its own."""
        raise NotImplementedError

    def side_of_new(self, data: dict[str, Any]) -> uuid.UUID | None:
        """The side a new row will belong to, for the per-side check before it is made: its `side`, or None
        for a row of the whole shop."""
        side = data.get("side")
        return None if side is None else side.pk

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Sent before? Look first, before any check: the row a first send made would fail the checks of
        # its own retry (MFANO already has a side P: the first send's own).
        sent_id = request.data.get("id") if isinstance(request.data, dict) else None
        row = self._stored(sent_id)
        if row is None:
            row = self._create(request)
        else:
            # Handed out like any row that is read: the side's check applies.
            self.check_object_permissions(request, row)
        return Response(self.get_serializer(row).data, status=status.HTTP_201_CREATED)

    def _create(self, request: Request) -> M:
        sent = self.create_serializer_class(data=request.data, context=self.get_serializer_context())
        sent.is_valid(raise_exception=True)
        data = sent.validated_data
        self.check_side_permission(request, self.side_of_new(data))
        try:
            # A savepoint: a refused insert undoes only this part, and the visit can still look and answer.
            with transaction.atomic():
                return self.create_row(data)
        except IntegrityError as error:
            if not _id_taken(error, self.model):
                # Another database rule: the service should have checked it first, so this is a bug.
                raise
        # The id was taken. Either the same request came twice at the same moment, and the other copy has
        # just made the row in this shop: then it is the answer, as for any retry.
        row = self._stored(data["id"])
        if row is None:
            # Or another shop's row has this id. The guard hides it from every lookup here, and the answer
            # says only that the id can't be used: nothing about that row, not even what it is (03 §5.4).
            raise ValidationError({"id": ValidationError("This id is already in use.", code="id.taken")})
        return row

    def _stored(self, row_id: object) -> M | None:
        # The row with this id in the visit's shop, if there is one: the guard hides every other shop's.
        try:
            row_id = uuid.UUID(str(row_id))
        except ValueError:
            return None  # no id, or not an id at all: the input check says so, beside the field
        return self.get_queryset().filter(pk=row_id).first()


class EditMixin[M: Editable](ShopViewSet[M]):
    """PATCH: change a row, unless someone else changed it since the client read it (02 §1, 03 §5.10).

    The client sends the changed fields and the `version` it read. A route that edits builds on this,
    names what an edit sends (`edit_serializer_class`, with `version`), and writes edit_row(), which calls
    its service; the service changes the row inside editing() (apps/core/editing.py), which refuses a stale
    version. Only PATCH: a full replace (PUT) would have to send every field, and could send old values back
    for the fields this person never touched."""

    # What an edit sends: the fields that may change, and the `version` the client read.
    edit_serializer_class: type[serializers.BaseSerializer[Any]]

    def edit_row(self, row: M, data: dict[str, Any]) -> M:
        """Change the row from the checked input, through the route's service. Each route writes its own."""
        raise NotImplementedError

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # This shop's row, through the per-side check, as for a read (get_object). Another shop's row is
        # not found, as for a read.
        row = self.get_object()
        sent = self.edit_serializer_class(data=request.data, context=self.get_serializer_context())
        sent.is_valid(raise_exception=True)
        return Response(self.get_serializer(self.edit_row(row, sent.validated_data)).data)


def _id_taken(error: IntegrityError, model: type[models.Model]) -> bool:
    # True when the refused insert broke the table's primary key: its id was already taken. PostgreSQL
    # names the broken rule, and it names a table's primary key "<table>_pkey".
    cause = error.__cause__
    return (
        isinstance(cause, psycopg.errors.UniqueViolation)
        and cause.diag.constraint_name == f"{model._meta.db_table}_pkey"
    )
