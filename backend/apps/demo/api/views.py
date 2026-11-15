"""apps/demo/api/views.py — the one-tap demo's two routes (OPS-3, BP15), mounted under /api/devices/v1/ by
config/urls.py beside the device routes of apps/people/api/device_urls.py:

    GET  /api/devices/v1/demo/open/   may Jaribu demo show here? true only where the demo shop is the only shop
    POST /api/devices/v1/demo/        one tap: this browser becomes a device of the demo shop, its key in a cookie,
                                      and gets the demo sellers' PINs to show under their tiles

Thin: each calls apps/demo/services.py and answers with its serializer (ADR-0015). Both are shut on the real server,
which never has the demo's sign, and on any database with a shop that isn't a demo (demo_shop_if_open).
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.demo.api.serializers import DemoDeviceSerializer, DemoOpenSerializer
from apps.demo.services import demo_shop_if_open, register_demo_device
from apps.people.api.authentication import set_key_cookie
from apps.people.api.base import DeviceView
from apps.people.api.throttles import PairingStartThrottle
from apps.people.device_keys import DEVICE_KEY_COOKIE


class DemoOpenView(APIView):
    # Asked by the welcome screen of a browser that is no device yet, on every server: so no login, and nothing of any
    # shop's in the answer, only true or false. No authentication at all, not just AllowAny, as for the health check
    # (apps/core/api/views.py): DRF's session check would read a session from the database for nothing. It reads the
    # shops' kinds alone, never a shop's own table, so the tenancy sweep leaves it to its own test (NOT_SHOP_ROUTES,
    # backend/tests/sweep_lists.py).
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=DemoOpenSerializer)
    def get(self, request: Request) -> Response:
        return Response(DemoOpenSerializer({"open": demo_shop_if_open() is not None}).data)


class DemoDeviceView(DeviceView):
    # A browser with no working key yet taps Jaribu demo, as a new device starts a pairing (PairingView,
    # apps/people/api/views.py): so no device is needed, and no shop is open unless its cookie already opens a device,
    # which is then refused. Every change on a device route is CSRF-checked (DeviceView), so another website can't make
    # a visitor's browser join.
    device_optional = True
    # The start of a pairing's limit, per caller's network, counted together with it: each tap makes a waiting request
    # and a device, so a flood of taps is a flood of starts (apps/people/api/throttles.py).
    throttle_classes = [PairingStartThrottle]

    @extend_schema(request=None, responses={201: DemoDeviceSerializer})
    def post(self, request: Request) -> Response:
        # The key the cookie holds now, if any, goes to the service, as PairingView sends it: read straight from the
        # cookie, never kept in a variable here. `made` holds the new key until set_key_cookie takes it, and never
        # prints it (DemoDevice's repr=False), so an error report that lists this function's variables shows no key.
        made = register_demo_device(replacing=request.COOKIES.get(DEVICE_KEY_COOKIE))
        response = Response(DemoDeviceSerializer(made).data, status=201)
        # The key goes in the cookie only, never in the body.
        set_key_cookie(response, made.key)
        return response
