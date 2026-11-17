"""apps/control/api/views.py — the control routes an office screen calls, under /api/v1/control/ (03 §5.10, CTRL-3).

Today one: a photo's file, handed out to someone allowed to see it (03 §5.13). The owner opens Asha's clock-in photo
beside her 07:55 on the attendance page (ATT-6); the PIN screen's faces come with PPL-9. Served only here, through
Django, after the shop's guard and the kind's key: never from an address of its own, which anyone holding the link
could open (apps/core/storage.py refuses to make one). Thin, as every route is (ADR-0015): the rule of who may open
which kind lives with the kinds (ATTACHMENT_KINDS, apps/control/models.py).
"""

from typing import Any, ClassVar

from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request

from apps.control.models import ATTACHMENT_KINDS, Attachment, AttachmentKind, AttachmentType
from apps.core.api.base import SEES_THE_SIDE, ShopViewSet, Sight
from apps.core.permissions import Permission


class AttachmentViewSet(ShopViewSet[Attachment]):
    # The shop's attachments, one at a time, by id. No list and no detail of its own yet: the screen that shows a
    # record's photos (ATT-6, PPL-9) asks its own route for the record, which will carry the photo's id.
    model = Attachment
    # A photo belongs to the whole shop, not to a side: a worker's attendance is the shop's (ATTACHMENT_KINDS).
    side_field = None
    # Opening a file only shows it, so the route asks only that the person sees the shop's rows, as any read of a
    # row of the whole shop does. The kind's own key is asked inside the action, on the whole shop: the key depends on
    # each photo's kind, and a show action may not name a key of its own here (PPL-5's rule, apps/core/api/base.py).
    action_permissions: ClassVar[dict[str, Permission | Sight]] = {"file": SEES_THE_SIDE}

    @extend_schema(
        responses={
            (200, AttachmentType.JPEG.value): OpenApiTypes.BINARY,
            (200, AttachmentType.WEBP.value): OpenApiTypes.BINARY,
        },
    )
    @action(detail=True, methods=["get"])
    def file(self, request: Request, *args: Any, **kwargs: Any) -> FileResponse:
        # The row through the guard and the person's sides (get_object): another shop's photo, or an id no shop has, is
        # "not found", alike.
        attachment = self.get_object()
        # The kind's key, on the whole shop: a clock-in photo is for whoever fixes attendance; a worker's face, for
        # anyone working here. Asked before the file's state, so someone without the key can't even learn whether a
        # photo came.
        needed = ATTACHMENT_KINDS[AttachmentKind(attachment.kind)].opened_with
        if needed is not None and needed not in self.held.on(None):
            # English for the logs; the screens translate the code (ADR-0032). The message travels in the answer too,
            # so it names nothing of the photo, not even its kind: someone without the key learns only that they may
            # not open it.
            raise PermissionDenied("This person may not open this photo.")
        if attachment.file_removed_at is not None:
            raise NotFound("This photo was removed.", code="attachment.file_removed")
        if not attachment.file:
            # Its record came; the laptop hasn't sent the file yet (CTRL-6).
            raise NotFound("This photo hasn't arrived yet.", code="attachment.file_waiting")
        # Opened now, inside the visit, while its shop is open (the storage checks the name's shop); sent after. The
        # type is the label's, which the upload checked against the file's first bytes, never guessed from its name.
        try:
            opened = attachment.file.open("rb")
        except FileNotFoundError:
            # The row said "kept" as it was read, but the file was gone by the time it was opened: a removal committed
            # in between, and its delete ran after its commit (remove_attachment_file). Said as the removal it is, not a
            # crash.
            raise NotFound("This photo was removed.", code="attachment.file_removed") from None
        answer = FileResponse(opened, content_type=attachment.content_type)
        # Never kept by the browser or a cache on the way: a photo of a person, behind a key that can be taken away
        # tomorrow (03 §10). nosniff: the browser takes the type as sent, and never runs the file as something else.
        answer["Cache-Control"] = "private, no-store"
        answer["X-Content-Type-Options"] = "nosniff"
        return answer
