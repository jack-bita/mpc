"""apps/core/api/base.py — the base of every office route: one shop per visit, rows built per visit and kept to
the sides the person sees, and the per-side permission check of every action (03 §5.4, §5.10; PPL-5).

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
- The sides and the keys (02 §5, X1; PPL-5). Each route names, in `action_permissions`, what each of its actions
  needs: a permission code, or SEES_THE_SIDE for an action that only shows rows. An action it doesn't name is
  refused with a server error before it starts, so no action is ever open by forgetting. The person a login names
  hands over their keys once a visit (a Person, apps/core/permissions.py), since `core` may not import `people`.
  visible_sides(): the sides the person holds any key on; every read the route makes keeps to them, so a list
  never shows the others and their rows are "not found". check_side_permission(): may the person do this action on
  this side, asked for each row edited or made one at a time, and on the whole shop for a change to a whole list.
  A person who is suspended, or has left, holds no key, so they see nothing and do nothing.
- Creates: a route that makes rows adds CreateOnceMixin. The client sends the new row's id (ADR-0007), so
  the same request sent twice makes one row, and an id already used in another shop is refused.
- Edits: a route that changes rows adds EditMixin. The client sends the `version` it read, so an edit made
  on an old copy is refused (409 version_conflict) instead of undoing someone else's.

Long lists come in pages through CursorPage (apps/core/api/pagination.py), the default for every list.
"""

import enum
import uuid
from collections.abc import Collection, Mapping
from contextlib import ExitStack
from functools import cached_property
from typing import Any, ClassVar, cast

import psycopg
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, models, transaction
from django.http import HttpRequest, HttpResponseBase
from rest_framework import exceptions, serializers, status
from rest_framework.permissions import SAFE_METHODS
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.acting import acting_as
from apps.core.models import Editable, ShopScoped
from apps.core.permissions import HeldPermissions, Permission, Person
from apps.core.tenancy import Actor, shop_context


class Sight(enum.Enum):
    # What an action that only shows rows needs: no key of its own, only to see the row's side. Its own value, not
    # None: None is what a forgotten action reads as (`.get()`), and those two must never be mixed up.
    SEES_THE_SIDE = "sees_the_side"


SEES_THE_SIDE = Sight.SEES_THE_SIDE


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
    # What each action of the route needs, by the action's name as DRF's router gives it ("list", "create",
    # "partial_update", or an @action's own name): a permission code, asked on the row's side, or on the whole shop
    # for a row of no side; or SEES_THE_SIDE, for an action that only shows rows. Each route writes its own, naming
    # every action it answers. Empty here, so every action of a route that names nothing is refused with a server error
    # (permission_needed(), PPL-5).
    action_permissions: ClassVar[Mapping[str, Permission | Sight]] = {}
    # The methods an office route may answer: DRF's list, less OPTIONS and TRACE, which initial() refuses. Listed so
    # that a 405's `Allow` header names only methods that can work.
    http_method_names = ["get", "post", "put", "patch", "delete", "head"]

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

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        # DRF's checks before any action runs: the login (above), its permission classes and its throttles. Then
        # ours, before the action reads or writes anything (PPL-5).
        super().initial(request, *args, **kwargs)
        if self.action is None or self.action == "metadata":
            # A method the route doesn't answer, such as PUT on a list: DRF leaves the action empty and would answer
            # 405 after these checks, so it is answered 405 here, before the naming check below takes the empty action
            # for a forgotten one. OPTIONS too (DRF's `metadata`): it would describe the route, the forms of the
            # actions included, to anyone logged in, even a person who may do none of them; the API's own description
            # is the schema (apps/core/api/schema.py).
            raise exceptions.MethodNotAllowed(request.method or "")
        # Every action is named, a route's own @actions included, before it reads or writes anything.
        self.permission_needed()
        lookup = self.lookup_url_kwarg or self.lookup_field
        # CreateOnceMixin's own create asks with the new row's side, once it has read what was sent. Only that one:
        # DRF's own CreateModelMixin, or a create a route writes over it, never asks, so it is asked here with the
        # rest. Compared with the method itself, not by the mixin's name: a route can list DRF's mixin before ours,
        # and then DRF's create is the one that runs.
        asks_for_itself = self.action == "create" and getattr(type(self), "create", None) is CreateOnceMixin.create
        if request.method in SAFE_METHODS:
            # Showing rows needs only to see their sides, which every read of the route keeps to (get_queryset).
            return
        if lookup in self.kwargs:
            # A change to one row: the row is found and checked now, with its own side, before the action runs
            # (get_object(), which asks check_object_permissions()). So an @action that finds its row some other way,
            # or never asks, is still checked, and a row the person can't see is "not found" before anything changes.
            # The action looks it up again when it runs: one more small query, for a check nothing can skip.
            self.get_object()
        elif not asks_for_itself:
            # A change sent to a whole list, not to one row, such as clearing it, or a create that doesn't ask: no
            # row's side to ask about, so it is asked on the whole shop, the most it could touch.
            self.check_side_permission(request, None)

    def permission_needed(self) -> Permission | Sight:
        """What this visit's action needs, as the route names it in `action_permissions`. A route that doesn't name
        the action is a bug: refused here with a server error, which is logged, never a 403 that would hide the bug
        behind a plain "no", nor a pass that would open the action to everyone."""
        needed = self.action_permissions.get(self.action or "")
        if needed is None:
            raise ImproperlyConfigured(
                f"{type(self).__name__} names no permission for its action {self.action!r} (action_permissions)."
            )
        if needed is not SEES_THE_SIDE and self.request.method in SAFE_METHODS:
            # A show action behind a key of its own, as debts (debt.view) and reports (report.view) will be. Nothing
            # yet keeps its rows to the sides where that key is held: it would show every side the person sees. The
            # first card that shows rows behind a key builds that (Jack, PPL-5; CAT-2's note).
            raise ImproperlyConfigured(
                f"{type(self).__name__}.{self.action} shows rows behind {needed}: "
                "a show action with a key of its own waits for the card that first needs one (PPL-5)."
            )
        if needed is SEES_THE_SIDE and self.request.method not in SAFE_METHODS:
            # The mirror rule: a change (a create, an edit, a void) always needs a key of its own. Seeing a side is not
            # leave to change it: named so, the change would be open to anyone who works there, a Worker included.
            raise ImproperlyConfigured(
                f"{type(self).__name__}.{self.action} changes rows and names no key for it: "
                "a change needs a permission code of its own (PPL-5)."
            )
        return needed

    @cached_property
    def held(self) -> HeldPermissions:
        # Every key the person acting holds, side by side, read once for the visit and kept on the view, which DRF
        # makes new for each visit: a list costs the same few queries however many sides a shop has (Jack, PPL-5).
        # Never kept on the person in `request.auth`: the same object can come back for another visit (a test's
        # client sends it to each one), and a copy kept there would outlive a suspension (X2).
        # cast: perform_authentication() has refused any login that names no staff member, and a staff member is
        # a Person (apps/core/permissions.py).
        return cast(Person, self.actor).held_permissions()

    def base_rows(self) -> models.QuerySet[M]:
        """The route's rows before they are kept to the person's sides. A route that needs more from its rows, such
        as their linked rows loaded with them (`select_related`), writes over this, building on super(), and never
        over get_queryset(), which keeps every read to the person's sides: a test refuses a route that does
        (backend/tests/test_route_permissions.py)."""
        # Built on each visit, inside the visit's shop. The default manager is the guarded `objects`, which
        # ShopScoped makes the default of every shop's table (CORE-2); CORE-7's sweep checks they all keep it.
        # cast: mypy reads the manager of `type[M]` as ShopScoped's, though the rows are this route's table's.
        return cast("models.QuerySet[M]", self.model._default_manager.all())

    def get_queryset(self) -> models.QuerySet[M]:
        if getattr(self, "swagger_fake_view", False):
            # drf-spectacular is describing the route (apps/core/api/schema.py), with no visit, so with no
            # shop. It only needs the table, to tell the type of the id in the address. An empty query, built
            # without the guard, can return no row.
            return models.QuerySet(self.model).none()
        rows = self.base_rows()
        # Then kept to the sides the person sees, here, where every read of the route starts: a list, the one row a
        # read or an edit looks up (get_object), a create's look for a repeat, and any @action of the route's own,
        # which may read rows without DRF's filter_queryset(). Rows of a side the person may not see are left out
        # of all of them, so a hidden side is not even shown to exist: its rows are "not found", as another shop's
        # are (03 §5.4).
        sides = self.visible_sides(self.request)
        if sides is None:
            return rows
        if self.side_field is None:
            # A row of the whole shop, such as a product, has no side to hide it behind: whoever sees a side sees
            # it, and whoever sees none, such as a person suspended, sees none of those rows either.
            return rows if sides else rows.none()
        return rows.filter(**{f"{self.side_field}__in": sides})

    # True while CreateOnceMixin hands back the row a create already made: nothing is made, so the row is checked as a
    # read, not for the create's key (CreateOnceMixin._replay). Every other check on the row still runs.
    _replaying = False

    # Where a row keeps its side, read by both side hooks: `side` on most tables; the link's own name on a
    # table that names it otherwise (a device's `home_side`); "pk" on a route whose rows are sides themselves
    # (SideViewSet); None on a table whose rows belong to the whole shop, such as products. A name the table
    # doesn't have fails loudly on a read or an edit (side_of() reads the link's id), but quietly on a create:
    # side_of_new() looks for it in what was sent, finds nothing, and checks the new row as one of the whole
    # shop. So CORE-7's sweep checks every route's name against its table (test_every_side_link_is_named_on_its_route).
    side_field: str | None = "side"

    def visible_sides(self, request: Request) -> Collection[uuid.UUID] | None:
        """The sides whose rows the person acting may see: those they hold at least one key on, or None for all of
        them, a side added later included, when a key of theirs covers every side (02 §5, X1)."""
        return self.held.sides_seen()

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
        on the whole shop when `side_id` is None? Asked for each row handed out one at a time, read, edited or
        made, and for a change to a whole list. Refuses with PermissionDenied, which the error handler answers as
        403 permission_denied (apps/core/api/errors.py)."""
        needed = self.permission_needed()
        if needed is SEES_THE_SIDE or self._replaying:
            # Only to see the side, which every read of the route already keeps to (get_queryset): a row handed out
            # was found among the person's own sides. A create sent again is such a read too (_replay below).
            return
        if needed not in self.held.on(side_id):
            # English for the logs; the screens translate the code (ADR-0032).
            raise exceptions.PermissionDenied(f"This person may not {needed} here.")

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
        # the answer shows the edit. Handed out like a row that is read: it was found among the person's own
        # sides (get_queryset), as any read is, so they may see it. Nothing is made, so the create's own key is not
        # asked again: a phone whose answer was lost gets it, even if the person's keys changed in between. Every
        # other check on the row runs as for any row handed out, a route's own included. The one way back for every
        # repeat, whichever look found it.
        self._replaying = True
        try:
            self.check_object_permissions(request, row)
        finally:
            self._replaying = False
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
                # No twin, yet the id clashes: another row has it that this visit can't see, another shop's, or
                # this shop's on a side the person doesn't see (get_queryset keeps to their sides). Every lookup here
                # hides that row, and the answer says only that the id can't be used: nothing about that row, not
                # even what it is (03 §5.4).
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
        # The row, found among the person's own sides and checked for the edit's key on its side (get_object, which
        # initial() already ran once before this action began). Another shop's row, or one on a side the person
        # doesn't see, is not found, as for a read.
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
