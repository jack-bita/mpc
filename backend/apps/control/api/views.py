"""apps/control/api/views.py — the control routes an office screen calls, under /api/v1/control/ (03 §5.10).

The flags, as *Tofauti* shows them (CTRL-4): the list, one flag whole, and the three actions on one, for whoever may
close them.

And a photo's file, handed out to someone allowed to see it (03 §5.13, CTRL-3). The owner opens Asha's clock-in photo
beside her 07:55 on the attendance page (ATT-12), and her face on her own page (PPL-9). Served only through Django,
here after the shop's guard and the kind's key, and to a laptop, for its PIN screen, by a route of its own (PPL-14,
apps/sync/api/views.py): never from an address of its own, which anyone holding the link could open
(apps/core/storage.py refuses to make one).

Thin, as every route is (ADR-0015): the flags are read by the selectors and moved by the services, and the rule of who
may open which kind of photo lives with the kinds (ATTACHMENT_KINDS, apps/control/models.py).
"""

from collections.abc import Callable
from typing import Any, ClassVar, cast

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from apps.control.api.downloads import PHOTO_ANSWER, photo_answer
from apps.control.api.pagination import FlagPage
from apps.control.api.serializers import FlagLineSerializer, FlagNoteCreateSerializer, FlagSerializer, FlagsQuery
from apps.control.models import ATTACHMENT_KINDS, Attachment, AttachmentKind, Flag, FlagNote
from apps.control.selectors import FlagState, flag_detail, flag_lines, flags_asked, in_state
from apps.control.services import dismiss_flag, explain_flag, resolve_flag
from apps.core.api.base import SEES_THE_SIDE, ShopViewSet, Sight
from apps.core.api.ids import id_taken
from apps.core.permissions import Permission


class FlagViewSet(ShopViewSet[Flag]):
    # GET flags/?state=waiting&kind=…&side=…: the list of *Tofauti*; GET flags/{id}/: one flag's page; and its three
    # actions, POST flags/{id}/explain/, …/resolve/ and …/dismiss/, each with a note (CTRL-4).
    model = Flag
    # A flag keeps its side in `side`: empty for a flag of the whole shop, as attendance's are (02 §12).
    side_field = "side"
    # A flag shows only to whoever may close it (02 §13), so even reading it is behind `flag.review`: the base keeps
    # every read to the sides where the person holds it, and to the whole shop's flags only for the key on every side.
    action_permissions = {
        "list": Permission.FLAG_REVIEW,
        "retrieve": Permission.FLAG_REVIEW,
        "explain": Permission.FLAG_REVIEW,
        "resolve": Permission.FLAG_REVIEW,
        "dismiss": Permission.FLAG_REVIEW,
    }
    serializer_class = FlagLineSerializer
    pagination_class = FlagPage

    def base_rows(self) -> QuerySet[Flag]:
        # Each line names its side: read in the same query, not one per line.
        return super().base_rows().select_related("side")

    @extend_schema(parameters=[FlagsQuery], responses=FlagLineSerializer(many=True))
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        query = FlagsQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        asked = query.validated_data
        flags = flags_asked(
            self.get_queryset(), kind=asked.get("kind"), side_id=asked.get("side"), whole_shop=asked["whole_shop"]
        )
        # cast: the page class named above; DRF types its paginator as any page's, and a page that may be no page.
        pages = cast(FlagPage, self.paginator)
        pages.waiting = in_state(flags, FlagState.WAITING).count()
        page = cast("list[Flag]", self.paginate_queryset(in_state(flags, asked["state"])))
        return self.get_paginated_response(FlagLineSerializer(flag_lines(page), many=True).data)

    @extend_schema(responses=FlagSerializer)
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # One the person may not close, another shop's, or an id no shop has: "not found", alike (get_object).
        return Response(FlagSerializer(flag_detail(self.get_object(), viewer=self.actor)).data)

    @extend_schema(request=FlagNoteCreateSerializer, responses=FlagSerializer)
    @action(detail=True, methods=["post"])
    def explain(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # *Eleza*: why it happened. It still waits, and more may be said.
        return self._step(request, explain_flag)

    @extend_schema(request=FlagNoteCreateSerializer, responses=FlagSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # *Imetatuliwa*: a real problem, dealt with. Closed for good.
        return self._step(request, resolve_flag)

    @extend_schema(request=FlagNoteCreateSerializer, responses=FlagSerializer)
    @action(detail=True, methods=["post"])
    def dismiss(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # *Si tatizo*: no problem after all. Closed for good.
        return self._step(request, dismiss_flag)

    def _step(self, request: Request, step: Callable[..., Flag]) -> Response:
        # The flag first, through the key's sides (get_object): one the person may not close is "not found", before
        # anything sent is read, so the tenancy sweep's empty request reaches the guard (ATT-6's review). Who may close
        # one it names, and a closed one, the services refuse. The answer is the flag whole, as its page shows it.
        flag = self.get_object()
        sent = FlagNoteCreateSerializer(data=request.data)
        sent.is_valid(raise_exception=True)
        try:
            # The note's id makes the send safe to repeat: the same one again is handed the flag as it is (ADR-0007).
            moved = step(flag, text=sent.validated_data["text"], by=self.actor, note_id=sent.validated_data["id"])
        except IntegrityError as refusal:
            # An id another shop's note holds is found only by the insert (03 §5.4), and the service's transaction went
            # back with it: answered as the id taken, with nothing of whose.
            if id_taken(refusal, FlagNote):
                raise ValidationError({"id": ValidationError("This id is already in use.", code="id.taken")}) from None
            raise
        return Response(FlagSerializer(flag_detail(moved, viewer=self.actor)).data)


class AttachmentViewSet(ShopViewSet[Attachment]):
    # The shop's attachments, one at a time, by id. No list and no detail of its own yet: the screen that shows a
    # record's photos (ATT-12, PPL-9) asks its own route for the record, which carries the photo's id.
    model = Attachment
    # A photo belongs to the whole shop, not to a side: a worker's attendance is the shop's (ATTACHMENT_KINDS).
    side_field = None
    # Opening a file only shows it, so the route asks only that the person sees the shop's rows, as any read of a
    # row of the whole shop does. The kind's own key is asked inside the action, on the whole shop, as it depends on
    # each photo's kind, which the route's list of keys can't say.
    action_permissions: ClassVar[dict[str, Permission | Sight]] = {"file": SEES_THE_SIDE}

    @extend_schema(responses=PHOTO_ANSWER)
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
        return photo_answer(attachment)
