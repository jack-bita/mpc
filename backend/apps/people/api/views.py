"""apps/people/api/views.py — the people routes, of two kinds (03 §5.10).

The office routes, which a staff member calls from the office screens, built on ShopViewSet (apps/core/api/base.py),
under /api/v1/people/ (apps/people/api/urls.py). Today a shop's devices (AUTH-5):

    GET   /api/v1/people/devices/                the shop's devices, of the sides the person sees, in pages
    GET   /api/v1/people/devices/{id}/           one device
    GET   /api/v1/people/devices/health/         the health page: each device's last sync, clock and outages (SYNC-14)
    POST  /api/v1/people/devices/                a manager says yes to a waiting device, with the code it shows
    PATCH /api/v1/people/devices/{id}/           a manager renames it
    POST  /api/v1/people/devices/{id}/block/     a manager stops it at once, with a reason
    POST  /api/v1/people/devices/{id}/unblock/   a manager lets it work again, with a reason

And a shop's workers, for whoever holds staff.manage on the whole shop (PPL-4), with their roles and extra keys (PPL-7),
a worker's temporary password (AUTH-6) and PIN (PPL-12), and their photo (PPL-9):

    GET   /api/v1/people/staff/                             every worker the shop has had, with what each was given
    GET   /api/v1/people/staff/{id}/                        one worker
    POST  /api/v1/people/staff/                             a new worker: the person and the job, in one step;
                                                            or, with hire_again, a new job for one who left (PPL-11)
    PATCH /api/v1/people/staff/{id}/                        fix their details, with the version read and a reason
    POST  /api/v1/people/staff/{id}/suspend/                stop a worker for a while, with a reason
    POST  /api/v1/people/staff/{id}/unsuspend/              bring them back, with a reason
    POST  /api/v1/people/staff/{id}/leave/                  record their last day, with a reason
    POST  /api/v1/people/staff/{id}/give-role/            give them one of the shop's roles, on a side or on all
    POST  /api/v1/people/staff/{id}/give-key/             give them one extra key, on a side or on all
    POST  /api/v1/people/staff/{id}/end-role/             take a role of theirs away, with a reason
    POST  /api/v1/people/staff/{id}/end-key/              take an extra key of theirs away, with a reason
    POST  /api/v1/people/staff/{id}/temporary-password/   someone with staff.manage sets one, face to face, and says why
    POST  /api/v1/people/staff/{id}/pin/                  the worker types their own PIN on the owner's phone (PPL-12)
    PUT   /api/v1/people/staff/{id}/photo/?photo=…&instead_of=…   set their photo, in the place of the one the page
                                                            showed: the body is the file, its id the phone's
    POST  /api/v1/people/staff/{id}/remove-photo/         take their photo off, with a reason (PPL-9)
    GET   /api/v1/people/roles/                           the shop's roles, to choose from when giving one

And the routes a device calls with its key, built on DeviceView (apps/people/api/base.py), under /api/devices/v1/
(apps/people/api/device_urls.py) and, for PIN login, /api/auth/ (apps/people/api/auth_urls.py):

    POST /api/devices/v1/pairing/   a new device asks to join a shop: a code to show, and its key in a cookie
    GET  /api/devices/v1/me/        a paired device learns its shop, its name, its code and its home side
    POST /api/auth/pin-login/       someone at a paired device types their PIN, and gets a session (AUTH-4)

And what a session itself may ask, built on neither (AUTH-4):

    GET  /api/auth/me/              who is logged in here, where, and what they may do; an office route, in all but name
    POST /api/auth/logout/          this browser's session ends, at once, whatever has happened to them since
    PATCH /api/auth/me/settings/    the person changes their own language and font, with no key (UI-9)

Thin: each one calls its service (apps/people/services.py), or reads its rows, and answers with its serializer
(ADR-0015).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast

from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Model, QuerySet
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_variables
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, mixins
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from apps.control.api.uploads import PHOTO_BODY, photo_sent
from apps.control.models import Attachment
from apps.core.api.base import SEES_THE_SIDE, CreateOnceMixin, EditMixin, ShopViewSet
from apps.core.api.ids import id_taken
from apps.core.permissions import Permission
from apps.people.api.authentication import set_key_cookie
from apps.people.api.base import DeviceView
from apps.people.api.pin_session import PIN_SESSION, pin_session_idle_minutes, start_pin_session
from apps.people.api.serializers import (
    STAFF_DETAILS,
    DeviceConfirmSerializer,
    DeviceEditSerializer,
    DeviceHealthSerializer,
    DeviceMeSerializer,
    DeviceReasonSerializer,
    DeviceSerializer,
    EndKeySerializer,
    EndRoleSerializer,
    GiveKeySerializer,
    GiveRoleSerializer,
    OwnSettingsAnswerSerializer,
    OwnSettingsSerializer,
    PairingStartSerializer,
    PhotoQuery,
    PinLoginSerializer,
    RemovePhotoSerializer,
    RoleSerializer,
    SetPinSerializer,
    StaffAddSerializer,
    StaffEditSerializer,
    StaffLeaveSerializer,
    StaffReasonSerializer,
    StaffSerializer,
    TemporaryPasswordSerializer,
    WhoIsHereSerializer,
)
from apps.people.api.staff_session import MeSessionAuthentication, StaffSessionAuthentication
from apps.people.api.throttles import PairingConfirmThrottle, PairingStartThrottle, PinLoginThrottle
from apps.people.device_keys import DEVICE_KEY_COOKIE
from apps.people.models import Device, PermissionGrant, Role, RoleAssignment, StaffMember, User
from apps.people.selectors import LoginRefused, idle_lock_minutes, outages_this_week, who_is_here
from apps.people.services import (
    add_worker,
    assign_role,
    change_own_settings,
    change_worker,
    confirm_pairing,
    end_permission,
    end_role,
    grant_permission,
    hire_again,
    mark_left,
    pin_login,
    remove_worker_photo,
    rename_device,
    set_pin,
    set_temporary_password,
    set_worker_photo,
    start_pairing,
    suspend,
    unsuspend,
)
from apps.people.services import block as block_device
from apps.people.services import unblock as unblock_device


class DeviceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CreateOnceMixin[Device], EditMixin[Device]):
    # The shop's devices, as the manager's device list shows them (UI-3): the manager's yes to a waiting one, a rename,
    # and a block or an unblock.
    model = Device
    # A device keeps its side as its home side: the list shows the devices of the sides the person sees, and each
    # change is asked on the device's home side, or on the one picked for a new device (03 §5.9).
    side_field = "home_side"
    # Whoever works on a side sees its devices, a seller included, but changes none of them (Jack, 2 Nov 2026): a name
    # and when it was last seen are no secret, nor is how it syncs (SYNC-14): the health page's button is for those
    # who look after the devices, as the device list's is, but what it shows is the device list's kind. Every change
    # needs device.manage on the home side, which each service asks again (PPL-5).
    action_permissions = {
        "list": SEES_THE_SIDE,
        "retrieve": SEES_THE_SIDE,
        "health": SEES_THE_SIDE,
        "create": Permission.DEVICE_MANAGE,
        "partial_update": Permission.DEVICE_MANAGE,
        "block": Permission.DEVICE_MANAGE,
        "unblock": Permission.DEVICE_MANAGE,
    }
    serializer_class = DeviceSerializer
    create_serializer_class = DeviceConfirmSerializer
    edit_serializer_class = DeviceEditSerializer

    def get_throttles(self) -> list[BaseThrottle]:
        # A manager's confirms are limited, per person, so codes can't be guessed (apps/people/api/throttles.py). DRF
        # asks this right after the login, before anything is checked, so a refused try counts too. Only a new try of a
        # code counts: the route's other actions are a manager's daily work; a send with no code can guess none; and a
        # confirm sent again, whose device the first send made, is answered with that device, as any repeat is
        # (CreateOnceMixin), so a double tap after a manager's tenth try still gets its laptop, never "wait".
        sent = self.request.data if isinstance(self.request.data, dict) else {}
        if self.action != "create" or not sent.get("pairing_code") or self._stored(sent.get("id")) is not None:
            return []
        return [PairingConfirmThrottle()]

    @property
    def staff(self) -> StaffMember:
        # The staff member acting, whom each service records as who confirmed, renamed or blocked the device. cast: the
        # login leaves them in `request.auth` (ShopViewSet.perform_authentication), which mypy reads as an Actor.
        return cast(StaffMember, self.actor)

    def create_row(self, data: dict[str, Any]) -> Device:
        # The phone's id goes to the service, so a confirm sent twice finds the device the first one made: the second
        # copy is refused there (pairing.code_used), and CreateOnceMixin then finds the device by this id and answers
        # with it, as for any repeat.
        return confirm_pairing(
            data["pairing_code"],
            name=data["name"],
            home_side=data["home_side"],
            by=self.staff,
            device_id=data["id"],
        )

    def edit_row(self, row: Device, data: dict[str, Any]) -> Device:
        return rename_device(row, version=data["version"], name=data["name"], by=self.staff)

    # The health page (*Hali ya vifaa*, SYNC-14, 03 §5.17): every device of the sides the person sees, by its number,
    # with its last push's report and its offline periods of the last week. One answer, not pages: a shop has a
    # handful of devices, and the page compares them side by side. The rows come from get_queryset(), so they keep to
    # the person's sides as the list does (PPL-5); the periods are read once for all of them.
    @extend_schema(responses=DeviceHealthSerializer(many=True))
    @action(detail=False, methods=["get"], pagination_class=None)
    def health(self, request: Request) -> Response:
        devices = list(self.get_queryset().order_by("code"))
        outages = outages_this_week(devices, now=timezone.now())
        return Response(DeviceHealthSerializer(devices, many=True, context={"outages": outages}).data)

    # Each action names what it takes and answers: the API's description would otherwise read every POST of this route
    # as a confirm (RouteSchema, apps/core/api/schema.py), and the app's types would be wrong (UI-2).
    @extend_schema(request=DeviceReasonSerializer, responses=DeviceSerializer)
    @action(detail=True, methods=["post"])
    def block(self, request: Request, pk: str | None = None) -> Response:
        # A stolen phone, stopped at once from the manager's own phone (03 §5.9, step 4): its key opens nothing from
        # its next request (AUTH-2).
        return self._change_status(request, block_device)

    @extend_schema(request=DeviceReasonSerializer, responses=DeviceSerializer)
    @action(detail=True, methods=["post"])
    def unblock(self, request: Request, pk: str | None = None) -> Response:
        # Back in the shop's hands: the same key works again, so the records it holds can still arrive (AUTH-1).
        return self._change_status(request, unblock_device)

    def _change_status(self, request: Request, change: Callable[..., Device]) -> Response:
        # The device, found among the person's own sides and checked for the action's key on its home side
        # (get_object; initial() already ran it once, before the action began): a device of a side the person
        # doesn't see is "not found", before the reason is even read. No version: a block is urgent, and is never
        # refused because someone renamed the device a moment ago (AUTH-1).
        device = self.get_object()
        sent = DeviceReasonSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        return Response(self.get_serializer(change(device, by=self.staff, reason=sent.validated_data["reason"])).data)


class StaffViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, CreateOnceMixin[StaffMember], EditMixin[StaffMember]
):
    # A shop's people, as the workers' page shows them (PPL-4, PPL-6): every worker the shop has had, those who left
    # included, each with every role and extra key they were given; a new worker, made once however often the page
    # sends him, or a new job for one who left, hired again (PPL-11); a worker's details fixed, from the copy the page
    # read, with a reason (PATCH, PPL-10); a worker suspended, brought back or marked left, each with a reason; and a
    # first or forgotten password, set face to face (ADR-0038); a role or an extra key given, or taken away with a
    # reason (PPL-7); a PIN, typed by the worker on the owner's phone (PPL-12); and their photo, set by its file or
    # taken off with a reason (PPL-9).
    model = StaffMember
    # A person's job belongs to the whole shop, whichever side they work on: a password opens them on every side, and a
    # suspension stops them on every side. So each key is asked on the whole shop, where a key for Dawa alone opens
    # nothing (PPL-5).
    side_field = None
    # staff.manage, the owner's own key, which he may hand to a manager (Jack, 4 Nov 2026). The workers too are for
    # whoever manages them, not for everyone who works there (PPL-4's card, default): the page shows each one's roles,
    # and their pay to whoever may see it (WAGE-2). Each service asks the key again, with the rest of who may
    # (apps/people/services.py).
    action_permissions = {
        "list": Permission.STAFF_MANAGE,
        "retrieve": Permission.STAFF_MANAGE,
        "create": Permission.STAFF_MANAGE,
        "partial_update": Permission.STAFF_MANAGE,
        "suspend": Permission.STAFF_MANAGE,
        "unsuspend": Permission.STAFF_MANAGE,
        "leave": Permission.STAFF_MANAGE,
        "give_role": Permission.STAFF_MANAGE,
        "give_key": Permission.STAFF_MANAGE,
        "end_role": Permission.STAFF_MANAGE,
        "end_key": Permission.STAFF_MANAGE,
        "temporary_password": Permission.STAFF_MANAGE,
        "pin": Permission.STAFF_MANAGE,
        "photo": Permission.STAFF_MANAGE,
        "remove_photo": Permission.STAFF_MANAGE,
    }
    serializer_class = StaffSerializer
    create_serializer_class = StaffAddSerializer
    edit_serializer_class = StaffEditSerializer

    def base_rows(self) -> QuerySet[StaffMember]:
        # Each worker's person read in the same query: the full name is the person's (User), not the job's.
        return super().base_rows().select_related("user")

    def create_row(self, data: dict[str, Any]) -> StaffMember:
        # The app's id goes to the service, so a send repeated finds the job the first one made (CreateOnceMixin): a new
        # worker, or a new job for one who left, hired again as the same person (PPL-11), found in this shop by the old
        # job's id (StaffField). Who may is each service's too.
        if data["hire_again"] is not None:
            return hire_again(
                data["hire_again"],
                display_name=data["display_name"],
                job_title=data["job_title"],
                started_on=data["started_on"],
                staff_id=data["id"],
                by=self._acting(),
            )
        return add_worker(
            shop=self._acting().shop,
            full_name=data["full_name"],
            display_name=data["display_name"],
            job_title=data["job_title"],
            started_on=data["started_on"],
            phone=data.get("phone"),
            staff_id=data["id"],
            by=self._acting(),
        )

    def edit_row(self, row: StaffMember, data: dict[str, Any]) -> StaffMember:
        # Only the boxes the page sent: one left out stays as it is (change_worker). Who may is the service's
        # (_locked_for_a_change), asked once both jobs are locked; the answer is the worker as now, with their new
        # version.
        details = {name: data[name] for name in STAFF_DETAILS if name in data}
        return change_worker(row, version=data["version"], reason=data["reason"], by=self._acting(), **details)

    # Each action names what it takes and answers, as the device routes do: the API's description would otherwise read
    # every POST of this route as an add (RouteSchema, apps/core/api/schema.py), and the app's types would be wrong.
    # Each answers with the worker as they are now, as the list shows them, so the page needs no second read.
    @extend_schema(request=StaffReasonSerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"])
    def suspend(self, request: Request, pk: str | None = None) -> Response:
        # A worker who stopped coming, stopped at once: their PIN opens nothing from their next request (AUTH-4), and
        # each laptop hears of it at its next sync (X2). Who may is the service's (_locked_for_a_change).
        sent = self._sent(request, StaffReasonSerializer)
        return self._answer(suspend(self._worker(), by=self._acting(), reason=sent["reason"]))

    @extend_schema(request=StaffReasonSerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"])
    def unsuspend(self, request: Request, pk: str | None = None) -> Response:
        sent = self._sent(request, StaffReasonSerializer)
        return self._answer(unsuspend(self._worker(), by=self._acting(), reason=sent["reason"]))

    @extend_schema(request=StaffLeaveSerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"])
    def leave(self, request: Request, pk: str | None = None) -> Response:
        # Final: a worker who comes back is hired again, as a new job (the add, with `hire_again`), and the old one
        # keeps its history (02 §5).
        sent = self._sent(request, StaffLeaveSerializer)
        return self._answer(
            mark_left(self._worker(), left_on=sent["left_on"], by=self._acting(), reason=sent["reason"])
        )

    # Ongeza kazi and Ondoa (PPL-7, for PPL-8's page). staff.manage on the whole shop opens the route, as for every
    # action here; each service asks who may again, with the rest of its rule: the giver rule for a give (02 §5), the
    # rule of Simamisha for an end (Jack: A). Each answers with the worker as they are now, with their roles and keys.
    @extend_schema(request=GiveRoleSerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"], url_path="give-role")
    def give_role(self, request: Request, pk: str | None = None) -> Response:
        worker = self._worker()
        sent = self._sent(request, GiveRoleSerializer)
        return self._given(
            RoleAssignment,
            lambda: assign_role(worker, sent["role"], side=sent["side"], by=self._acting(), given_id=sent["id"]),
            worker,
        )

    @extend_schema(request=GiveKeySerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"], url_path="give-key")
    def give_key(self, request: Request, pk: str | None = None) -> Response:
        worker = self._worker()
        sent = self._sent(request, GiveKeySerializer)
        return self._given(
            PermissionGrant,
            lambda: grant_permission(
                worker, sent["permission"], side=sent["side"], by=self._acting(), granted_id=sent["id"]
            ),
            worker,
        )

    @extend_schema(request=EndRoleSerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"], url_path="end-role")
    def end_role(self, request: Request, pk: str | None = None) -> Response:
        worker = self._worker()
        sent = self._sent(request, EndRoleSerializer)
        end_role(sent["role_given"], reason=sent["reason"], by=self._acting())
        return self._answer(worker)

    @extend_schema(request=EndKeySerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"], url_path="end-key")
    def end_key(self, request: Request, pk: str | None = None) -> Response:
        worker = self._worker()
        sent = self._sent(request, EndKeySerializer)
        end_permission(sent["key"], reason=sent["reason"], by=self._acting())
        return self._answer(worker)

    def _given(self, model: type[Model], give: Callable[[], object], worker: StaffMember) -> Response:
        # The give, with the app's id. Sent before, the service answers with what the first send made (_given_before).
        with self._refusing_a_taken_id(model):
            give()
        return self._answer(worker)

    @contextmanager
    def _refusing_a_taken_id(self, model: type[Model]) -> Iterator[None]:
        # A write that makes a row with the app's id: a role or a key given, a photo set. An id another shop's row holds
        # is found only by the insert, which PostgreSQL refuses on the table's primary key: answered as the id taken,
        # and nothing more about that row (03 §5.4), as CreateOnceMixin does. The service's block rolled back with the
        # refusal, so nothing was written.
        try:
            yield
        except IntegrityError as refusal:
            if id_taken(refusal, model):
                raise ValidationError({"id": ValidationError("This id is already in use.", code="id.taken")}) from None
            raise

    def _sent(self, request: Request, form: type[Serializer[Any]]) -> dict[str, Any]:
        # What was sent, checked. Read after initial() has found the worker, so another shop's is "not found" first.
        # With the view in its context: a role or a key to end is found among this worker's rows alone
        # (_OfThisWorker), and a side among the shop's (SideField).
        sent = form(data=request.data, context=self.get_serializer_context())
        sent.is_valid(raise_exception=True)
        return cast(dict[str, Any], sent.validated_data)

    def _worker(self) -> StaffMember:
        # The worker, found in the visit's shop and checked for the action's key (get_object; initial() already ran it
        # once, before the action began): another shop's worker is "not found", before anything sent is read.
        return self.get_object()

    def _acting(self) -> StaffMember:
        # cast: the login leaves the staff member acting in `request.auth`, which mypy reads as an Actor.
        return cast(StaffMember, self.actor)

    def _answer(self, staff: StaffMember) -> Response:
        return Response(self.get_serializer(staff).data)

    # `sent` holds the password while the service runs, and so do the serializer's frames while they read it: every
    # variable here, and in everything this calls, shows as stars in Django's error reports, as in the service itself.
    @extend_schema(request=TemporaryPasswordSerializer, responses={204: None})
    @action(detail=True, methods=["post"], url_path="temporary-password")
    @sensitive_variables()
    def temporary_password(self, request: Request, pk: str | None = None) -> Response:
        # The person, found in the visit's shop and checked for the action's key (get_object; initial() already ran it
        # once, before the action began): another shop's person is "not found", before anything sent is read.
        staff = self.get_object()
        sent = TemporaryPasswordSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        # cast: the login leaves the staff member acting in `request.auth`, which mypy reads as an Actor.
        set_temporary_password(
            staff,
            sent.validated_data["password"],
            by=cast(StaffMember, self.actor),
            reason=sent.validated_data["reason"],
        )
        # Nothing to answer with, on purpose: once sent, the password is never shown again (ADR-0038).
        return Response(status=204)

    # Weka PIN (PPL-12): the owner hands his phone over and the worker types their own PIN, so whoever types it is the
    # one who knows it. The route only passes who acts: who may (pin.own, pin.superuser_only, pin.more_keys), the demo,
    # the PIN's strength, and lifting the locks are set_pin's, under its own locks. Answers with the worker as they are
    # now, has_pin included, so the page needs no second read. `sent` holds the PIN while the service runs: every
    # variable here, and in everything this calls, shows as stars in Django's error reports, as on the password's route.
    @extend_schema(request=SetPinSerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"])
    @sensitive_variables()
    def pin(self, request: Request, pk: str | None = None) -> Response:
        worker = self._worker()
        sent = self._sent(request, SetPinSerializer)
        # `by` is the person logged in, never one the page names: the edit history keeps who set it, and when.
        return self._answer(set_pin(worker, sent["pin"], by=self._acting()))

    # Piga picha and Chagua picha (PPL-9): the body is the photo itself, as the phone shrank it, with no form around it,
    # as the laptop's upload is (apps/sync/api/views.py). PUT, as a photo sent twice is one photo: its id, made on the
    # phone, is in the address beside the worker's, but after the ?, as the tenancy sweep calls a route whose path names
    # one row, and no more; beside it, the photo it replaces, the one the page showed: a newer one is 409
    # version_conflict, and stays. Who may, the demo, and the old photo's end are set_worker_photo's. Answers with the
    # worker as they are now, photo included.
    @extend_schema(parameters=[PhotoQuery], request=PHOTO_BODY, responses=StaffSerializer)
    @action(detail=True, methods=["put"])
    def photo(self, request: Request, pk: str | None = None) -> Response:
        # The worker first, so another shop's is "not found" before anything sent is read; then the id; the body last,
        # its length before a byte of it (photo_sent).
        worker = self._worker()
        asked = PhotoQuery(data=request.query_params)
        asked.is_valid(raise_exception=True)
        content = photo_sent(request)
        with self._refusing_a_taken_id(Attachment):
            changed = set_worker_photo(
                worker,
                photo_id=asked.validated_data["photo"],
                instead_of=asked.validated_data["instead_of"],
                content=content,
                by=self._acting(),
            )
        return self._answer(changed)

    # Ondoa picha (PPL-9), of the photo the page shows: a newer one is 409 version_conflict, and stays.
    @extend_schema(request=RemovePhotoSerializer, responses=StaffSerializer)
    @action(detail=True, methods=["post"], url_path="remove-photo")
    def remove_photo(self, request: Request, pk: str | None = None) -> Response:
        worker = self._worker()
        sent = self._sent(request, RemovePhotoSerializer)
        return self._answer(
            remove_worker_photo(worker, photo_id=sent["photo"], reason=sent["reason"], by=self._acting())
        )


class RoleViewSet(mixins.ListModelMixin, ShopViewSet[Role]):
    # The shop's roles, for Ongeza kazi (PPL-7, PPL-8): each with its template, name and the codes it gives. Its own
    # route, not an action of the workers', as a role belongs to no worker. Only a list: a role is changed by no card
    # yet (parking lot item 26).
    model = Role
    # A role belongs to the whole shop, as a worker does: asked on the whole shop, as the workers' list is (PPL-4).
    side_field = None
    # For whoever gives roles: the codes each role gives are what the worker's page shows beside it, and they are the
    # owner's business, as the workers' roles are (the workers' list, PPL-4's card, default).
    action_permissions = {"list": Permission.STAFF_MANAGE}
    serializer_class = RoleSerializer


class PinLoginView(DeviceView):
    # 03 §5.9: a shop's device says who stands at it. Built on DeviceView, so a device logs in first, with its key, and
    # a blocked one never gets here. It takes no one's PIN but its own shop's people's. Limited per device, as each try
    # costs a full check of 19 MiB (apps/people/api/throttles.py).
    throttle_classes = [PinLoginThrottle]

    # `sent` holds the PIN while the service runs: every variable here, and in everything this calls, shows as stars in
    # Django's error reports.
    @extend_schema(request=PinLoginSerializer, responses={204: None})
    @sensitive_variables()
    def post(self, request: Request) -> Response:
        sent = PinLoginSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        # cast: DeviceView has refused any visit with no device; mypy can't see that.
        device = cast(Device, request.auth)
        try:
            staff = pin_login(device, sent.validated_data["staff"], sent.validated_data["pin"], at=timezone.now())
        except LoginRefused as refused:
            # 403: the device is fine, and it is the person who can't act today. English for the logs; the app
            # translates the code (ADR-0032).
            raise exceptions.PermissionDenied(str(refused), code=refused.code) from refused
        start_pin_session(request, staff, device, idle_minutes=idle_lock_minutes(staff.shop))
        # Nothing to answer with: the app asks `me` next, as after any login.
        return Response(status=204)


class LogoutView(APIView):
    # Ends the session this browser holds, at once: the row is deleted on the server, so a copy of its number opens
    # nothing (03 §5.9). DRF's own session login, not ours: it asks nothing about the person's job or the device, so a
    # suspended person, or someone on a blocked laptop, can still log out. It still checks the CSRF token, so another
    # website can't log someone out. With no session, nothing to do, and the same answer. It reads no shop's table
    # (NOT_SHOP_ROUTES, backend/tests/sweep_lists.py).
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    # `auth` names the session's cookie by the name the office routes describe it with (StaffSessionScheme). Left to
    # read DRF's class, the API's description would meet two different classes under one name, and warn. The library's
    # type hint says a list of texts, but it copies this value into the description as it stands, and OpenAPI wants
    # this shape (`manage.py spectacular --validate` agrees): the library's hint, not our value, is what is off.
    @extend_schema(request=None, responses={204: None}, auth=[{"cookieAuth": []}])  # type: ignore[list-item]
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=204)


class AtAShop(BasePermission):
    # Someone acting as a staff member at a shop: the job the login put in `request.auth` (StaffSessionAuthentication).
    # Nobody logged in, and the superuser, who is nobody's staff, are refused as an office route refuses them
    # (ShopViewSet), with not_authenticated, before anything is read. A permission of its own, not AllowAny with a check
    # after it: the API's description reads the permission to say who may call the route, and AllowAny would tell it
    # "no login at all" (UI-9's review).
    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.auth is None:
            raise exceptions.NotAuthenticated("This route needs a staff login at a shop.")
        return True


class OwnSettingsView(APIView):
    # A person changes their own language and font (UI-9, ADR-0039). Not an office route: an office route asks every
    # change for a key of its own (PPL-5), and everyone may change their own choices, so no key fits. Beside logout, as
    # it acts on the person, who belongs to no shop, not on a shop's rows; its answer holds the two choices and nothing
    # else. So the sweep doesn't call it (NOT_SHOP_ROUTES, backend/tests/sweep_lists.py), and
    # test_settings_answer_holds_nothing_of_a_shop proves the answer instead.
    #
    # The office routes' own login, though, not logout's: it reads the person afresh on every visit, so a suspended
    # person, someone on a temporary password, a copied badge or a blocked laptop is refused here as on every office
    # route (ADR-0038). It reads the person's job and its shop, and for a PIN's session the device that holds the key,
    # each inside the shop its login door names (apps/people/login_doors.py), only to refuse them. Its save writes the
    # person's staff line in every shop where they work, so their laptops show the new choice (change_own_settings,
    # SYNC-15); its answer holds none of it. It checks the CSRF token too, so another website can't change someone's
    # language.
    authentication_classes = [StaffSessionAuthentication]
    permission_classes = [AtAShop]
    # No answer to OPTIONS, which would describe the route's form to whoever asks: refused as the office routes refuse
    # it, as the API's own description is the schema (ShopViewSet.initial, apps/core/api/base.py).
    metadata_class = None

    @extend_schema(request=OwnSettingsSerializer, responses=OwnSettingsAnswerSerializer)
    def patch(self, request: Request) -> Response:
        sent = OwnSettingsSerializer(data=request.data, partial=True)
        sent.is_valid(raise_exception=True)
        # cast: the login has put the person here, as AtAShop checked; DRF's type stubs can't see that.
        person = change_own_settings(cast(User, request.user), **sent.validated_data)
        return Response(OwnSettingsAnswerSerializer(person).data)


class MeViewSet(ShopViewSet[StaffMember]):
    # Who is logged in here, where, and what they may do (03 §5.10). Built on the office routes' base, so the visit's
    # shop opens as for any office route, and the sweep calls it as shop B's person. It shows only the person's own job,
    # so it needs no key of its own.
    model = StaffMember
    side_field = None
    action_permissions = {"me": SEES_THE_SIDE}
    serializer_class = WhoIsHereSerializer
    # Open to someone on a temporary password, and to nobody else that the office routes refuse.
    authentication_classes = [MeSessionAuthentication]

    # `auth` as on LogoutView: the same cookie as the office routes, described by the same name.
    @extend_schema(responses=WhoIsHereSerializer, auth=[{"cookieAuth": []}])  # type: ignore[list-item]
    def me(self, request: Request) -> Response:
        session = request._request.session
        badge = session.get(PIN_SESSION) or {}
        here = who_is_here(
            cast(StaffMember, self.actor),
            device_id=badge.get("device"),
            idle_minutes=pin_session_idle_minutes(session),
        )
        return Response(self.get_serializer(here).data)


class PairingView(DeviceView):
    # 03 §5.9, step 1: a new device, with no working key yet, asks to join. So no device is needed, and no shop is open
    # unless its cookie already opens a device, which is then refused.
    device_optional = True
    # Limited per caller's network, so a flood of starts can't fill the waiting list, nor hunt for codes to confirm
    # (apps/people/api/throttles.py). The device's `me` names no limit: it is never slowed down.
    throttle_classes = [PairingStartThrottle]

    @extend_schema(request=None, responses={201: PairingStartSerializer})
    def post(self, request: Request) -> Response:
        # The key its cookie holds now, if any, goes to the service, which keeps the rules (ADR-0015). A key that
        # already opens a device is refused (pairing.already_paired): a tap on "Sajili kifaa hiki" on a working
        # device, or a request another website made it send, must not swap its key for a new one. A key still waiting
        # has its old code retired, so a manager can't confirm a code whose key no browser holds any more. A blocked
        # device never gets here: its login refuses it first (device.blocked), so it keeps its key for an unblock
        # (AUTH-1). Read straight from the cookie, never kept in a variable here: only the service hides its
        # variables from error reports.
        pairing = start_pairing(replacing=request.COOKIES.get(DEVICE_KEY_COOKIE))
        response = Response(PairingStartSerializer(pairing.request).data, status=201)
        # The key goes in the cookie only, never in the body. It stays inside `pairing`, which never prints it
        # (NewPairing's repr=False), until set_key_cookie, which hides it from error pages.
        set_key_cookie(response, pairing.key)
        return response


# The CSRF token's cookie goes with every answer of this route, a refusal included (ensure_csrf_cookie, around the
# whole visit): the app asks `me` first, paired or not, and its first change, the start of a pairing, needs the token
# (ADR-0038). On dispatch, not on get(): a visit with no device is refused before get() runs.
@method_decorator(ensure_csrf_cookie, name="dispatch")
class DeviceMeView(DeviceView):
    # 03 §5.9, step 3: the device learns its shop and its device code for receipt numbers, and shows the shop's name.
    # Waiting for a manager's yes, or with no key, it gets 401 not_authenticated; blocked, 401 device.blocked.

    @extend_schema(responses=DeviceMeSerializer)
    def get(self, request: Request) -> Response:
        # cast: DeviceView has refused any visit with no device; mypy can't see that.
        return Response(DeviceMeSerializer(cast(Device, request.auth)).data)
