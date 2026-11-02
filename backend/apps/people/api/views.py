"""apps/people/api/views.py — the routes a device calls with its key, built on DeviceView (apps/people/api/base.py).

    POST /api/devices/v1/pairing/   a new device asks to join a shop: a code to show, and its key in a cookie
    GET  /api/devices/v1/me/        a paired device learns its shop, its name, its code and its home side

Thin: each one calls its service (apps/people/services.py), or reads its device, and answers with its serializer
(ADR-0015).
"""

from typing import cast

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.people.api.authentication import DEVICE_KEY_COOKIE, set_key_cookie
from apps.people.api.base import DeviceView
from apps.people.api.serializers import DeviceMeSerializer, PairingStartSerializer
from apps.people.models import Device
from apps.people.services import start_pairing


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
