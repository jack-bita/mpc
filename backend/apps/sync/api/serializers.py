"""apps/sync/api/serializers.py — the fields a shop's devices may see of each record they keep a copy of, the
bootstrap's answer (SYNC-2; 03 §6.1, §6.4), and the pull's question and answer (SYNC-3).

One serializer per table the registry sends (apps/sync/registry.py): a side, a payment account, a person at work, a
dated rule's row. Each names its fields one by one, never `__all__`, so a column a later card adds stays on the server
until someone decides it travels. What must never travel, buying prices, PIN hashes and passwords above all (03 §6.1,
the sync rules), is checked against these lists by test_bootstrap_secrets.py. Read-only: devices never write through
them; what a device makes travels as a document (SYNC-4). Then the bootstrap's answer, and the pull's question and
answer, as the API schema describes them. A pull's change carries the same records, and test_bootstrap_secrets.py checks
what it adds around them too, field by field and as sent. Last, the push's question and answer (SYNC-4): each document's
envelope, checked here, and each document's answer.
"""

from collections.abc import Mapping
from typing import Any

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers

from apps.control.models import FlagKind
from apps.core.api.ids import uuid7_only
from apps.core.languages import Language
from apps.core.models import ChangeOp
from apps.core.settings_registry import KINDS, Scope
from apps.people.models import Font, StaffMember
from apps.people.permissions import held_permissions
from apps.shops.models import PaymentAccount, Setting, Side
from apps.sync.models import PushedStatus
from apps.sync.push import ACCEPTED, DUPLICATE, INVALID, RETRY


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


# The pull's question and answer (SYNC-3), as the API schema describes them. The answer itself is built by page
# (apps/sync/pull.py) from the registry; these name the same tables with the same records, which
# test_answer_shape_names_every_registry_table (test_pull_route.py) holds.

# The biggest number the change log can hold (Change.seq, a big integer): a cursor past it names no change.
BIGGEST_CHANGE_NUMBER = 2**63 - 1


class ChangeNumber(serializers.IntegerField):
    # A change number sent in the address. DRF reads a blank value there (`?cursor=`) as a field left out, and so as its
    # default: a device that lost its cursor and sent it blank would read the whole log again at every sync, and nobody
    # would notice. Here a blank value is a value, checked as one, and refused as no whole number (invalid).

    def get_value(self, dictionary: Mapping[str, Any]) -> Any:
        # The field's name is set once it is bound to PullQuery, before any value is read; the types allow None.
        if self.field_name is not None and dictionary.get(self.field_name) == "":
            return ""
        return super().get_value(dictionary)


class PullQuery(serializers.Serializer[Any]):
    # What a device asks: the last change number it read. Left out, 0: nothing read yet, as numbers start at 1. One
    # that is no change number ("abc", -1, a blank) is refused under `cursor` (400 invalid), never read as another.
    cursor = ChangeNumber(
        min_value=0,
        max_value=BIGGEST_CHANGE_NUMBER,
        default=0,
        help_text="The last change number this device read: the bootstrap's cursor, then each page's. 0 for none.",
    )


class ChangeRecord(serializers.Serializer[Any]):
    # What every change on a page says, whatever its table: its number, its table's code, its record's id, and what to
    # do: `upsert`, save `data` as the record now is, new or changed; `archive`, take it off the lists. Then `data`
    # itself: the record, through the fields of the table each change below names, null for an archive.
    seq = serializers.IntegerField(min_value=1)
    entity = serializers.CharField()
    id = serializers.UUIDField()
    op = serializers.ChoiceField(choices=ChangeOp.choices)
    # The table's record, the registry's own (apps/sync/registry.py), named by each table's change below.
    record: type[serializers.ModelSerializer[Any]]

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        # `data`, the name 03 §6.4 gives it, is added here, once for all four tables, from each one's `record`. Not
        # written as a field in each class below: DRF would take it off the class as a field, but mypy reads the class
        # as written, and finds it standing where every serializer keeps its own `.data`, the answer it renders.
        fields = super().get_fields()
        fields["data"] = self.record(allow_null=True)
        return fields


class SideChange(ChangeRecord):
    record = SideRecord


class PaymentAccountChange(ChangeRecord):
    record = PaymentAccountRecord


class StaffChange(ChangeRecord):
    record = StaffRecord


class SettingChange(ChangeRecord):
    record = SettingRecord


# Each table's change, by its code, in the registry's order: the schema then says which record a change of each table
# carries, so the app's types know a "staff" change holds a person.
CHANGE_RECORDS: dict[str, type[ChangeRecord]] = {
    "side": SideChange,
    "payment_account": PaymentAccountChange,
    "staff": StaffChange,
    "setting": SettingChange,
}


class PullAnswer(serializers.Serializer[Any]):
    # One page of the pull: up to 1,000 changes after the cursor, in order, each told apart by its `entity`; the cursor
    # to ask from next, the cursor asked when nothing came; whether more wait after it; the server's time, for the
    # device's clock; and the oldest app version that may still sync, null while any may.
    changes = PolymorphicProxySerializer(
        component_name="Change",
        # A copy, built where mypy reads it as the wider dict the schema's class takes: a dict's values are fixed to
        # their type, so CHANGE_RECORDS itself, of ChangeRecord classes alone, doesn't pass as one.
        serializers={code: change for code, change in CHANGE_RECORDS.items()},
        resource_type_field_name="entity",
        many=True,
    )
    cursor = serializers.IntegerField(
        min_value=0,
        help_text="The last change number this page read, sent or passed over, or the cursor asked when none came:"
        " the next pull asks from it.",
    )
    has_more = serializers.BooleanField(
        help_text="More changes wait after this page: ask again at once, from its cursor. A page can hold fewer than"
        " 1,000 changes and still have more after it."
    )
    server_time = serializers.DateTimeField()
    min_app_version = serializers.CharField(allow_null=True)


class PushedEnvelope(serializers.Serializer[Any]):
    # One document as a laptop sends it (03 §6.3): the parts every type has, checked here, around its payload, which
    # its own type's shape checks (apps/sync/push.py). A broken envelope is a bug in the laptop's sync code, not a
    # document to set aside: the whole push is refused, under the field (`documents.0.device_seq`).
    id = serializers.UUIDField(validators=[uuid7_only], help_text="The document's id, made on the laptop (UUIDv7).")
    type = serializers.CharField(max_length=40)
    schema_version = serializers.IntegerField(min_value=1, max_value=2**31 - 1)
    device_seq = serializers.IntegerField(min_value=1, max_value=2**63 - 1, help_text="The laptop's number for it.")
    client_time = serializers.DateTimeField(help_text="The laptop's clock when it was made: kept, never trusted.")
    created_by = serializers.UUIDField(help_text="The staff member who made it at the counter.")
    payload = serializers.DictField(help_text="The document itself, in its type's shape.")


class PushBatch(serializers.Serializer[Any]):
    # Up to 100 documents a push (03 §6.3), so one push stays short on a shop's slow line. No device id: the key says
    # which laptop sends (AUTH-2). The laptop's app version and unsent count come with SYNC-5, which records them.
    # A list field of envelopes, not `many=True`: the same checks, each envelope's under its number
    # (`documents.0.device_seq`), and its limit reaches the API's description (maxItems), which a list serializer's
    # doesn't, nor the type checker's notes on the `many=True` form.
    documents = serializers.ListField(child=PushedEnvelope(), max_length=100)


class FlagRaised(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=FlagKind.choices)


# The four answers, by name, for the schema to name this very list (PushAnswerStatusEnum), as it does the settings'
# lists above: an automatic name, taken from the field, would change the day another field of that name joins.
PUSH_ANSWER_STATUSES = [ACCEPTED, DUPLICATE, INVALID, RETRY]


class PushedAnswer(serializers.Serializer[Any]):
    # One document's answer (apps/sync/push.py, Answer): accepted, duplicate, invalid or retry.
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=PUSH_ANSWER_STATUSES)
    first = serializers.ChoiceField(
        choices=PushedStatus.choices, allow_null=True, help_text="A duplicate's first answer."
    )
    posted_seq = serializers.IntegerField(
        min_value=1, allow_null=True, help_text="The last change number its save took."
    )
    flags = FlagRaised(many=True)
    code = serializers.CharField(allow_blank=True, help_text="An invalid one's reason, as the error shape names it.")

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        # `fields`, as the error shape names it, added here: written in the class, it would stand where every
        # serializer keeps its own `.fields` (the same reason as ChangeRecord's `data`).
        fields = super().get_fields()
        fields["fields"] = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
        return fields


class PushAnswer(serializers.Serializer[Any]):
    # One answer per document, in the laptop's order, up to the first retry.
    answers = PushedAnswer(many=True)
