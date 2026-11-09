"""apps/sync/api/serializers.py — the fields a shop's devices may see of each record they keep a copy of, and the
bootstrap's answer (SYNC-2; 03 §6.1, §6.4).

One serializer per table the registry sends (apps/sync/registry.py): a side, a payment account, a person at work, a
dated rule's row. Each names its fields one by one, never `__all__`, so a column a later card adds stays on the server
until someone decides it travels. What must never travel, buying prices, PIN hashes and passwords above all (03 §6.1,
the sync rules), is checked against these lists by test_bootstrap_secrets.py. Read-only: devices never write through
them; what a device makes travels as a document (SYNC-4). Then the bootstrap's answer, as the API schema describes it.
"""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.languages import Language
from apps.core.settings_registry import KINDS, Scope
from apps.people.models import Font, StaffMember
from apps.people.permissions import held_permissions
from apps.shops.models import PaymentAccount, Setting, Side


class SideRecord(serializers.ModelSerializer[Side]):
    # A side as a counter needs it: its letter starts every number printed there (D7), its name heads the screens, its
    # flow says how it sells (02 §4), and whether it is live yet (ADR-0033).
    class Meta:
        model = Side
        fields = ["id", "code", "name", "sale_flow", "is_live"]
        read_only_fields = fields


class PaymentAccountRecord(serializers.ModelSerializer[PaymentAccount]):
    # Where a payment can land, and for which sides. The Lipa Namba's number is printed for customers, so it is no
    # secret. `sides`: their ids, by letter, as payment_account_rows reads them.
    sides = serializers.PrimaryKeyRelatedField[Side](many=True, read_only=True)

    class Meta:
        model = PaymentAccount
        fields = ["id", "kind", "name", "provider", "number", "sides"]
        read_only_fields = fields


class SideKeysRecord(serializers.Serializer[Any]):
    # The codes a person was given on one side alone.
    side = serializers.UUIDField()
    permissions = serializers.ListField(child=serializers.CharField())


class StaffKeysRecord(serializers.Serializer[Any]):
    # A person's keys, side by side, as HeldPermissions keeps them (apps/core/permissions.py). On a side, a person holds
    # `every_side` plus that side's own codes; on the whole shop, `every_side` alone (02 §5). Codes given on every side
    # count on a side added later too, so a new side needs no person's row sent again.
    every_side = serializers.ListField(child=serializers.CharField())
    sides = SideKeysRecord(many=True)


class StaffRecord(serializers.ModelSerializer[StaffMember]):
    # A person at work, as a shared laptop needs them offline: the names for their tile on the PIN screen, whether they
    # are suspended (X2), when their PIN last changed, so the laptop drops its own check of the old one (SYNC-10), their
    # own language and font (UI-9), and their keys, so the counter checks them offline (03 §5.8). A photo joins with
    # PPL-4. Never the PIN's hash, a password, a phone or an email: whoever uses the laptop next could read them.
    # `pin_changed_at` is empty for someone with no PIN, which tells only that nobody can log in as them here.
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    language = serializers.ChoiceField(source="user.language", choices=Language.choices, read_only=True)
    font = serializers.ChoiceField(source="user.font", choices=Font.choices, read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = StaffMember
        fields = ["id", "full_name", "display_name", "status", "pin_changed_at", "language", "font", "permissions"]
        read_only_fields = fields

    @extend_schema_field(StaffKeysRecord)
    def get_permissions(self, staff: StaffMember) -> dict[str, Any]:
        # Worked out on the server by the one function the office routes and `me` use, so the laptop does no role
        # arithmetic and can't drift from 02 §5. Nothing for a person suspended (X2). Two queries a person: a shop has a
        # handful of people. Codes A to Z and sides by id, so the same keys always read the same; a side left with no
        # codes, as a role emptied by its owner leaves, opens nothing, so isn't listed.
        held = held_permissions(staff)
        return {
            "every_side": sorted(held.every_side),
            "sides": [
                {"side": str(side_id), "permissions": sorted(codes)}
                for side_id, codes in sorted(held.on_side.items(), key=lambda side: str(side[0]))
                if codes
            ],
        }


class SettingRecord(serializers.ModelSerializer[Setting]):
    # A dated rule's row: which rule, for the whole shop (`side` empty) or one side, its value as the rule's kind writes
    # it ("1500.00", "07:35"), and the shop's day it starts on. Not its note: the owner's reason is for the office.
    class Meta:
        model = Setting
        fields = ["id", "key", "side", "value", "effective_from"]
        read_only_fields = fields


# A rule's scopes, as the choices of its `scope` below: by value alone, as Scope is a plain enum, not Django's choices.
# The schema names this very list (SettingScopeEnum, ENUM_NAME_OVERRIDES in config/settings/base.py), as it matches a
# name by each choice's value and label: Scope itself would give the labels "SHOP" and "SIDE", and match nothing.
SETTING_SCOPES = [scope.value for scope in Scope]
# A rule's kinds, by name, for the same reason: the schema names this very list (SettingKindEnum).
SETTING_KINDS = [kind.code for kind in KINDS]


class SettingKeyRecord(serializers.Serializer[Any]):
    # One rule in the list in core: its key, its kind's name, which says how to read its stored text, whether a side may
    # have a value of its own, and its default as its kind writes it (setting_keys, apps/sync/bootstrap.py).
    key = serializers.CharField()
    kind = serializers.ChoiceField(choices=SETTING_KINDS)
    scope = serializers.ChoiceField(choices=SETTING_SCOPES)
    default = serializers.CharField()


class BootstrapAnswer(serializers.Serializer[Any]):
    # The bootstrap's answer, as the API schema and the app's types describe it. The answer itself is built by snapshot
    # (apps/sync/bootstrap.py) from the registry; this names the same tables with the same fields, which
    # test_answer_shape_names_every_registry_table holds, so a table added to the registry is added here too.
    cursor = serializers.IntegerField(
        min_value=0, help_text="The shop's last change number this copy holds: the first pull asks for what came after."
    )
    side = SideRecord(many=True)
    payment_account = PaymentAccountRecord(many=True)
    staff = StaffRecord(many=True)
    setting = SettingRecord(many=True)
    setting_keys = SettingKeyRecord(many=True)
