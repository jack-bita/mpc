"""apps/people/api/throttles.py — pairing is slowed down for whoever asks too often (AUTH-5; 03 §5.10).

Two limits, 10 an hour each *(default)* (DEFAULT_THROTTLE_RATES, config/settings/base.py):

- the start of a pairing (POST /api/devices/v1/pairing/), per address: every device of a shop shares the shop's one
  public address, so the limit counts the whole shop, and a few devices an hour is plenty;
- a manager's confirm (POST /api/v1/people/devices/), per person: someone typing codes over and over, by mistake or
  to guess one, waits.

A request over its limit is refused with 429 throttled, and `wait`, the seconds until the next try
(apps/core/api/errors.py). Every request counts, a refused one too: a guessed code is a refused confirm. The counts live
in the database cache, in PostgreSQL, shared by every server worker (CACHES, config/settings/base.py; ADR-0023). A
device's own calls, `me` and later sync, name no limit, so they are never slowed down.
"""

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class PairingStartThrottle(SimpleRateThrottle):
    # The start of a pairing, counted per caller's address: a device that asks has no key that works yet, and nobody
    # is logged in.
    scope = "pairing.start"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

    def get_ident(self, request: Request) -> str:
        # The caller's address as the proxy in front saw it, never as the caller says it.
        header = settings.CLIENT_IP_HEADER
        if not header:
            # On a laptop and on the real server: the entry Caddy added to X-Forwarded-For, NUM_PROXIES from its end
            # (DRF's own reading); the entries before it are the caller's own words.
            return super().get_ident(request)
        # On the demo: the header Cloudflare writes over any the caller sent (render.yaml). Django gives a request's
        # headers as HTTP_ and their name in capitals, with _ for -: CF-Connecting-IP is HTTP_CF_CONNECTING_IP. A
        # request without it, which Cloudflare would never pass on, counts with the address it came from: the proxy
        # in front, shared by every such request, so it is slowed down sooner, never let through.
        meta_name = "HTTP_" + header.upper().replace("-", "_")
        return str(request.META.get(meta_name) or request.META.get("REMOTE_ADDR", ""))


class PairingConfirmThrottle(SimpleRateThrottle):
    # A manager's confirm, counted per person: one person who works at two shops (02 D12) has one count, not one at
    # each.
    scope = "pairing.confirm"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        if getattr(view, "action", None) != "create":
            # Only the confirm: the device list, a rename, a block or an unblock are a manager's daily work, never a
            # guess. None leaves the request uncounted.
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
