"""apps/shops/api/views.py — the shops routes, under /api/v1/shops/ (03 §5.10).

Thin: each one reads through the guard of the visit's shop (ShopViewSet, apps/core/api/base.py) and
writes through a service (ADR-0015). For now a shop's sides: the list, one side, adding one, and
renaming one, switching it on or off (SHOP-3) or giving it its band (SHOP-4); the shop's rules: every one with its
value today and its rows, and a new value from a day on (SHOP-3); and the days the shop is closed: those to come, a new
one, a cancel and a new last day (ATT-8).
"""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import SEES_THE_SIDE, CreateOnceMixin, EditMixin
from apps.core.permissions import Permission
from apps.shops.api.serializers import (
    ClosureCreateSerializer,
    ClosureLastDaySerializer,
    ClosureReasonSerializer,
    ClosureSerializer,
    SettingCreateSerializer,
    SettingSerializer,
    ShopClosuresAnswer,
    ShopRulesAnswer,
    SideCreateSerializer,
    SideEditSerializer,
    SideSerializer,
)
from apps.shops.models import Closure, Setting, Shop, Side
from apps.shops.selectors import coming_closures, shop_rules, shop_today
from apps.shops.services import (
    add_closure,
    add_side,
    cancel_closure,
    change_last_day,
    rename_side,
    set_setting,
    set_side_band,
    switch_side,
)


class SideViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CreateOnceMixin[Side], EditMixin[Side]):
    # GET sides/ lists the visit's shop's sides, in pages; GET sides/{id}/ reads one; POST sides/ adds one;
    # PATCH sides/{id}/ renames one, switches it on or off, or gives it its band.
    model = Side
    # A side is its own side, found by its own id: whoever may act on Dawa may see Dawa (side_of()), and a
    # list shows the sides a person may see (visible_sides()). A new side belongs to no side yet, so adding
    # one is checked as an action on the whole shop (side_of_new()).
    side_field = "pk"
    # Anyone who works on a side may see it. Adding a side, renaming one, switching it on or off or changing its band
    # changes the shop itself: the shop's rules (`settings.manage`), one of the owner's own four (spec §6). Adding one
    # asks on the whole shop; renaming, switching one or changing its band, on that side (PPL-5).
    action_permissions = {
        "list": SEES_THE_SIDE,
        "retrieve": SEES_THE_SIDE,
        "create": Permission.SETTINGS_MANAGE,
        "partial_update": Permission.SETTINGS_MANAGE,
    }
    serializer_class = SideSerializer
    create_serializer_class = SideCreateSerializer
    edit_serializer_class = SideEditSerializer

    def create_row(self, data: dict[str, Any]) -> Side:
        # Adding a side also makes its stock location and its cash drawer (add_side). The shop is always the
        # visit's own. A sale flow and a band are passed on only when the app sent them: otherwise add_side's own
        # defaults apply, so each default is written in one place.
        chosen = {name: data[name] for name in ("sale_flow", "band") if name in data}
        return add_side(
            shop=Shop.objects.get(pk=self.actor.shop_id),
            side_id=data["id"],
            code=data["code"],
            name=data["name"],
            by=self.actor,
            **chosen,
        )

    def edit_row(self, row: Side, data: dict[str, Any]) -> Side:
        # A new name, the switch or a band, never two: SideEditSerializer has checked that exactly one came.
        if "is_live" in data:
            return switch_side(row, version=data["version"], is_live=data["is_live"], by=self.actor)
        if "band" in data:
            return set_side_band(row, version=data["version"], band=data["band"], by=self.actor)
        return rename_side(row, version=data["version"], name=data["name"], by=self.actor)


class SettingViewSet(CreateOnceMixin[Setting]):
    # GET settings/ lists every rule as the settings page shows it (SHOP-5); POST settings/ gives one a new value from a
    # day on. No address for one row, nor any edit: a rule's rows are never changed, only added to (ADR-0013).
    model = Setting
    # A rule's row keeps its side in `side`: empty for a rule of the whole shop, which whoever sees a side may see.
    side_field = "side"
    # Seeing the rules needs only to see a side (default, SHOP-3): every rule already travels to every laptop of the
    # shop (SYNC-2), so the page hides nothing a counter doesn't hold. A new value changes the shop's rules:
    # `settings.manage`, the owner's (spec §6), asked on the row's side, or on the whole shop for a shop's rule.
    action_permissions = {
        "list": SEES_THE_SIDE,
        "create": Permission.SETTINGS_MANAGE,
    }
    serializer_class = SettingSerializer
    create_serializer_class = SettingCreateSerializer
    # One answer, not pages: the registry is a short list, and the page shows it whole.
    pagination_class = None

    def base_rows(self) -> QuerySet[Setting]:
        # Each row names who set it (`set_by`): their staff row comes in the same read, not one read per row.
        return super().base_rows().select_related("created_by")

    @extend_schema(responses=ShopRulesAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        shop = Shop.objects.get(pk=self.actor.shop_id)
        # The rows and the sides the person sees: get_queryset() keeps the rows to them, and the sides are read the same
        # way (None: every side). The read itself is the selector's (apps/shops/selectors.py).
        seen = self.visible_sides(request)
        sides = Side.objects.order_by("code") if seen is None else Side.objects.filter(pk__in=seen).order_by("code")
        today = shop_today(shop)
        rules = shop_rules(shop, rows=self.get_queryset(), sides=list(sides), on=today)
        return Response(ShopRulesAnswer({"today": today, "rules": rules}).data)

    def create_row(self, data: dict[str, Any]) -> Setting:
        # The shop is always the visit's own; set_setting checks the rest, and refuses with its codes.
        return set_setting(
            Shop.objects.get(pk=self.actor.shop_id),
            setting_id=data["id"],
            key=data["key"],
            value=data["value"],
            effective_from=data["effective_from"],
            side=data.get("side"),
            note=data.get("note", ""),
            by=self.actor,
        )


class ClosureViewSet(CreateOnceMixin[Closure]):
    # GET closures/ lists those to come (ATT-9's list); POST closures/ adds one; POST closures/{id}/cancel/ is Ondoa;
    # POST closures/{id}/last-day/ moves its last day. No address to read one, nor any edit: a closure changes only by
    # its two actions, each with a reason (ATT-8).
    model = Closure
    # A closure belongs to the whole shop: a funeral closes both sides.
    side_field = None
    # Seeing them needs only to see a side: a worker may know when the shop is closed. Every change needs
    # `settings.manage` on the whole shop, the owner's (spec §6), as a closed day changes everyone's pay.
    action_permissions = {
        "list": SEES_THE_SIDE,
        "create": Permission.SETTINGS_MANAGE,
        "cancel": Permission.SETTINGS_MANAGE,
        "last_day": Permission.SETTINGS_MANAGE,
    }
    serializer_class = ClosureSerializer
    create_serializer_class = ClosureCreateSerializer
    # One answer, not pages: a shop closes a handful of days a year, and the page shows them all.
    pagination_class = None

    def base_rows(self) -> QuerySet[Closure]:
        # Each closure names who added it (`added_by`): their staff row comes in the same read, not one read per row.
        return super().base_rows().select_related("created_by")

    @extend_schema(responses=ShopClosuresAnswer)
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        today = shop_today(Shop.objects.get(pk=self.actor.shop_id))
        closures = coming_closures(self.get_queryset(), today=today)
        return Response(ShopClosuresAnswer({"today": today, "closures": closures}).data)

    def create_row(self, data: dict[str, Any]) -> Closure:
        # The shop is always the visit's own; add_closure checks the rest, and refuses with its codes.
        return add_closure(
            Shop.objects.get(pk=self.actor.shop_id),
            closure_id=data["id"],
            first_day=data["first_day"],
            last_day=data["last_day"],
            name=data["name"],
            by=self.actor,
        )

    # Each action names what it takes and answers: the API's description would otherwise read every POST of this route
    # as a create (RouteSchema, apps/core/api/schema.py), and the app's types would be wrong (UI-2).
    @extend_schema(request=ClosureReasonSerializer, responses=ClosureSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        # The closure first, among the visit's shop's (get_object): another shop's is "not found", as an id no shop has,
        # before what was sent is even read (03 §5.4). Then the reason's shape; the service checks the rest.
        closure = self.get_object()
        sent = ClosureReasonSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        changed = cancel_closure(closure, reason=sent.validated_data["reason"], by=self.actor)
        return Response(self.get_serializer(changed).data)

    @extend_schema(request=ClosureLastDaySerializer, responses=ClosureSerializer)
    @action(detail=True, methods=["post"], url_path="last-day")
    def last_day(self, request: Request, pk: str | None = None) -> Response:
        # As cancel: the closure first, then what was sent.
        closure = self.get_object()
        sent = ClosureLastDaySerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        changed = change_last_day(
            closure, last_day=sent.validated_data["last_day"], reason=sent.validated_data["reason"], by=self.actor
        )
        return Response(self.get_serializer(changed).data)
