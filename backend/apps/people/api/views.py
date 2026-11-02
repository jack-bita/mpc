"""apps/people/api/views.py — the people routes, of two kinds (03 §5.10).

The office routes, which a staff member calls from the office screens, built on ShopViewSet (apps/core/api/base.py),
under /api/v1/people/ (apps/people/api/urls.py). Today a shop's devices (AUTH-5):

    GET  /api/v1/people/devices/        the shop's devices, of the sides the person sees, in pages
    GET  /api/v1/people/devices/{id}/   one device
    POST /api/v1/people/devices/        a manager says yes to a waiting device, with the code it shows

And the routes a device calls with its key, built on DeviceView (apps/people/api/base.py), under /api/devices/v1/
(apps/people/api/device_urls.py):

    POST /api/devices/v1/pairing/   a new device asks to join a shop: a code to show, and its key in a cookie
    GET  /api/devices/v1/me/        a paired device learns its shop, its name, its code and its home side

Thin: each one calls its service (apps/people/services.py), or reads its rows, and answers with its serializer
(ADR-0015).
"""

from typing import Any, cast

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import SEES_THE_SIDE, CreateOnceMixin
from apps.core.permissions import Permission
from apps.people.api.authentication import DEVICE_KEY_COOKIE, set_key_cookie
from apps.people.api.base import DeviceView
from apps.people.api.serializers import (
    DeviceConfirmSerializer,
    DeviceMeSerializer,
    DeviceSerializer,
    PairingStartSerializer,
)
from apps.people.models import Device, StaffMember
from apps.people.services import confirm_pairing, start_pairing


class DeviceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, CreateOnceMixin[Device]):
    # The shop's devices, as the manager's device list shows them (UI-3), and the manager's yes to a waiting one.
    model = Device
    # A device keeps its side as its home side: the list shows the devices of the sides the person sees, and saying
    # yes to one is asked on the home side picked (03 §5.9).
    side_field = "home_side"
    # Whoever works on a side sees its devices, a seller included, but changes none of them (Jack, 2 Nov 2026): a name
    # and when it was last seen are no secret. Saying yes to one needs device.manage on its home side, which
    # confirm_pairing asks too (PPL-5).
    action_permissions = {
        "list": SEES_THE_SIDE,
        "retrieve": SEES_THE_SIDE,
        "create": Permission.DEVICE_MANAGE,
    }
    serializer_class = DeviceSerializer
    create_serializer_class = DeviceConfirmSerializer

    def create_row(self, data: dict[str, Any]) -> Device:
        # The phone's id goes to the service, so a confirm sent twice finds the device the first one made: the second
        # copy is refused there (pairing.code_used), and CreateOnceMixin then finds the device by this id and answers
        # with it, as for any repeat. cast: the login leaves the staff member acting in `request.auth`
        # (ShopViewSet.perform_authentication), and the service records who confirmed.
        return confirm_pairing(
            data["pairing_code"],
            name=data["name"],
            home_side=data["home_side"],
            by=cast(StaffMember, self.actor),
            device_id=data["id"],
        )


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
