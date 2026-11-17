"""apps/sync/api/views.py — the sync routes a device calls with its key, under /api/sync/v1/ (03 §5.10, §6).

The bootstrap (SYNC-2), which hands a new or reset device a copy of its whole shop; the pull (SYNC-3), which tells it
what changed since; the push (SYNC-4), which takes what a laptop saved offline; and a photo's file (CTRL-3), which a
laptop sends after the record that named it. Each builds on DeviceView
(apps/people/api/base.py): the device's key logs it in, a blocked one is refused (401 device.blocked), and its shop is
open for the whole visit, so every read goes through the guard and sees that shop alone. The tenancy sweep finds these
routes by themselves and calls each as a device of each shop. Thin: what is read, and in which order, lives in
apps/sync/bootstrap.py and apps/sync/pull.py, and what is saved, in apps/sync/push.py and apps/control/services.py
(ADR-0043).
"""

import uuid
from typing import cast

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.gzip import gzip_page
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.control.models import LARGEST_FILE, Attachment, AttachmentType
from apps.control.services import receive_attachment_file
from apps.people.api.base import DeviceView
from apps.people.models import Device
from apps.people.services import Outage
from apps.sync import pull
from apps.sync.api.serializers import BootstrapAnswer, PullAnswer, PullQuery, PushAnswer, PushBatch
from apps.sync.bootstrap import snapshot
from apps.sync.push import Sent, push


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
        return Response(snapshot(device))


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


class PushView(DeviceView):
    # A laptop of the shop sends what it saved offline; its key has opened the shop for the visit (DeviceView), and its
    # CSRF token is checked by the key's login.

    @extend_schema(request=PushBatch, responses=PushAnswer)
    def post(self, request: Request) -> Response:
        device = cast(Device, request.auth)
        sent = PushBatch(data=request.data)
        # A broken envelope, or more than 100: 400 invalid, under the field, through the one error handler.
        sent.is_valid(raise_exception=True)
        documents = [Sent(**document) for document in sent.validated_data["documents"]]
        # The server's clock as the push arrived, one time for the whole batch and the laptop's report.
        answers = push(
            device,
            documents,
            received_at=timezone.now(),
            sent_at=sent.validated_data["sent_at"],
            unsent_count=sent.validated_data["unsent_count"],
            app_version=sent.validated_data["app_version"],
            outages=[Outage(**outage) for outage in sent.validated_data["outages"]],
        )
        return Response(PushAnswer({"answers": answers}).data)


class AttachmentFileView(DeviceView):
    # A laptop of the shop sends a photo's file, after the record that named it reached the server (CTRL-3, 03 §5.13):
    # the request's body is the file itself, as the laptop shrank it, with no form around it. Its key has opened the
    # shop for the visit (DeviceView), and its CSRF token is checked by the key's login, as the push's is. Safe to send
    # again: the same file twice, or a file already removed, answers 204 alike, so the laptop drops its copy.
    # `model`: the table the address's id is in, so the tenancy sweep asks about each of shop A's photos as shop B's
    # laptop, and expects the answer an id no shop has gets (DeviceView.model).
    model = Attachment

    @extend_schema(
        request={AttachmentType.JPEG.value: OpenApiTypes.BINARY, AttachmentType.WEBP.value: OpenApiTypes.BINARY},
        responses={204: None},
    )
    def put(self, request: Request, pk: uuid.UUID) -> Response:
        # The file's length first, from the request's head, before a byte of the file is read: a 50 MB upload is
        # refused unread, and the server's memory never holds it.
        length = _length_of(request)
        if length is None:
            # No length, or one that is no number: Django would read the body as empty, and the photo would be refused
            # as no image, which the laptop takes as a bad photo and sets aside for good. A request sent in pieces with
            # no length (chunked, as a proxy on the way may send it) says nothing about the photo, so the laptop is told
            # to send it again instead (CTRL-6), and nothing is read.
            raise LengthRequired()
        if length > LARGEST_FILE:
            raise ValidationError("A file is kept up to 1 MB.", code="attachment.too_big")
        try:
            # request.body, never request.data: the body is the file's own bytes, which no parser of DRF's should read.
            receive_attachment_file(pk, content=request.body)
        except Attachment.DoesNotExist:
            # An id this shop doesn't hold, another shop's included, answers as one no shop has: nothing tells shop B's
            # laptop that shop A's photo exists. The laptop also gets this when it sends a file before its record:
            # it tries again after its next push (CTRL-6).
            raise NotFound("No photo with this id here.", code="attachment.not_found") from None
        return Response(status=204)


def _length_of(request: Request) -> int | None:
    # The body's length as the request's head gives it (Content-Length); None when it gives none, or one that is no
    # whole number of bytes.
    try:
        length = int(request.META.get("CONTENT_LENGTH") or "")
    except ValueError:
        return None
    return length if length >= 0 else None


class LengthRequired(exceptions.APIException):
    # 411 Length Required: HTTP's own answer for a request that must say its length. The one error shape gives it this
    # code (apps/core/api/errors.py), which the laptop reads as "send it again", not as a refused photo (CTRL-6).
    status_code = 411
    default_detail = "Send the photo with its length (Content-Length)."
    default_code = "attachment.length_required"
