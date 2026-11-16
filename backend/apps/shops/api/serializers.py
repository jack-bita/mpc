"""apps/shops/api/serializers.py — how the shops tables look in the API (03 §5.10).

Thin: they describe fields and check their shape. Every write goes through apps/shops/services.py
(ADR-0015), which checks the rules. A route answers with one serializer, how a row looks (SideSerializer),
and takes what a create sends and what an edit sends with others (SideCreateSerializer, SideEditSerializer).
The settings routes (SHOP-3) answer a rule's row (SettingSerializer), take a new one (SettingCreateSerializer), and
list every rule as the settings page shows it (ShopRulesAnswer). The closures routes (ATT-8) answer a closure
(ClosureSerializer), take a new one (ClosureCreateSerializer), a cancel's reason (ClosureReasonSerializer) and a new
last day (ClosureLastDaySerializer), and list those to come (ShopClosuresAnswer).
"""

from typing import Any

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.core.api.ids import uuid7_only
from apps.core.settings_registry import KEYS, KINDS, Scope
from apps.shops.api.fields import SideField
from apps.shops.models import Closure, Setting, Side


class SideSerializer(serializers.ModelSerializer[Side]):
    # A side as the app reads it. No `shop`: it is always the visit's own (apps/core/api/base.py). The app
    # keeps `version` and sends it back with an edit (apps/core/editing.py).
    class Meta:
        model = Side
        fields = ["id", "code", "name", "sale_flow", "is_live", "band", "created_at", "updated_at", "version"]
        read_only_fields = fields


class SideCreateSerializer(serializers.ModelSerializer[Side]):
    # What the app sends to add a side, with the id it made itself (ADR-0007). The letter and the name are
    # checked again by the service (full_clean): "d" is stored as "D", and a second D is refused. The sale flow and the
    # band may be left out, for add_side's own defaults.
    class Meta:
        model = Side
        fields = ["id", "code", "name", "sale_flow", "band"]
        extra_kwargs = {
            # Required, and a UUIDv7: without an id of its own, a phone's retry would look like a new side
            # (apps/core/api/ids.py). No unique check of the id here: the route looks the id up itself, first
            # and again after any refusal, and answers a repeat with the stored side (CreateOnceMixin,
            # apps/core/api/base.py). DRF's check would only add a query, and refuse a repeat before the
            # route could look.
            "id": {"required": True, "validators": [uuid7_only]},
        }


# The changes an edit of a side may send, one at a time (SideEditSerializer.validate).
SIDE_CHANGES = ("name", "is_live", "band")


class SideEditSerializer(serializers.ModelSerializer[Side]):
    # What the app sends to change a side: a new name, the on/off switch (SHOP-3), or the band under its top bar
    # (SHOP-4), and the version of the side it read. Never the letter: it is printed on receipts and never changes.
    # Anything else sent is ignored.
    # `version` is declared here: the model keeps it out of every form and API field (editable=False), since
    # only apps/core/editing.py writes it; here it is what the client read, not a value to store.
    version = serializers.IntegerField(min_value=1)

    class Meta:
        model = Side
        fields = ["name", "is_live", "band", "version"]
        # Each may be left out, as an edit sends one of them; validate() asks for exactly one.
        extra_kwargs = {"name": {"required": False}, "is_live": {"required": False}, "band": {"required": False}}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # One change at a time: a rename, a switch and a band are three services (rename_side, switch_side,
        # set_side_band), each checking the version the app read, so the second of two in one request would always find
        # the version moved on. A screen sends one, so anything else is a bug in the app: the plain `invalid`, with no
        # sentence of its own.
        if sum(change in attrs for change in SIDE_CHANGES) != 1:
            raise serializers.ValidationError("Send a new name, the switch or a band, one at a time.", code="invalid")
        return attrs


# The registry's keys, kinds and scopes as fixed choices, so the app's types know each one by name. The kinds and scopes
# are the very lists the bootstrap names (SettingKindEnum, SettingScopeEnum, ENUM_NAME_OVERRIDES in
# config/settings/base.py), built the same way here, as `shops` may not import `sync`: the schema matches a list by its
# choices, so both answers share one type. The keys are named there too (SettingKeyEnum).
SETTING_KEYS = [key.key for key in KEYS]
SETTING_KINDS = [kind.code for kind in KINDS]
SETTING_SCOPES = [scope.value for scope in Scope]


class SettingSerializer(serializers.ModelSerializer[Setting]):
    # A rule's row as the office reads it: the bootstrap's fields (SettingRecord), and the owner's note, who set it and
    # when, which stay in the office. `set_by` is the nickname the screens show, read through the row's `created_by`,
    # not imported: `shops` may not name `people` (ADR-0043). None for a row the system wrote, as a seed does.
    set_by = serializers.CharField(source="created_by.display_name", allow_null=True, read_only=True)

    class Meta:
        model = Setting
        fields = ["id", "key", "side", "value", "effective_from", "note", "set_by", "created_at"]
        read_only_fields = fields


class SettingCreateSerializer(serializers.ModelSerializer[Setting]):
    # What the settings page sends for a new value, with the id it made itself (ADR-0007). The key stays plain text
    # here: an unknown one is refused by Setting.clean() with its own code (setting.key_unknown), beside the others.
    # The side is one of the visit's shop that the person sees, or "not found" (SideField); none for a shop's rule.
    side = SideField(required=False, allow_null=True)

    class Meta:
        model = Setting
        fields = ["id", "key", "side", "value", "effective_from", "note"]
        extra_kwargs = {
            # Required, and a UUIDv7, as for a new side (SideCreateSerializer): the route looks the id up itself.
            "id": {"required": True, "validators": [uuid7_only]},
        }


class RuleAnswer(serializers.Serializer[Any]):
    # One line of the settings page (Rule, apps/shops/selectors.py).
    key = serializers.ChoiceField(choices=SETTING_KEYS)
    kind = serializers.ChoiceField(choices=SETTING_KINDS)
    scope = serializers.ChoiceField(choices=SETTING_SCOPES)
    side = serializers.UUIDField(source="side.pk", allow_null=True, help_text="Empty for a rule of the whole shop.")
    default = serializers.CharField()
    value = serializers.CharField(help_text="The value in force today, as its kind writes it.")
    rows = SettingSerializer(many=True)


# many=False: the answer is one object, not a list, although the route's action is `list`. Without it the schema would
# describe an array of these, and the app's types with it.
@extend_schema_serializer(many=False)
class ShopRulesAnswer(serializers.Serializer[Any]):
    # Every rule as the settings page shows it, and the shop's today: the page's date box starts there, as a new value
    # can't start before it (setting.date_past).
    today = serializers.DateField()
    rules = RuleAnswer(many=True)


class ClosureSerializer(serializers.ModelSerializer[Closure]):
    # A closure as the office reads it (ATT-8). `added_by` is the nickname the screens show, read through the row's
    # `created_by`, as a rule's `set_by` is: `shops` may not name `people` (ADR-0043). None for one the system added, as
    # the demo's seed does.
    added_by = serializers.CharField(source="created_by.display_name", allow_null=True, read_only=True)

    class Meta:
        model = Closure
        fields = ["id", "first_day", "last_day", "name", "status", "added_by", "created_at"]
        read_only_fields = fields


class ClosureCreateSerializer(serializers.ModelSerializer[Closure]):
    # What the page sends for a new closure, with the id it made itself (ADR-0007). The rest is add_closure's to check,
    # each mistake beside its box in its own code: a name of spaces is let through here, so the service refuses it with
    # its own sentence (closure.name_blank) instead of the form's plain `blank`; one left out is the form's `required`.
    class Meta:
        model = Closure
        fields = ["id", "first_day", "last_day", "name"]
        extra_kwargs = {
            # Required, and a UUIDv7, as for a new side (SideCreateSerializer): the route looks the id up itself.
            "id": {"required": True, "validators": [uuid7_only]},
            "name": {"allow_blank": True},
        }


class ClosureReasonSerializer(serializers.Serializer[Any]):
    # What Ondoa sends: why, kept in its audit line with who and when (rule 7). A blank reason is let through, so the
    # service refuses it with its own code, closure.reason_required, beside the box; one left out is the form's own
    # `required`. 500 characters at most, as the audit line keeps (control.AuditEvent), as a device's block does.
    reason = serializers.CharField(max_length=500, allow_blank=True)


class ClosureLastDaySerializer(ClosureReasonSerializer):
    # What a moved last day sends: the new last day, and why, as for a cancel.
    last_day = serializers.DateField()


# many=False, as for ShopRulesAnswer: the answer is one object, though the route's action is `list`.
@extend_schema_serializer(many=False)
class ShopClosuresAnswer(serializers.Serializer[Any]):
    # The closures to come, as the settings page lists them, and the shop's today: the page's date boxes start there, as
    # a closure can't start before it (closure.date_past), and it tells which closures have begun (no Ondoa).
    today = serializers.DateField()
    closures = ClosureSerializer(many=True)
