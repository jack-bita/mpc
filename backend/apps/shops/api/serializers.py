"""apps/shops/api/serializers.py — how the shops tables look in the API (03 §5.10).

Thin: they describe fields and check their shape. Every write goes through apps/shops/services.py
(ADR-0015), which checks the rules. A route answers with one serializer, how a row looks (SideSerializer),
and takes what a create sends with another (SideCreateSerializer).
"""

from rest_framework import serializers

from apps.shops.models import Side


class SideSerializer(serializers.ModelSerializer[Side]):
    # A side as the app reads it. No `shop`: it is always the visit's own (apps/core/api/base.py).
    class Meta:
        model = Side
        fields = ["id", "code", "name", "sale_flow", "is_live", "created_at"]
        read_only_fields = fields


class SideCreateSerializer(serializers.ModelSerializer[Side]):
    # What the app sends to add a side, with the id it made itself (ADR-0007). The letter and the name are
    # checked again by the service (full_clean): "d" is stored as "D", and a second D is refused.
    class Meta:
        model = Side
        fields = ["id", "code", "name", "sale_flow"]
        extra_kwargs = {
            # Required: without its own id, a phone's retry would look like a new side. No unique check of
            # the id here: the route looks the id up itself first, and a clash at the insert is its answer
            # (CreateOnceMixin, apps/core/api/base.py). DRF's check would only add a query, and turn two
            # copies of one request at the same moment into a refusal instead of one side.
            "id": {"required": True, "validators": []},
        }
