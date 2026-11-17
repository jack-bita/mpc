"""apps/demo/api/serializers.py — how the one-tap demo's answers look in the API (OPS-3, 03 §5.10).

Thin: they describe the answers' shape; the device is made by apps/demo/services.py (ADR-0015). The device's key is
never among the fields: it goes in its cookie only (AUTH-2).
"""

from typing import Any

from rest_framework import serializers

from apps.demo.services import DemoDevice, DemoPin


class DemoOpenSerializer(serializers.Serializer[Any]):
    # Whether Jaribu demo may show on this server's welcome screen: true only where the demo shop is the only shop.
    open = serializers.BooleanField(read_only=True)


class DemoPinSerializer(serializers.Serializer[DemoPin]):
    # One seller's PIN, for the PIN screen to show under the tile of this staff member (OPS-3). Public on purpose: it
    # opens only the demo's fake shop, made again every day, and the README prints it too.
    staff_id = serializers.UUIDField(read_only=True)
    pin = serializers.CharField(read_only=True)


class DemoDeviceSerializer(serializers.Serializer[DemoDevice]):
    # What one tap answers: the PINs to show. The device itself the app learns as every device does, from `me`
    # (apps/people/api/views.py), with the key its cookie now holds.
    pins = DemoPinSerializer(many=True, read_only=True)
