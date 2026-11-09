"""apps/sync/api/views.py — the sync routes a device calls with its key, under /api/sync/v1/ (03 §5.10, §6).

For now one: the bootstrap (SYNC-2), which hands a new or reset device a copy of its whole shop. The pull (SYNC-3) and
the push (SYNC-4) join it. Each builds on DeviceView (apps/people/api/base.py): the device's key logs it in, a blocked
one is refused (401 device.blocked), and its shop is open for the whole visit, so every read goes through the guard and
sees that shop alone. The tenancy sweep finds these routes by themselves and calls each as a device of each shop.
Thin: what is read, and in which order, lives in apps/sync/bootstrap.py (ADR-0015).
"""

from typing import cast

from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.people.api.base import DeviceView
from apps.people.models import Device
from apps.sync.api.serializers import BootstrapAnswer
from apps.sync.bootstrap import snapshot


# Compressed for a client that asks (Accept-Encoding: gzip), as every browser does: the copy grows to about 1 MB once
# products and customers travel (03 §6.4), over a shop's slow line. Here, not on every route: an answer that mixes a
# secret with words a stranger can choose can leak through its compressed size (BREACH), and this one holds neither a
# secret nor anything from the request. Django adds random bytes to each compressed answer as a further guard.
@method_decorator(gzip_page, name="dispatch")
class BootstrapView(DeviceView):
    # A device of the shop asks; its key has opened the shop for the visit (DeviceView).

    @extend_schema(responses=BootstrapAnswer)
    def get(self, request: Request) -> Response:
        # cast: DeviceView has refused any visit with no device; mypy can't see that.
        device = cast(Device, request.auth)
        return Response(snapshot(device.shop))
