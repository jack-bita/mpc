"""apps/people/api/authentication.py — the device key login: a paired device's requests log in as that device, in its
own shop (AUTH-2; 03 §5.4, §5.9; ADR-0038, ADR-0018).

A paired device keeps its key in a cookie, `device_key`, which page scripts can't read (HttpOnly). Every request it
sends carries the cookie, and DeviceKeyAuthentication, a DRF login class, turns it into the device:

    cookie ──hash──▶ the door: which shop? ──▶ that shop open ──▶ the device, through the guard
                     (apps/people/login_doors.py)                   shop suspended? 401 shop.suspended
                                                                    blocked? 401 device.blocked
                                                                    a change? the CSRF token, or 403
                                                                    ──▶ request.auth = the device

The device is the visit's Actor (apps/core/tenancy.py): its `shop_id`, and a `staff_id` of None, since a device is a
shop's machine, not a person. The device routes open its shop for the whole visit (DeviceView, apps/people/api/base.py);
office routes don't use this login at all, and refuse a device alone (CORE-6).

This file owns the cookie (its name, how long it lasts, and the one function that sets it), the login class, the
CSRF check the device routes share, and the cookie's description for the API's schema.
"""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseBase
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.request import Request

from apps.core.tenancy import shop_context
from apps.people.device_keys import hash_device_key
from apps.people.login_doors import shop_of_device_key
from apps.people.models import Device, DeviceStatus
from apps.people.selectors import LoginRefused, check_shop_active
from apps.people.services import note_device_seen

# The cookie's name, a promise to every browser that holds one: it never changes. It holds "key" on purpose: Django's
# error pages and error reports hide the value of any cookie whose name holds KEY, TOKEN or SECRET
# (SafeExceptionReporterFilter), so a crash in a device's visit never prints its key.
DEVICE_KEY_COOKIE = "device_key"
# How long a browser keeps it: 400 days, the most Chrome allows, whatever a server asks for (RFC 6265bis). The device
# routes send it again as the device is seen (DeviceView), so a device in use never reaches the end.
DEVICE_KEY_MAX_AGE = timedelta(days=400)


# Django's error reports, which a server with DEBUG off logs and sends, list each function's local variables when
# something fails. (Its debug page, on a laptop with DEBUG on, shows everything, as DEBUG means it to.) Marked with no
# names, so every variable is hidden, shown as stars: here, and in every function this one calls, since Django hides a
# variable in each frame below a marked one too. Not by name, as start_pairing hides its `key`
# (apps/people/services.py): Django's own set_cookie holds the key under another name, `value`, and a crash inside it
# would print it.
@sensitive_variables()
def set_key_cookie(response: HttpResponseBase, key: str) -> None:
    """Put the device's key in its cookie, on the answer about to leave (03 §5.9):
    - HttpOnly: page scripts can't read it, so a bad script in the page can't steal it (ADR-0038);
    - Secure, where the session's is (production): it travels over HTTPS only;
    - SameSite Strict: the browser never sends it with a request another website starts. The app and the API share
      one address, so the app itself never needs that;
    - only for /api/: never sent with the app's pages and pictures."""
    response.set_cookie(
        DEVICE_KEY_COOKIE,
        key,
        max_age=DEVICE_KEY_MAX_AGE,
        path="/api/",
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Strict",
    )


def enforce_csrf(request: Request) -> None:
    """Refuse a change (POST and the like) that doesn't carry the CSRF token, with DRF's own check: the one its session
    login runs, so a refusal reads the same on every route (403 permission_denied, "CSRF Failed: ..."). A browser sends
    the device's cookie with every request to our address, even one another website makes it send; only our own pages
    can read the `csrftoken` cookie and send its value back in the X-CSRFToken header (ADR-0038)."""
    SessionAuthentication().enforce_csrf(request)


class DeviceKeyAuthentication(BaseAuthentication):
    # DRF makes a new one of these for every visit (APIView.get_authenticators), so what it notes about this visit
    # stays with this visit: DeviceView reads `seen` from it as the answer leaves (apps/people/api/base.py).

    # True when this visit moved the device's last_seen_at: the answer then sends the key's cookie again.
    seen = False

    # Every device request passes here holding its key, so a crash anywhere in the login, or below it, must not print
    # the key or its hash in an error report: every variable hidden, as in set_key_cookie above. A crash here still
    # shows its lines, only not its values.
    @sensitive_variables()
    def authenticate(self, request: Request) -> tuple[AnonymousUser, Device] | None:
        key = request.COOKIES.get(DEVICE_KEY_COOKIE)
        if not key:
            # No cookie: no login, as for a new device that hasn't asked yet. DRF then tries the next login class, if
            # the route has one, and otherwise leaves the visit with nobody (request.auth None).
            return None
        key_hash = hash_device_key(key)
        shop_id = shop_of_device_key(key_hash)
        if shop_id is None:
            # A key no device holds: made up, still waiting for a manager's yes, or from a database that was reset.
            # No login, as with no cookie, rather than a refusal: a device whose code expired must still be able to
            # ask again with its old cookie (POST /api/devices/v1/pairing/).
            return None
        # The device itself, read through the guard inside its shop, which the door named. Opened for this read only:
        # the route opens it again for the whole visit, together with who acts (DeviceView).
        with shop_context(shop_id):
            # Its shop comes with it, in the same query, for the check below.
            device = Device.objects.select_related("shop").filter(key_hash=key_hash).first()
            if device is None:
                # Gone between the door and this read, which nothing in the app does: no login, as for no device.
                return None
            # Seen, blocked or not: a stolen phone that keeps calling shows when (02 v1.12). At most every few
            # minutes, so most visits write nothing (note_device_seen, apps/people/services.py).
            self.seen = note_device_seen(device, at=timezone.now())
        # A suspended shop stops every way in (check_shop_active), asked before the device's own status: it is the shop
        # that stopped it. The key itself still holds, and works again once the shop does (ADR-0018). 401, as for a
        # blocked device: the key opens nothing now.
        try:
            check_shop_active(device.shop)
        except LoginRefused as refused:
            raise exceptions.AuthenticationFailed(str(refused), code=refused.code) from refused
        if device.status != DeviceStatus.ACTIVE:
            # Only an active device works (02 §5). Asked as "not active", never as "blocked", so a status a later card
            # adds, such as a retired device, is refused until that card says otherwise: the login fails closed. Today
            # blocked is the only other status (the database allows no third): stopped on its very next request
            # (ADR-0018), with a code of its own, so the app locks and says why. 401: the key itself opens nothing now.
            # English for the logs; the app translates the code (ADR-0032).
            raise exceptions.AuthenticationFailed("This device is blocked.", code="device.blocked")
        # A change needs the CSRF token, as a session's does: the cookie alone would let another website act as the
        # device. A read passes this check by itself.
        enforce_csrf(request)
        # No person: AnonymousUser, as Django calls nobody. Who acts is the device, in request.auth.
        return AnonymousUser(), device

    def authenticate_header(self, request: Request) -> str:
        # DRF answers a refused login with 401 only when the route's first login class names how to log in, here
        # in the WWW-Authenticate header; without it DRF answers 403 (CORE-6's watch-out). No browser acts on this
        # name: the app reads the answer's code, not the header.
        return 'DeviceKey realm="api"'


# drf-spectacular's extension base files each subclass in a registry, in an __init_subclass__ with no type hints,
# which mypy's strict mode refuses to call silently: the library's own untyped code, not ours.
class DeviceKeyScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    # How the API's schema describes this login (ADR-0025): a key in a cookie. drf-spectacular finds this description
    # by its target class as it describes each route, and warns of a login it can't describe, which CORE-6's schema
    # test refuses. Here, beside the class, so it is loaded whenever the class is.
    target_class = DeviceKeyAuthentication
    name = "deviceKey"

    def get_security_definition(self, auto_schema: AutoSchema) -> dict[str, Any]:
        return {"type": "apiKey", "in": "cookie", "name": DEVICE_KEY_COOKIE}
