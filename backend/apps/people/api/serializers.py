"""apps/people/api/serializers.py — how the people tables look in the API (03 §5.10).

Thin: they describe fields and their shape; every write goes through apps/people/services.py (ADR-0015). Today the
answers of the two device routes (apps/people/api/views.py). A key, a key's hash or a PIN's hash is never among the
fields: they never leave the server (03 §5.9).
"""

from typing import Any

from rest_framework import serializers

from apps.people.models import Device, PairingRequest
from apps.shops.models import Shop, Side


class PairingStartSerializer(serializers.ModelSerializer[PairingRequest]):
    # What a new device gets back when it asks to join: the code to show on its screen, and until when it can be typed.
    # Never the key: an answer's body is what page scripts can read; the key goes in its cookie only.
    class Meta:
        model = PairingRequest
        fields = ["code", "expires_at"]
        read_only_fields = fields


class MeDeviceSerializer(serializers.ModelSerializer[Device]):
    # The device itself: its name on the manager's list, its code for receipt numbers (D7), and whether it works.
    # Never its key's hash.
    class Meta:
        model = Device
        fields = ["id", "name", "code", "status"]
        read_only_fields = fields


class MeSideSerializer(serializers.ModelSerializer[Side]):
    # The side it mostly serves, which the counter screens open on.
    class Meta:
        model = Side
        fields = ["id", "code", "name"]
        read_only_fields = fields


class MeShopSerializer(serializers.ModelSerializer[Shop]):
    # Its shop. Shown by name, so a code claimed by the wrong shop's manager is seen at once (03 §5.9).
    class Meta:
        model = Shop
        fields = ["id", "name", "code"]
        read_only_fields = fields


class DeviceMeSerializer(serializers.Serializer[Device]):
    # What a paired device learns about itself (03 §5.9, step 3), in three parts, read from the device and its two
    # links: the device's shop is the visit's own, open for the whole visit (DeviceView).
    device = MeDeviceSerializer(source="*")
    home_side = MeSideSerializer()
    shop = MeShopSerializer()

    def to_internal_value(self, data: Any) -> Any:
        # Only ever an answer: nothing is sent to this route.
        raise NotImplementedError
