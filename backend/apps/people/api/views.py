"""apps/people/api/views.py — the people routes, of two kinds (03 §5.10).

The office routes, which a staff member calls from the office screens, built on ShopViewSet (apps/core/api/base.py),
under /api/v1/people/ (apps/people/api/urls.py). Today a shop's devices (AUTH-5):

    GET   /api/v1/people/devices/                the shop's devices, of the sides the person sees, in pages
    GET   /api/v1/people/devices/{id}/           one device
    POST  /api/v1/people/devices/                a manager says yes to a waiting device, with the code it shows
    PATCH /api/v1/people/devices/{id}/           a manager renames it
    POST  /api/v1/people/devices/{id}/block/     a manager stops it at once, with a reason
    POST  /api/v1/people/devices/{id}/unblock/   a manager lets it work again, with a reason

And the routes a device calls with its key, built on DeviceView (apps/people/api/base.py), under /api/devices/v1/
(apps/people/api/device_urls.py):

    POST /api/devices/v1/pairing/   a new device asks to join a shop: a code to show, and its key in a cookie
    GET  /api/devices/v1/me/        a paired device learns its shop, its name, its code and its home side

Thin: each one calls its service (apps/people/services.py), or reads its rows, and answers with its serializer
(ADR-0015).
"""

from collections.abc import Callable
from typing import Any, cast

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import SEES_THE_SIDE, CreateOnceMixin, EditMixin
from apps.core.permissions import Permission
from apps.people.api.authentication import DEVICE_KEY_COOKIE, set_key_cookie
from apps.people.api.base import DeviceView
from apps.people.api.serializers import (
    DeviceConfirmSerializer,
    DeviceEditSerializer,
    DeviceMeSerializer,
    DeviceReasonSerializer,
    DeviceSerializer,
    PairingStartSerializer,
)
from apps.people.models import Device, StaffMember
from apps.people.services import block as block_device
from apps.people.services import confirm_pairing, rename_device, start_pairing
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


class PairingView(DeviceView):
    # 03 §5.9, step 1: a new device, with no working key yet, asks to join. So no device is needed, and no shop is open
    # unless its cookie already opens a device, which is then refused.
    device_optional = True

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
# (ADR-0017). On dispatch, not on get(): a visit with no device is refused before get() runs.
@method_decorator(ensure_csrf_cookie, name="dispatch")
class DeviceMeView(DeviceView):
    # 03 §5.9, step 3: the device learns its shop and its device code for receipt numbers, and shows the shop's name.
    # Waiting for a manager's yes, or with no key, it gets 401 not_authenticated; blocked, 401 device.blocked.

    @extend_schema(responses=DeviceMeSerializer)
    def get(self, request: Request) -> Response:
        # cast: DeviceView has refused any visit with no device; mypy can't see that.
        return Response(DeviceMeSerializer(cast(Device, request.auth)).data)
