"""apps/people/api/throttles.py — pairing is slowed down for whoever asks too often (AUTH-5; 03 §5.10).

Two limits, 10 an hour each *(default)* (DEFAULT_THROTTLE_RATES, config/settings/base.py):

- the start of a pairing (POST /api/devices/v1/pairing/), per caller's network: its one public IPv4 address, or its
  IPv6 network (a /64), where each phone has an address of its own. Every device of a shop shares it, so the limit
  counts the whole shop, and a few devices an hour is plenty;
- a manager's confirm (POST /api/v1/people/devices/), per person: someone typing codes over and over, by mistake or
  to guess one, waits.

A request over its limit is refused with 429 throttled, and `wait`, the seconds until the next try
(apps/core/api/errors.py). Every request counts, a refused one too: a guessed code is a refused confirm. The counts live
in the database cache, in PostgreSQL, shared by every server worker, each limit in a table of its own (CACHES,
config/settings/base.py; ADR-0023). A
device's own calls, `me` and later sync, name no limit, so they are never slowed down.
"""

import ipaddress

from django.conf import settings
from django.core.cache import caches
from django.utils.crypto import salted_hmac
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


def caller_network(address: str) -> str:
    """The network a caller's address belongs to, as the start's limit counts it: an IPv4 address alone, which a shop
    shares behind its router; an IPv6 address by its /64, the network a phone takes addresses in as it likes, so a new
    address in it is the same caller; and an IPv4 address written in IPv6's form (::ffff:203.0.113.10) as that IPv4."""
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        # Not an address at all, which only a broken proxy would send: counted as it is, so it still has a limit.
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


class OwnTableThrottle(SimpleRateThrottle):
    # A limit that counts in a cache table of its own (CACHES, config/settings/base.py): a full table loses a third of
    # its rows by their keys' ABC order, so a flood of another limit's callers, in a shared one, would clear this
    # limit's counts.
    cache_name: str

    def __init__(self) -> None:
        # Looked up as the throttle is made, once per visit, never as the module loads: a test may change the caches.
        self.cache = caches[self.cache_name]
        super().__init__()


class PairingStartThrottle(OwnTableThrottle):
    # The start of a pairing, counted per caller's network: a device that asks has no key that works yet, and nobody
    # is logged in.
    scope = "pairing.start"
    cache_name = "pairing_start"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        if request.method != "POST":
            # Only a start: DRF counts before it finds the action, so a GET, which this route refuses (405), would
            # count too, and a page's hidden images could use up the shop's starts. None leaves it uncounted.
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

    def get_ident(self, request: Request) -> str:
        # Kept as a fingerprint of the caller's network, never the address: the counts sit in a table, and in its
        # backups, long after their hour, and an address can name a person. An HMAC with the server's secret key, so
        # the same network always gives the same fingerprint, and nobody without the key can tell which it was.
        return salted_hmac(self.scope, caller_network(self._address(request)), algorithm="sha256").hexdigest()

    def _address(self, request: Request) -> str:
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


class PairingConfirmThrottle(OwnTableThrottle):
    # A manager's confirm, counted per person: one person who works at two shops (02 D12) has one count, not one at
    # each.
    scope = "pairing.confirm"
    cache_name = "pairing_confirm"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        if getattr(view, "action", None) != "create":
            # Only the confirm: the device list, a rename, a block or an unblock are a manager's daily work, never a
            # guess. None leaves the request uncounted.
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
