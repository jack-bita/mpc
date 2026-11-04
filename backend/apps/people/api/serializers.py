"""apps/people/api/serializers.py — how the people tables look in the API (03 §5.10).

Thin: they describe fields and their shape; every write goes through apps/people/services.py (ADR-0015). Today a
shop's devices on the office routes (AUTH-5): a device as the device list shows it, and what a manager sends to say
yes to a waiting one, to rename one, and to block or unblock one; what the owner sends to set a temporary password
(AUTH-6); and the answers of the two routes a device calls with its key (apps/people/api/views.py). A key, a key's hash
or a PIN's hash is never among the fields: they never leave the server (03 §5.9).
"""

from typing import Any

from rest_framework import serializers

from apps.core.api.ids import uuid7_only
from apps.people.models import Device, PairingRequest
from apps.shops.api.fields import SideField
from apps.shops.models import Shop, Side


class DeviceSerializer(serializers.ModelSerializer[Device]):
    # A device as the shop's device list shows it (UI-3): its name, its code for receipt numbers (D7), its home side,
    # whether it works, and when its key last reached the server, so a stolen phone that keeps calling shows when. No
    # `shop`: it is always the visit's own. The app keeps `version` and sends it back with a rename
    # (apps/core/editing.py). Never the key's hash.
    class Meta:
        model = Device
        fields = ["id", "name", "code", "home_side", "status", "last_seen_at", "created_at", "updated_at", "version"]
        read_only_fields = fields


class DeviceConfirmSerializer(serializers.ModelSerializer[Device]):
    # What the manager's phone sends to say yes to a waiting device (03 §5.9, step 2): the new device's id, made on the
    # phone (ADR-0007), the code the device shows, the name it gets and its home side. confirm_pairing checks the rest:
    # the code, the name, and device.manage on the side.
    # `pairing_code`, not `code`: a device's `code` is its number in receipt numbers (D7), which the answer shows. As a
    # person types it, in any case, with a dash or spaces; the service cleans it (clean_typed_code). 20 characters at
    # most: the 8 of a code, with room for those.
    pairing_code = serializers.CharField(max_length=20)
    # A side of the visit's shop that the manager sees; any other is "not found" (apps/shops/api/fields.py).
    home_side = SideField()

    class Meta:
        model = Device
        fields = ["id", "pairing_code", "name", "home_side"]
        extra_kwargs = {
            # Required, and a UUIDv7: without an id of its own, a double tap would look like a second device
            # (apps/core/api/ids.py). No unique check of the id here: the route looks the id up itself, first and
            # again after any refusal, and answers a repeat with the stored device (CreateOnceMixin).
            "id": {"required": True, "validators": [uuid7_only]},
        }


class DeviceEditSerializer(serializers.ModelSerializer[Device]):
    # What the app sends to rename a device: the new name, and the version of the device it read. Only the name: its
    # code is printed in receipt numbers (D7) and never changes, and nothing moves a device to another home side yet.
    # Anything else sent is ignored.
    # `version` is declared here: the model keeps it out of every form and API field (editable=False), since only
    # apps/core/editing.py writes it; here it is what the client read, not a value to store.
    version = serializers.IntegerField(min_value=1)

    class Meta:
        model = Device
        fields = ["name", "version"]


class DeviceReasonSerializer(serializers.Serializer[Any]):
    # What a block or an unblock sends: why, kept in its audit line with who and when (rule 7). A blank reason is let
    # through, so the service refuses it with its own code, device.reason_required, which the screen translates; one
    # left out is the form's own `required`. 500 characters at most, as the audit line keeps (control.AuditEvent).
    reason = serializers.CharField(max_length=500, allow_blank=True)


class TemporaryPasswordSerializer(serializers.Serializer[Any]):
    # What the owner sends to set a person's temporary password (AUTH-6, ADR-0038). Only ever read in: the route answers
    # with nothing, and nothing shows a password back.
    # DRF takes the spaces off both ends, as allauth's login does with what is typed, and refuses one of only spaces: a
    # password stored with them could never log in. 128 characters at most, so a huge one can't be sent to the slow
    # hash. What makes a good password is the service's.
    password = serializers.CharField(max_length=128, write_only=True)
    # Why, kept in its audit line with who and when (T3). A blank reason is let through, so the service refuses it with
    # its own code, staff.reason_required. 500 characters at most, as the audit line keeps (control.AuditEvent).
    reason = serializers.CharField(max_length=500, allow_blank=True, write_only=True)


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
