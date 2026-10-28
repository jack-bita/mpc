"""apps/shops/api/serializers.py — how the shops tables look in the API (03 §5.10).

Thin: they describe fields and check their shape. Every write goes through apps/shops/services.py
(ADR-0015), which checks the rules.
"""

from rest_framework import serializers

from apps.shops.models import Side


class SideSerializer(serializers.ModelSerializer[Side]):
    # A side as the app reads it. No `shop`: it is always the visit's own (apps/core/api/base.py).
    class Meta:
        model = Side
        fields = ["id", "code", "name", "sale_flow", "is_live", "created_at"]
        read_only_fields = fields
