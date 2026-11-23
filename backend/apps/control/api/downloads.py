"""apps/control/api/downloads.py — handing out a photo's file (03 §5.13).

Who may open a photo is each route's to ask: the office's asks the photo's kind's key (apps/control/api/views.py). What
is handed out, and how, is photo_answer()'s alone, for every route that does, so two of them can't drift apart: a photo
one of them never lets a cache keep is never kept through another. Here, in `control`, as it owns the attachments
(apps/control/models.py) and every app may import it (ADR-0043), beside the way a photo comes in (uploads.py).
"""

from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from rest_framework.exceptions import NotFound

from apps.control.models import Attachment, AttachmentType

# What such a route answers, for the API's description: a photo's bytes, of one of the two types kept.
PHOTO_ANSWER = {
    (200, AttachmentType.JPEG.value): OpenApiTypes.BINARY,
    (200, AttachmentType.WEBP.value): OpenApiTypes.BINARY,
}


def photo_answer(attachment: Attachment) -> FileResponse:
    """The photo's file, for someone the route has already let in, or "not found", said as it is: removed, or not here
    yet."""
    if attachment.file_removed_at is not None:
        raise NotFound("This photo was removed.", code="attachment.file_removed")
    if not attachment.file:
        # Its record came; the laptop hasn't sent the file yet (CTRL-6).
        raise NotFound("This photo hasn't arrived yet.", code="attachment.file_waiting")
    # Opened now, inside the visit, while its shop is open (the storage checks the name's shop); sent after. The type is
    # the label's, which the upload checked against the file's first bytes, never guessed from its name.
    try:
        opened = attachment.file.open("rb")
    except FileNotFoundError:
        # The row said "kept" as it was read, but the file was gone by the time it was opened: a removal committed in
        # between, and its delete ran after its commit (remove_attachment_file). Said as the removal it is, not a crash.
        raise NotFound("This photo was removed.", code="attachment.file_removed") from None
    answer = FileResponse(opened, content_type=attachment.content_type)
    # Never kept by the browser or a cache on the way: a photo of a person, behind a key that can be taken away tomorrow
    # (03 §10). nosniff: the browser takes the type as sent, and never runs the file as something else.
    answer["Cache-Control"] = "private, no-store"
    answer["X-Content-Type-Options"] = "nosniff"
    return answer
