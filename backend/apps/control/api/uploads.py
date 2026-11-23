"""apps/control/api/uploads.py — reading a photo that a request's whole body is (03 §5.13).

A laptop sends a clock-in's photo (CTRL-3, apps/sync/api/views.py) and the office sends a worker's (PPL-9,
apps/people/api/views.py) the same way: the body is the file's own bytes, with no form around it. Both routes read it
through photo_sent(), so one check guards both, and can't drift into two: the request's length is asked before a byte
of the file is read. Here, in `control`, as it owns the attachments (apps/control/models.py) and every app may import it
(ADR-0043). What the file is, and whether it is the right one, stays the services' (apps/control/services.py).
"""

from django.core.exceptions import ValidationError
from drf_spectacular.types import OpenApiTypes
from rest_framework import exceptions
from rest_framework.request import Request

from apps.control.models import LARGEST_FILE, AttachmentType

# What such a route takes, for the API's description: a photo's bytes, of one of the two types kept.
PHOTO_BODY = {AttachmentType.JPEG.value: OpenApiTypes.BINARY, AttachmentType.WEBP.value: OpenApiTypes.BINARY}


class LengthRequired(exceptions.APIException):
    # 411 Length Required: HTTP's own answer for a request that must say its length. The one error shape gives it this
    # code (apps/core/api/errors.py), which the laptop reads as "send it again", not as a refused photo (CTRL-6).
    status_code = 411
    default_detail = "Send the photo with its length (Content-Length)."
    default_code = "attachment.length_required"


def photo_sent(request: Request) -> bytes:
    """The photo a request's body is, read only once the request's head says it is small enough: a 50 MB upload is
    refused unread, and the server's memory never holds it."""
    length = _length_of(request)
    if length is None:
        # No length, or one that is no number: Django would read the body as empty, and the photo would be refused as
        # no image, which the laptop takes as a bad photo and sets aside for good. A request sent in pieces with no
        # length (chunked, as a proxy on the way may send it) says nothing about the photo, so whoever sent it is told
        # to send it again instead (CTRL-6), and nothing is read.
        raise LengthRequired()
    if length > LARGEST_FILE:
        raise ValidationError("A file is kept up to 1 MB.", code="attachment.too_big")
    # request.body, never request.data: the body is the file's own bytes, which no parser of DRF's should read.
    return request.body


def _length_of(request: Request) -> int | None:
    # The body's length as the request's head gives it (Content-Length); None when it gives none, or one that is no
    # whole number of bytes.
    try:
        length = int(request.META.get("CONTENT_LENGTH") or "")
    except ValueError:
        return None
    return length if length >= 0 else None
