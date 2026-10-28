"""apps/shops/api/views.py — the shops routes, under /api/v1/shops/ (03 §5.10).

Thin: each one reads through the guard of the visit's shop (ShopViewSet, apps/core/api/base.py) and
writes through a service (ADR-0015). For now a shop's sides: the list, and one side.
"""

import uuid

from rest_framework import mixins

from apps.core.api.base import ShopViewSet
from apps.shops.api.serializers import SideSerializer
from apps.shops.models import Side


class SideViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ShopViewSet[Side]):
    # GET sides/ lists the visit's shop's sides, in pages; GET sides/{id}/ reads one.
    model = Side
    serializer_class = SideSerializer

    def side_of(self, row: Side) -> uuid.UUID:
        # A side is its own side: whoever may act on Dawa may see Dawa.
        return row.pk
