"""apps/shops/api/views.py — the shops routes, under /api/v1/shops/ (03 §5.10).

Thin: each one reads through the guard of the visit's shop (ShopViewSet, apps/core/api/base.py) and
writes through a service (ADR-0015). For now a shop's sides: the list, one side, and adding one.
"""

import uuid
from typing import Any

from rest_framework import mixins

from apps.core.api.base import CreateOnceMixin
from apps.shops.api.serializers import SideCreateSerializer, SideSerializer
from apps.shops.models import SaleFlow, Shop, Side
from apps.shops.services import add_side


class SideViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CreateOnceMixin[Side]):
    # GET sides/ lists the visit's shop's sides, in pages; GET sides/{id}/ reads one; POST sides/ adds one.
    model = Side
    serializer_class = SideSerializer
    create_serializer_class = SideCreateSerializer

    def side_of(self, row: Side) -> uuid.UUID:
        # A side is its own side: whoever may act on Dawa may see Dawa.
        return row.pk

    def create_row(self, data: dict[str, Any]) -> Side:
        # Adding a side also makes its stock location and its cash drawer (add_side). The shop is always the
        # visit's own. A new side belongs to no side yet, so the per-side check asks about the whole shop
        # (side_of_new finds no `side` in what was sent).
        return add_side(
            shop=Shop.objects.get(pk=self.actor.shop_id),
            side_id=data["id"],
            code=data["code"],
            name=data["name"],
            sale_flow=data.get("sale_flow", SaleFlow.ONE_SCREEN),
            by=self.actor,
        )
