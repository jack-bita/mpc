"""apps/sync/api/views.py — the sync routes a device calls with its key, under /api/sync/v1/ (03 §5.10, §6).

The bootstrap (SYNC-2), which hands a new or reset device a copy of its whole shop, and the pull (SYNC-3), which tells
it what changed since. The push (SYNC-4) joins them. Each builds on DeviceView (apps/people/api/base.py): the device's
key logs it in, a blocked one is refused (401 device.blocked), and its shop is open for the whole visit, so every read
goes through the guard and sees that shop alone. The tenancy sweep finds these routes by themselves and calls each as
a device of each shop. Thin: what is read, and in which order, lives in apps/sync/bootstrap.py and apps/sync/pull.py
(ADR-0041).
"""

from typing import cast

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.gzip import gzip_page
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.people.api.base import DeviceView
from apps.people.models import Device
from apps.sync import pull
from apps.sync.api.serializers import BootstrapAnswer, PullAnswer, PullQuery
from apps.sync.bootstrap import snapshot


# Compressed for a client that asks (Accept-Encoding: gzip), as every browser does: once products and customers
# travel, the copy is still about 1 MB compressed (03 §6.4), over a shop's slow line. Here, not on every route: an
# answer that mixes a secret with words a stranger can choose can leak through its compressed size (BREACH), and this
# one holds neither a secret nor anything from the request. Django adds random bytes to each compressed answer as a
# further guard.
# And never kept by a cache, the browser's or a proxy's on the way (Cache-Control: no-store, private): it holds the
# shop's whole staff list and everyone's keys, and a reset device must get today's lists, never yesterday's.
@method_decorator(gzip_page, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class BootstrapView(DeviceView):
    # A device of the shop asks; its key has opened the shop for the visit (DeviceView).

    @extend_schema(responses=BootstrapAnswer)
    def get(self, request: Request) -> Response:
        # cast: DeviceView has refused any visit with no device; mypy can't see that.
        device = cast(Device, request.auth)
        return Response(snapshot(device.shop))


# Compressed and never cached, as the bootstrap is, for the same reasons: a page of 1,000 changes over a slow line, and
# the shop's people and their keys on it. Gzip is safe here too: a page holds no secret, and the one thing the request
# chooses that it can show is the cursor, a number checked as one.
@method_decorator(gzip_page, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class PullView(DeviceView):
    # A device of the shop asks what changed after the last change it read; its key has opened the shop for the visit.

    @extend_schema(parameters=[PullQuery], responses=PullAnswer)
    def get(self, request: Request) -> Response:
        device = cast(Device, request.auth)
        asked = PullQuery(data=request.query_params)
        # A cursor that is no change number: 400 invalid, under `cursor`, through the one error handler.
        asked.is_valid(raise_exception=True)
        return Response(pull.page(device.shop, asked.validated_data["cursor"]))
