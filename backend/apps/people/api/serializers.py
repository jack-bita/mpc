"""apps/people/api/serializers.py — how the people tables look in the API (03 §5.10).

Thin: they describe fields and their shape; every write goes through apps/people/services.py (ADR-0015). Today a
shop's devices on the office routes (AUTH-5): a device as the device list shows it, and as the health page shows it,
with its last push's report and its offline periods (SYNC-14); what a manager sends to say yes to a waiting one, to
rename one, and to block or unblock one; a shop's workers, each with what they were given, as the workers' page
shows them (PPL-4); what the owner sends to set a temporary password (AUTH-6); what a device sends for a PIN login,
and what `me` answers (AUTH-4); what a person sends to change their own language and font (UI-9); and the answers of
the routes a device calls with its key (apps/people/api/views.py), the PIN screen's list of people among them (UI-4).
A key, a key's hash or a PIN's hash is never among the fields: they never leave the server (03 §5.9).
"""

from datetime import timedelta
from typing import Any, cast

from django.db import models
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.api.ids import uuid7_only
from apps.people.models import OWN_SETTINGS, Device, DeviceOutage, PairingRequest, StaffMember, User
from apps.people.selectors import Given, given_to
from apps.shops.api.fields import SideField
from apps.shops.models import Shop, Side, SideBand


class DeviceSerializer(serializers.ModelSerializer[Device]):
    # A device as the shop's device list shows it (UI-3): its name, its code for receipt numbers (D7), its home side,
    # whether it works, and when its key last reached the server, so a stolen phone that keeps calling shows when. No
    # `shop`: it is always the visit's own. The app keeps `version` and sends it back with a rename
    # (apps/core/editing.py). Never the key's hash.
    class Meta:
        model = Device
        fields = ["id", "name", "code", "home_side", "status", "last_seen_at", "created_at", "updated_at", "version"]
        read_only_fields = fields


class DeviceOutageSerializer(serializers.ModelSerializer[DeviceOutage]):
    # One offline period a laptop reported (SYNC-14, 02: DeviceOutage): when it lost the server and when it heard it
    # again, by its own clock, as kept. It may end before it starts, after the laptop's clock was put back: the page
    # shows it as the laptop said, and says so. With `end_unknown`, its end is only the last time the laptop's app saw
    # it, as the laptop went off: the page shows "– ?".
    class Meta:
        model = DeviceOutage
        fields = ["id", "started_at", "ended_at", "end_unknown"]
        read_only_fields = fields


class DeviceHealthSerializer(serializers.ModelSerializer[Device]):
    # A device as the health page shows it (*Hali ya vifaa*, SYNC-14, 03 §5.17): who it is, whether it works, what it
    # said about itself at its last push (when, how many records still wait on it, which app), how far its clock was
    # from the server's, and its offline periods of the last week. Every report field is empty until its first push,
    # so the page can say "not synced yet" rather than show a made-up 0. No key's hash, as on the device list.
    clock_error_seconds = serializers.SerializerMethodField()
    outages = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            "id",
            "name",
            "code",
            "home_side",
            "status",
            "last_synced_at",
            "unsent_count",
            "app_version",
            "clock_error_seconds",
            "outages",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_clock_error_seconds(self, device: Device) -> int | None:
        # The laptop's clock minus the server's, in whole seconds (a laptop 6 minutes slow is -360): a number the app
        # reads at once, where Django's own text for a duration ("-1 23:54:00") would need parsing. Rounded away from
        # zero, never toward it (SYNC-14's review): a clock 120.4 s fast already makes its clock-ins wait for review
        # (more than 2 minutes, CLOCK_SLACK), so the page must read it as past the slack, 121, never as 120, within it.
        # By whole-number division, never through a float. divmod rounds down, which is away from zero for a clock
        # behind; for one ahead, a part-second left over rounds up.
        if device.clock_error is None:
            return None
        seconds, left = divmod(device.clock_error, timedelta(seconds=1))
        if left and seconds >= 0:
            seconds += 1
        return seconds

    @extend_schema_field(DeviceOutageSerializer(many=True))
    def get_outages(self, device: Device) -> Any:
        # Read once for every device by the route (outages_this_week), handed in through the context: one query for
        # the page, not one per device.
        periods = self.context["outages"].get(device.pk, [])
        return DeviceOutageSerializer(periods, many=True).data


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


class GivenRoleSerializer(serializers.Serializer[Any]):
    # One role a worker was given, with its side (None: every side). `template` names a copied role, whose `name` is
    # empty: the page shows the template's name in its own words (sw.json, en.json; 02 §5).
    id = serializers.UUIDField(read_only=True)
    role = serializers.UUIDField(read_only=True)
    template = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    side = serializers.UUIDField(read_only=True, allow_null=True)


class GivenKeySerializer(serializers.Serializer[Any]):
    # One extra key a worker was given beyond their roles, with its side (None: every side).
    id = serializers.UUIDField(read_only=True)
    permission = serializers.CharField(read_only=True)
    side = serializers.UUIDField(read_only=True, allow_null=True)


class StaffListSerializer(serializers.ListSerializer[StaffMember]):
    # A page of workers: what each was given is read for the whole page at once, in two queries, before each worker is
    # written out (given_to), not twice per worker. Kept in the context the workers' serializers share, which DRF makes
    # new for each answer.
    # `data`: the page, a list, or the rows' query, as DRF hands either. Any: DRF's types know only one row here.
    def to_representation(self, data: Any) -> Any:
        rows = list(data.all() if isinstance(data, models.Manager | models.QuerySet) else data)
        # cast: DRF types the context as read-only, but it is the plain dict each answer starts with.
        cast(dict[str, Any], self.context)["given"] = given_to([row.pk for row in rows])
        return super().to_representation(rows)


class StaffSerializer(serializers.ModelSerializer[StaffMember]):
    # A worker as the workers' page shows them (PPL-4, PPL-6): their full name and phone, which are the person's (User),
    # their nickname, job title, first day, status and leaving day, and every role and extra key they were given. No
    # `shop`: it is always the visit's own. Never their PIN's hash, nor when it was set, nor their email or password
    # (03 §5.9). The phone, for whoever manages the workers (the route's staff.manage), as they type it and a temporary
    # password needs it (PPL-10); never to a laptop, whose copy of the people is StaffRecord's (apps/sync).
    # `version` is the job's, which a fix sends back (apps/core/editing.py): the model keeps it out of every form and
    # API field it could be written through (editable=False), so here it is only read.
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True, allow_null=True)
    # The superuser switched the person off in the admin: their job may still say "active", but they log in nowhere,
    # and no laptop shows them (staff_rows, SYNC-15). Said apart from `status`, which is the job's (PPL-4's review).
    switched_off = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    keys = serializers.SerializerMethodField()

    class Meta:
        model = StaffMember
        fields = [
            "id",
            "full_name",
            "phone",
            "display_name",
            "job_title",
            "started_on",
            "status",
            "left_on",
            "switched_off",
            "roles",
            "keys",
            "version",
        ]
        read_only_fields = fields
        list_serializer_class = StaffListSerializer

    def _given(self, staff: StaffMember) -> Given:
        # From the page's read, for a list; read here for one worker shown alone, once for both fields.
        given: dict[Any, Given] = cast(dict[str, Any], self.context).setdefault("given", {})
        if staff.pk not in given:
            given.update(given_to([staff.pk]))
        return given[staff.pk]

    def get_switched_off(self, staff: StaffMember) -> bool:
        return not staff.user.is_active

    @extend_schema_field(GivenRoleSerializer(many=True))
    def get_roles(self, staff: StaffMember) -> Any:
        return GivenRoleSerializer(self._given(staff).roles, many=True).data

    @extend_schema_field(GivenKeySerializer(many=True))
    def get_keys(self, staff: StaffMember) -> Any:
        return GivenKeySerializer(self._given(staff).keys, many=True).data


class StaffAddSerializer(serializers.Serializer[Any]):
    # What the workers' page sends to add a worker (PPL-4): the job's id, made on the phone (ADR-0007), the person's
    # full name, and the job's nickname, job title and first day. Spaces at either end are taken off, so spaces alone
    # are a blank name, refused beside its box. The lengths are the tables' own. add_worker checks the rest: a nickname
    # another current worker has (staff.display_name_taken).
    # Required, and a UUIDv7: without an id of its own, a send repeated would look like a second Juma. No unique check
    # of the id here: the route looks it up itself, first and again after any refusal (CreateOnceMixin).
    id = serializers.UUIDField(validators=[uuid7_only])
    full_name = serializers.CharField(max_length=User._meta.get_field("full_name").max_length)
    display_name = serializers.CharField(max_length=StaffMember._meta.get_field("display_name").max_length)
    # May be empty: many workers have no title beyond their role.
    job_title = serializers.CharField(
        max_length=StaffMember._meta.get_field("job_title").max_length, allow_blank=True, required=False, default=""
    )
    # Today, in the shop's time, if none is sent (add_staff).
    started_on = serializers.DateField(required=False, allow_null=True, default=None)


class StaffReasonSerializer(serializers.Serializer[Any]):
    # What a suspension or a bringing back sends: why, kept in its audit line with who and when (rule 7). A blank reason
    # is let through, so the service refuses it with its own code, staff.reason_required, which the screen translates;
    # one left out is the form's own `required`. 500 characters at most, as the audit line keeps (control.AuditEvent).
    reason = serializers.CharField(max_length=500, allow_blank=True)


# What a fix may send: the person's details and the job's (change_worker, PPL-10).
STAFF_DETAILS = ("full_name", "phone", "display_name", "job_title", "started_on")


class StaffEditSerializer(StaffReasonSerializer):
    # What the worker's page sends to fix a worker's details (PPL-10): the boxes it changed, the version of the worker
    # it read, and why (Jack, PPL-10: A). Every detail may be left out: one left out stays as it is. Spaces at either
    # end are taken off, so spaces alone are a blank name, refused beside its box, as on Ongeza; the lengths are the
    # tables' own. change_worker checks the rest: a wrong phone (phone.invalid), one another person has (unique), a
    # nickname another current worker has (staff.display_name_taken), a stale version (409 version_conflict).
    version = serializers.IntegerField(min_value=1)
    full_name = serializers.CharField(max_length=User._meta.get_field("full_name").max_length, required=False)
    # As it was typed, "0712 345 678": longer than the 16 characters stored, as the admin's box takes (PhoneField).
    # Empty takes the phone off.
    phone = serializers.CharField(max_length=32, allow_blank=True, required=False)
    display_name = serializers.CharField(
        max_length=StaffMember._meta.get_field("display_name").max_length, required=False
    )
    job_title = serializers.CharField(
        max_length=StaffMember._meta.get_field("job_title").max_length, allow_blank=True, required=False
    )
    started_on = serializers.DateField(required=False)


class StaffLeaveSerializer(StaffReasonSerializer):
    # What a leaving sends: why, and the worker's last day, which the page fills in as today for the owner to change. A
    # day ahead is the service's to refuse (staff.left_in_future), as leaving takes effect at once.
    left_on = serializers.DateField()


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


class PinLoginSerializer(serializers.Serializer[Any]):
    # What a shop's device sends when someone types their PIN (AUTH-4): who, and the PIN. Only ever read in: the route
    # answers with nothing, and nothing shows a PIN back.
    staff = serializers.UUIDField(write_only=True)
    # 16 characters at most, so a huge text can't reach the slow hash. Not checked as 4 digits here: anything else just
    # counts as a wrong try, with the same answer.
    pin = serializers.CharField(max_length=16, write_only=True)


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
    # The side it mostly serves, which the counter screens open on, with the band its top bar draws before anyone logs
    # in (SHOP-4). The device keeps it in its saved copy, so the bar draws it offline too.
    class Meta:
        model = Side
        fields = ["id", "code", "name", "band"]
        read_only_fields = fields


class MeShopSerializer(serializers.ModelSerializer[Shop]):
    # Its shop. Shown by name, so a code claimed by the wrong shop's manager is seen at once (03 §5.9). And what an
    # offline device needs to know of it (SYNC-2's review): its time zone, to tell which of its rules is in force today,
    # as a rule starts on the shop's own day (02 §1); its currency, for amounts on screen; and its language, for screens
    # nobody has logged in to yet. Here, not in the bootstrap: a shop's own row has no line in the change log, so a copy
    # sent once would go stale, and a device asks this route again every 5 minutes (03 §5.9).
    class Meta:
        model = Shop
        fields = ["id", "name", "code", "timezone", "currency", "default_language"]
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


class MeUserSerializer(serializers.ModelSerializer[User]):
    # The person, as the screens greet them, in their own language and font (03 §7.4, UI-9): the app applies both at
    # every login, so they follow the person to any device. No phone and no email: a screen on a shared laptop doesn't
    # need them, and the next person could read them there.
    class Meta:
        model = User
        fields = ["id", "full_name", "language", "font"]
        read_only_fields = fields


class OwnSettingsSerializer(serializers.ModelSerializer[User]):
    # What a person sends to `PATCH /api/auth/me/settings/` (UI-9): one of their two choices, or both, each refused
    # under its field if it isn't one the app knows (invalid_choice). Only these two fields: anything else sent, another
    # person's id included, is not read at all. Both optional, as the screen sends only the one just tapped: written
    # out, though the model's defaults already make them so, as that is a promise to the screen, not a side effect.
    class Meta:
        model = User
        fields = list(OWN_SETTINGS)
        extra_kwargs = {name: {"required": False} for name in OWN_SETTINGS}


class OwnSettingsAnswerSerializer(serializers.ModelSerializer[User]):
    # What the route answers: both choices, always, as now saved. Read-only, so the API's description, and the app's
    # types from it, say both are always there.
    class Meta:
        model = User
        fields = list(OWN_SETTINGS)
        read_only_fields = fields


class MeStaffSerializer(serializers.ModelSerializer[StaffMember]):
    # Their job at this shop. Never the PIN's hash.
    class Meta:
        model = StaffMember
        fields = ["id", "display_name", "job_title"]
        read_only_fields = fields


class MeSideKeysSerializer(serializers.Serializer[Any]):
    # One side, with what the person may do there. The side's own fields beside its keys, so a screen needs no second
    # call to name its tabs, nor to draw the band of the side the office's top bar names (SHOP-4).
    id = serializers.UUIDField(source="side.pk")
    code = serializers.CharField(source="side.code")
    name = serializers.CharField(source="side.name")
    band = serializers.ChoiceField(source="side.band", choices=SideBand.choices)
    permissions = serializers.ListField(child=serializers.CharField())


class MePermissionsSerializer(serializers.Serializer[Any]):
    # What the person may do (02 §5, X1): on the whole shop, and on each side they hold a key on. A side they hold none
    # on isn't named: they don't see it on any route either.
    whole_shop = serializers.ListField(child=serializers.CharField())
    sides = MeSideKeysSerializer(many=True)


class WhoIsHereSerializer(serializers.Serializer[Any]):
    # What `GET /api/auth/me/` answers (apps/people/selectors.py, who_is_here). `device` and `home_side` are empty for a
    # password on a person's own phone.
    user = MeUserSerializer()
    staff = MeStaffSerializer()
    shop = MeShopSerializer()
    device = MeDeviceSerializer(allow_null=True)
    home_side = MeSideSerializer(allow_null=True)
    must_change_password = serializers.BooleanField()
    # How long a shared device's screen may sit unused, in minutes: a PIN's badge's own, or for a password, the shop's
    # setting. Selling uses the device's key, not the session, so it never pushes the server's idle time forward: the
    # screen keeps a lock of its own, as long as the badge lasts (UI-4). A phone that is only the person's own never
    # shows that screen.
    idle_minutes = serializers.IntegerField()
    permissions = MePermissionsSerializer(source="*")

    def to_internal_value(self, data: Any) -> Any:
        # Only ever an answer: nothing is sent to this route.
        raise NotImplementedError
