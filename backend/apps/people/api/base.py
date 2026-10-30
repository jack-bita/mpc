"""apps/people/api/base.py — the base of every route a device calls with its key (AUTH-2; 03 §5.4, §5.10).

An office route builds on ShopViewSet (apps/core/api/base.py) and needs a person. A device route builds on DeviceView
and needs a paired device instead, logged in by its key (apps/people/api/authentication.py): today the start of a
pairing and `me`; later sync (SYNC-2 on) and PIN login (AUTH-4).

- The shop. Right after the login, before any check reads a table, the view opens the device's shop (shop_context)
  and tells PostgreSQL who acts (acting_as: the shop, and nobody, as a device is no person), and keeps both for the
  whole visit, the error answer included, as ShopViewSet does. Both close however the visit ends.
- No device. A route that needs one refuses the visit (401 not_authenticated). A route a new device calls before
  it has a working key says `device_optional = True`, and then runs with no shop open: it may read no shop's table.
- CSRF. A device's change is checked by its login; a change sent with no device, such as the start of a pairing, is
  checked here. So every change on every device route needs the token (ADR-0017).

CORE-7's sweep finds every route built on this by itself, and calls each as a device of each shop, and with no key at
all (backend/tests/test_tenancy_sweep.py).
"""

from contextlib import ExitStack
from typing import Any, ClassVar

from django.http import HttpRequest, HttpResponseBase
from rest_framework import exceptions
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.acting import acting_as
from apps.core.tenancy import shop_context
from apps.people.api.authentication import DeviceKeyAuthentication, enforce_csrf
from apps.people.models import Device


class DeviceView(APIView):
    # The device key is the only login a device route takes: a staff session alone opens none of them.
    authentication_classes = [DeviceKeyAuthentication]
    # Who may: a device, checked as its shop opens (perform_authentication), not by DRF's permission classes, which
    # ask about a person (request.user), and a device is none.
    permission_classes = [AllowAny]
    # True on a route a new device calls before a manager has said yes: it runs without a device, and so without a
    # shop. False on every other route, which refuses a visit with no device.
    device_optional: ClassVar[bool] = False
    # The visit's stack of things to close as it ends: the device's shop, and who acts as PostgreSQL knows it. Set in
    # dispatch(), once per visit; DRF makes a new view object for every visit, so two visits never share it.
    _visit: ExitStack

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        # DRF's whole visit runs inside this `with`, as in ShopViewSet: the login, the checks, the action and the error
        # answer. Leaving it closes the shop and who acts, however the visit ends.
        with ExitStack() as self._visit:
            return super().dispatch(request, *args, **kwargs)

    def perform_authentication(self, request: Request) -> None:
        # DRF calls this first in every visit, before its permission and throttle checks, which may read tables too.
        super().perform_authentication(request)  # runs the login: request.auth, or a refusal such as device.blocked
        device = request.auth
        if isinstance(device, Device):
            self._visit.enter_context(shop_context(device.shop_id))
            # Opened after the shop, so it closes first. An edit a device's visit makes to an office table is then
            # recorded as made in its shop by nobody (apps/core/acting.py), and an edit of another shop's row refused.
            self._visit.enter_context(acting_as(device))
        elif not self.device_optional:
            # No key, or one that opens no device. English for the logs; the app translates the code (ADR-0032).
            raise exceptions.NotAuthenticated("This route needs a paired device's key.")

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if request.method not in SAFE_METHODS and not isinstance(request.auth, Device):
            # A change with no device, such as the start of a pairing: no login checked its CSRF token, so it is
            # checked here. Without it, another website could make a paired laptop ask again (03 §5.9).
            enforce_csrf(request)
