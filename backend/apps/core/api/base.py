"""apps/core/api/base.py — the base of every office route: one shop per visit, rows built per visit, a place
for the per-side permission check (03 §5.4, §5.10).

An office route builds on ShopViewSet: `class SideViewSet(ShopViewSet[Side])`.

- The shop. Login names who acts and the shop a visit works for: it leaves the staff member acting in
  `request.auth`, an Actor (apps/core/tenancy.py) with a `shop_id` and a `staff_id`. Right after login,
  before any check reads a table, the view opens that shop (shop_context) and keeps it open for the whole
  visit, the error answer included. It closes it however the visit ends, so the next visit on the same
  server worker starts with no shop. A visit whose login names no shop, or no staff member, is refused.
- Who acts. Right after the shop, the view tells PostgreSQL who acts for the visit, and its shop
  (apps/core/acting.py), so the trigger that records every office edit names them and refuses an edit of another
  shop's row (03 §5.16), and takes both back as the visit ends.
- The rows. get_queryset() builds them from the guarded manager on each visit, inside the open shop, so
  the guard filters them to that shop (ADR-0022). A table's rows can't be named in the class body, as DRF
  allows (`queryset = Side.objects.all()`): that would ask for a shop while the module loads, and raise.
- The sides. Two hooks PPL-3 fills in (02 §5, X1). visible_sides(): which sides' rows a person may see at
  all; every read leaves the others out, so a list never shows them and their rows are "not found".
  check_side_permission(): may the person do this action on this side, asked for each row read, edited or
  made one at a time.
- Creates: a route that makes rows adds CreateOnceMixin. The client sends the new row's id (ADR-0007), so
  the same request sent twice makes one row, and an id already used in another shop is refused.
- Edits: a route that changes rows adds EditMixin. The client sends the `version` it read, so an edit made
  on an old copy is refused (409 version_conflict) instead of undoing someone else's.

Long lists come in pages through CursorPage (apps/core/api/pagination.py), the default for every list.
"""

import uuid
from collections.abc import Collection
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

from apps.core.acting import acting_as
from apps.core.models import Editable, ShopScoped
from apps.core.tenancy import Actor, shop_context


class ShopViewSet[M: ShopScoped](GenericViewSet[M]):
    # The table whose rows the route shows, read per visit in get_queryset().
    model: type[M]
    # Who acts in this visit, from login: a staff member of the visit's shop, whom the services record as
    # who made or changed a row.
    actor: Actor
    # The visit's stack of things to close when it ends: the open shop, and who acts as PostgreSQL knows it.
    # Set in dispatch(), once per visit; DRF makes a new view object for every visit, so two visits never
    # share it.
    _visit: ExitStack

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        # DRF's whole visit runs inside this `with`: login, checks, the action, and the error answer if
        # one is raised. perform_authentication() below opens the shop and who acts on the stack; leaving
        # the `with` closes both, however the visit ends. (DRF turns the answer into bytes only after this returns.
        # By then its data is already built, so nothing reads a table with the shop closed.)
        with ExitStack() as self._visit:
            return super().dispatch(request, *args, **kwargs)

    def perform_authentication(self, request: Request) -> None:
        # DRF calls this early in every visit, right before the permission and throttle checks, which may
        # read tables too: so the shop opens here, and not later.
        super().perform_authentication(request)  # runs the login: request.user and request.auth
        shop_id = getattr(request.auth, "shop_id", None)
        staff_id = getattr(request.auth, "staff_id", None)
        if not isinstance(shop_id, uuid.UUID) or not isinstance(staff_id, uuid.UUID):
            # Nobody logged in; a login that names no shop, like the superuser's admin session (the
            # superuser is nobody's staff); or one that names a shop but no person, like a device's key
            # alone (AUTH-2). Request code never reads across shops (03 §5.4), and every row an office route
            # makes or changes records the staff member who did it, so the visit stops here, before any
            # table is read.
            raise exceptions.NotAuthenticated("Office routes need a staff login at a shop.")
        self._visit.enter_context(shop_context(shop_id))
        # cast: DRF's type stubs know only its own Token model in `request.auth`; ours carries a shop.
        self.actor = cast(Actor, request.auth)
        # Opened after the shop, so it closes first, as the visit ends. Every edit the visit makes to an office
        # table is then recorded with this staff member's name, whichever service makes it, and an edit of another
        # shop's row is refused (ADR-0036, T1).
        self._visit.enter_context(acting_as(self.actor))

    def get_queryset(self) -> models.QuerySet[M]:
        if getattr(self, "swagger_fake_view", False):
            # drf-spectacular is describing the route (apps/core/api/schema.py), with no visit, so with no
            # shop. It only needs the table, to tell the type of the id in the address. An empty query, built
            # without the guard, can return no row.
            return models.QuerySet(self.model).none()
        # Built on each visit, inside the visit's shop. The default manager is the guarded `objects`, which
        # ShopScoped makes the default of every shop's table (CORE-2); CORE-7's sweep checks they all keep it.
        # cast: mypy reads the manager of `type[M]` as ShopScoped's, though the rows are this route's table's.
        return cast("models.QuerySet[M]", self.model._default_manager.all())

    # Where a row keeps its side, read by both side hooks: `side` on most tables; the link's own name on a
    # table that names it otherwise (a device's `home_side`); "pk" on a route whose rows are sides themselves
    # (SideViewSet); None on a table whose rows belong to the whole shop, such as products. A name the table
    # doesn't have fails loudly on a read or an edit (side_of() reads the link's id), but quietly on a create:
    # side_of_new() looks for it in what was sent, finds nothing, and checks the new row as one of the whole
    # shop. So CORE-7's sweep checks every route's name against its table (test_every_side_link_is_named_on_its_route).
    side_field: str | None = "side"

    def visible_sides(self, request: Request) -> Collection[uuid.UUID] | None:
        """The sides whose rows the person acting may see, or None for all of them. PPL-3 fills it in from the
        person's roles; until then, every side."""
        return None

    def filter_queryset[R](self, queryset: models.QuerySet[M, R]) -> models.QuerySet[M, R]:
        # DRF narrows every read here: a list's rows, and the one row a read or an edit looks up (get_object).
        # Rows of a side the person may not see are left out of both, so a hidden side is not even shown to
        # exist: its rows are "not found", as another shop's are.
        rows = super().filter_queryset(queryset)
        sides = self.visible_sides(self.request)
        if sides is None or self.side_field is None:
            return rows
        return rows.filter(**{f"{self.side_field}__in": sides})

    def side_of(self, row: M) -> uuid.UUID | None:
        """The side a row belongs to, for the per-side check, found by `side_field`: None for a row of the
        whole shop."""
        if self.side_field is None:
            return None
        if self.side_field == "pk":
            return row.pk
        # The link's id (`side_id`), read without loading the side. No default: a wrong name raises.
        return cast("uuid.UUID | None", getattr(row, f"{self.side_field}_id"))

    def check_side_permission(self, request: Request, side_id: uuid.UUID | None) -> None:
        """The per-side check (03 §5.4): may the person acting do this action (`self.action`) on this side, or
        on the whole shop when `side_id` is None? Asked for each row handed out one at a time: read, edited,
        or made, and a create's repeat as a read of the stored row. A list is narrowed by visible_sides()
        instead. Refuses with PermissionDenied. PPL-3 fills it in with its permission codes; until then,
        anyone logged in at the open shop may."""

    def check_object_permissions(self, request: Request, obj: Any) -> None:
        # DRF calls this for every row get_object() hands out, to read it or to change it: the usual
        # checks, then the side's.
        super().check_object_permissions(request, obj)
        self.check_side_permission(request, self.side_of(obj))


class CreateOnceMixin[M: ShopScoped](ShopViewSet[M]):
    """POST: make a row once, however many times the same request arrives (ADR-0007, 03 §5.10).

    The client makes the new row's id and sends it with the row. A phone whose answer was lost sends the
    same request again, with the same id, and gets the stored row back, with the same 201: the row as it is
    now, so if someone edited it in between, the answer shows the edit. The id names the create: a repeat
    gets the stored row whatever else it carries. A route that makes rows builds on this, names what a
    create sends (`create_serializer_class`), and writes create_row(), which calls its service."""

    # What a create sends: the new row's fields, `id` among them, and required.
    create_serializer_class: type[serializers.BaseSerializer[Any]]

    def create_row(self, data: dict[str, Any]) -> M:
        """Make the new row from the checked input, through the route's service. Each route writes its own."""
        raise NotImplementedError

    def side_of_new(self, data: dict[str, Any]) -> uuid.UUID | None:
        """The side a new row will belong to, for the per-side check before it is made, found by
        `side_field` in what was sent: None for a row of the whole shop, and for a new side, which belongs to
        no side yet."""
        if self.side_field is None or self.side_field == "pk":
            return None
        side = data.get(self.side_field)
        return None if side is None else side.pk

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Sent before? Look first, before any check: the row a first send made would fail the checks of
        # its own retry (MFANO already has a side P: the first send's own).
        sent_id = request.data.get("id") if isinstance(request.data, dict) else None
        row = self._stored(sent_id)
        row = self._create(request) if row is None else self._replay(request, row)
        return Response(self.get_serializer(row).data, status=status.HTTP_201_CREATED)

    def _replay(self, request: Request, row: M) -> M:
        # A send this shop already has a row for gets that row back, as it is now: if it was edited since,
        # the answer shows the edit. Handed out like a row that is read, so the side's check applies, as on
        # a read. The one way back for every repeat, whichever look found it.
        self.check_object_permissions(request, row)
        return row

    def _create(self, request: Request) -> M:
        sent = self.create_serializer_class(data=request.data, context=self.get_serializer_context())
        sent.is_valid(raise_exception=True)
        data = sent.validated_data
        self.check_side_permission(request, self.side_of_new(data))
        try:
            # Its own transaction (inside an open one, such as a test's, a savepoint): a refused write undoes
            # only this part, and the visit can still look again and answer.
            with transaction.atomic():
                return self.create_row(data)
        except (ValidationError, IntegrityError) as refusal:
            # Refused. Perhaps by a twin: another copy of this very request, sent at the same moment, that
            # made the row while this copy was busy. Finished during this copy's checks, it makes them refuse
            # ("letter P is taken": by its own side); finished during its insert, the id clashes. The id
            # names the create, so if this shop now has a row with it, the twin made it: that is the answer.
            twin = self._stored(data["id"])
            if twin is not None:
                return self._replay(request, twin)
            if isinstance(refusal, IntegrityError) and _id_taken(refusal, self.model):
                # No twin, yet the id clashes: another shop's row has it. The guard hides that row from every
                # lookup here, and the answer says only that the id can't be used: nothing about that row,
                # not even what it is (03 §5.4).
                raise ValidationError({"id": ValidationError("This id is already in use.", code="id.taken")}) from None
            # A real refusal, such as a second side D, answered with its code; or another database rule, which
            # the service should have checked first: a bug, left to become a 500.
            raise

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
