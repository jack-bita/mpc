"""apps/people/api/views.py — the people routes, of two kinds (03 §5.10).

The office routes, which a staff member calls from the office screens, built on ShopViewSet (apps/core/api/base.py),
under /api/v1/people/ (apps/people/api/urls.py). Today a shop's devices (AUTH-5):

    GET   /api/v1/people/devices/                the shop's devices, of the sides the person sees, in pages
    GET   /api/v1/people/devices/{id}/           one device
    POST  /api/v1/people/devices/                a manager says yes to a waiting device, with the code it shows
    PATCH /api/v1/people/devices/{id}/           a manager renames it
    POST  /api/v1/people/devices/{id}/block/     a manager stops it at once, with a reason
    POST  /api/v1/people/devices/{id}/unblock/   a manager lets it work again, with a reason

And a staff member's temporary password (AUTH-6):

    POST  /api/v1/people/staff/{id}/temporary-password/   someone with staff.manage sets one, face to face, and says why

And the routes a device calls with its key, built on DeviceView (apps/people/api/base.py), under /api/devices/v1/
(apps/people/api/device_urls.py) and, for PIN login, /api/auth/ (apps/people/api/auth_urls.py):

    POST /api/devices/v1/pairing/   a new device asks to join a shop: a code to show, and its key in a cookie
    GET  /api/devices/v1/me/        a paired device learns its shop, its name, its code and its home side
    POST /api/auth/pin-login/       someone at a paired device types their PIN, and gets a session (AUTH-4)

And what a session itself may ask, built on neither (AUTH-4):

    GET  /api/auth/me/              who is logged in here, where, and what they may do; an office route, in all but name
    POST /api/auth/logout/          this browser's session ends, at once, whatever has happened to them since

Thin: each one calls its service (apps/people/services.py), or reads its rows, and answers with its serializer
(ADR-0015).
"""

from collections.abc import Callable
from typing import Any, cast

from django.contrib.auth import logout
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_variables
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, mixins
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from apps.core.api.base import SEES_THE_SIDE, CreateOnceMixin, EditMixin, ShopViewSet
from apps.core.permissions import Permission
from apps.people.api.authentication import set_key_cookie
from apps.people.api.base import DeviceView
from apps.people.api.pin_session import PIN_SESSION, start_pin_session
from apps.people.api.serializers import (
    DeviceConfirmSerializer,
    DeviceEditSerializer,
    DeviceMeSerializer,
    DeviceReasonSerializer,
    DeviceSerializer,
    PairingStartSerializer,
    PinLoginSerializer,
    TemporaryPasswordSerializer,
    WhoIsHereSerializer,
)
from apps.people.api.staff_session import MeSessionAuthentication
from apps.people.api.throttles import PairingConfirmThrottle, PairingStartThrottle, PinLoginThrottle
from apps.people.device_keys import DEVICE_KEY_COOKIE
from apps.people.models import Device, StaffMember
from apps.people.selectors import LoginRefused, idle_lock_minutes, who_is_here
from apps.people.services import block as block_device
from apps.people.services import confirm_pairing, pin_login, rename_device, set_temporary_password, start_pairing
from apps.people.services import unblock as unblock_device


class DeviceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CreateOnceMixin[Device], EditMixin[Device]):
    # The shop's devices, as the manager's device list shows them (UI-3): the manager's yes to a waiting one, a rename,
    # and a block or an unblock.
    model = Device
    # A device keeps its side as its home side: the list shows the devices of the sides the person sees, and each
    # change is asked on the device's home side, or on the one picked for a new device (03 §5.9).
    side_field = "home_side"
    # Whoever works on a side sees its devices, a seller included, but changes none of them (Jack, 2 Nov 2026): a name
    # and when it was last seen are no secret. Every change needs device.manage on the home side, which each service
    # asks again (PPL-5).
    action_permissions = {
        "list": SEES_THE_SIDE,
        "retrieve": SEES_THE_SIDE,
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


class StaffViewSet(ShopViewSet[StaffMember]):
    # A shop's people. One action so far: a first or forgotten password, set face to face (ADR-0038). PPL-4 adds the
    # list, the adding and the rest, and its screen calls this.
    model = StaffMember
    # A person's password opens them on every side, whichever side they work on: the row belongs to the whole shop, so
    # the key is asked on the whole shop, where a key for Dawa alone opens nothing (PPL-5).
    side_field = None
    # The owner's own key, which he may hand to a manager (Jack, 4 Nov 2026). The service asks it again, with the rest
    # of who may (_check_may_set_password, apps/people/services.py).
    action_permissions = {"temporary_password": Permission.STAFF_MANAGE}
    serializer_class = TemporaryPasswordSerializer

    # `sent` holds the password while the service runs, and so do the serializer's frames while they read it: every
    # variable here, and in everything this calls, shows as stars in Django's error reports, as in the service itself.
    @extend_schema(request=TemporaryPasswordSerializer, responses={204: None})
    @action(detail=True, methods=["post"], url_path="temporary-password")
    @sensitive_variables()
    def temporary_password(self, request: Request, pk: str | None = None) -> Response:
        # The person, found in the visit's shop and checked for the action's key (get_object; initial() already ran it
        # once, before the action began): another shop's person is "not found", before anything sent is read.
        staff = self.get_object()
        sent = self.get_serializer(data=request.data)
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
        badge = request._request.session.get(PIN_SESSION) or {}
        here = who_is_here(cast(StaffMember, self.actor), device_id=badge.get("device"))
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
