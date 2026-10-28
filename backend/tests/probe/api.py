"""tests/probe/api.py — test-only routes over probe.Note, for the tenancy sweep's own tests
(backend/tests/test_tenancy_sweep.py).

Each route is built to pass the sweep, or to break one of its checks in one way:

- NoteViewSet is built the way every office route is (apps/core/api/base.py), so it shows, edits, makes and
  voids each visit's own shop's notes only, and sends them as a download in pieces too.
- LeakyNoteViewSet makes the mistake the sweep is there to catch: it reads its rows past the guard, so every
  shop's notes show, in its list, its detail route, its edits, its void, the note a create hands back, its
  download, its CSV export, its search, which needs a query parameter, and its plain JSON.
  LeakyNoteTextViewSet leaks the same way but shows no ids, only the texts, as a report of names and
  totals would.
- NoteFormFirstViewSet checks an edit's form before it looks for the row: the same 400 for every row.
- NoteMakerViewSet only makes notes, and names a side link a note doesn't have.
- NoteByTextViewSet finds a note by its text, a key each shop has its own of.
- NoteBulkViewSet takes a DELETE on its whole list, which the sweep has no request for.
- NoteReportViewSet answers a PDF, which the sweep can't read.
- ClosedNoteViewSet's list refuses a shop with no notes; EndlessNoteViewSet's list has a broken cursor,
  whose next page is always itself.
- NoteDiaryViewSet shows the notes of one day, as a day's report will: it needs ?date=.
- note_count is a plain view, built on no ShopViewSet, so the sweep could never call it as a shop: it must
  refuse such a route.

tests/probe/urls.py mounts them, and only the sweep's tests use that address list.
"""

from typing import Any

from django.db import models
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import CreateOnceMixin, ShopViewSet
from apps.core.api.ids import uuid7_only
from tests.probe.models import Note


class NoteSerializer(serializers.ModelSerializer[Note]):
    class Meta:
        model = Note
        fields = ["id", "text"]


class NoteCreateSerializer(serializers.ModelSerializer[Note]):
    # What a create sends, as for a side (apps/shops/api/serializers.py): the id the app made, required.
    class Meta:
        model = Note
        fields = ["id", "text"]
        extra_kwargs = {"id": {"required": True, "validators": [uuid7_only]}}


class NoteViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, CreateOnceMixin[Note]):
    # Read, edited (PUT, PATCH), made once (POST, CreateOnceMixin: a repeat gets the stored note back) and
    # voided (POST on one note). DRF's edit, the void and a create's look for a repeat all read through the
    # same guard as a read, so another shop's note is "not found" whatever is sent.
    model = Note
    # A note belongs to the whole shop, not to a side.
    side_field = None
    # Typed as any note serializer, so that LeakyNoteTextViewSet below may swap in its own.
    serializer_class: type[serializers.ModelSerializer[Note]] = NoteSerializer
    create_serializer_class = NoteCreateSerializer

    def create_row(self, data: dict[str, Any]) -> Note:
        note = Note(id=data["id"], shop_id=self.actor.shop_id, text=data["text"])
        note.save()
        return note

    @action(detail=True, methods=["post"])
    def void(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # A change to one note sent as a POST, the way voids and cancels will be: nothing is deleted or
        # replaced (rule 7, 03 §5.10). It finds its note through the route's own rows, as a payment's void will,
        # by whatever names the note in the address (`pk`, or `text` on NoteByTextViewSet).
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=False)
    def stream(self, request: Request) -> StreamingHttpResponse:
        # The notes as a download sent in pieces, the usual way to send a file (a payslip, a report): such an
        # answer has no `.content`, only its pieces. The notes are read here, inside the visit, while its shop
        # is open: pieces made later, as the answer goes out, would find the shop closed and raise.
        texts = [note.text for note in self.get_queryset()]
        return StreamingHttpResponse((f"{text}\n" for text in texts), content_type="text/csv")


class LeakyNoteViewSet(NoteViewSet):
    def get_queryset(self) -> models.QuerySet[Note]:
        # The leak: every shop's notes, read through the admin's door instead of the guard.
        return Note.all_shops.all()

    @action(detail=False)
    def export(self, request: Request) -> HttpResponse:
        # The same leak as a download, in CSV, as a report's export would answer: not JSON, and its texts
        # written with no quotes around them.
        return HttpResponse("\n".join(note.text for note in self.get_queryset()), content_type="text/csv")

    @action(detail=False)
    def search(self, request: Request) -> Response:
        # The same leak behind a query parameter, as a day's report needs its date: called without `text`, it
        # answers 400 and shows nothing.
        text = request.query_params.get("text")
        if not text:
            raise serializers.ValidationError({"text": "Required."})
        return Response(NoteSerializer(self.get_queryset().filter(text__contains=text), many=True).data)

    @action(detail=False)
    def plain(self, request: Request) -> JsonResponse:
        # The same leak through Django's own JsonResponse, not DRF's: it writes a letter such as é as an escape
        # code (\u00e9), not as itself, as DRF does.
        return JsonResponse({"texts": [note.text for note in self.get_queryset()]})


class NoteFormFirstViewSet(NoteViewSet):
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Checks what was sent before it looks for the row: an empty edit gets the same 400 whichever row it
        # names, a real one or one that doesn't exist, so it gives nothing away.
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        return super().partial_update(request, *args, **kwargs)


class NoteMakerViewSet(mixins.CreateModelMixin, ShopViewSet[Note]):
    # A route that only makes notes, and keeps ShopViewSet's default `side_field`, "side", which a note doesn't
    # have: the side check must see a route with no read too.
    model = Note
    serializer_class = NoteSerializer


class NoteByTextViewSet(NoteViewSet):
    # A row found by a key of each shop's own, as a side could be by its letter: two shops may each have a
    # note with the same text.
    lookup_field = "text"


class NoteBulkViewSet(NoteViewSet):
    @action(detail=False, methods=["delete"])
    def clear(self, request: Request) -> Response:
        # A change sent to a whole list, which the sweep has no request for: it must say so, not pass it by.
        # It changes nothing here; the sweep never sends it.
        return Response(status=204)


class NoteReportViewSet(NoteViewSet):
    @action(detail=False)
    def pdf(self, request: Request) -> HttpResponse:
        # The notes as a PDF, as a report may come: a PDF squeezes its text, so no search of its bytes finds the
        # notes in it. This one is a stand-in, the start of a PDF file and no more: only its kind matters here.
        return HttpResponse(b"%PDF-1.7\n", content_type="application/pdf")


class ClosedNoteViewSet(NoteViewSet):
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # A list that refuses a visitor, as one a person has no permission for will (PPL-3): the sweep can't
        # look inside it. It refuses a shop that has no notes, so that in its test shop A, which has one, still
        # sees its own list, and only shop B is refused.
        if not self.get_queryset().exists():
            raise PermissionDenied
        return super().list(request, *args, **kwargs)


class EndlessNoteViewSet(NoteViewSet):
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # A broken cursor: every page names itself as the next one, so a sweep that followed pages with no
        # limit would never end. Each page shows the visit's own notes, as a real page would.
        notes = NoteSerializer(self.get_queryset(), many=True).data
        return Response({"next": request.build_absolute_uri(), "previous": None, "results": notes})


class NoteDiaryViewSet(NoteViewSet):
    @action(detail=False)
    def day(self, request: Request) -> Response:
        # The notes made on one day, as a day's report will show a day's sales: it needs ?date=, and a date with
        # no notes shows nothing, to shop A as to shop B.
        if "date" not in request.query_params:
            raise serializers.ValidationError({"date": "Required."})
        notes = self.get_queryset().filter(created_at__date=request.query_params["date"])
        return Response(NoteSerializer(notes, many=True).data)


class NoteTextSerializer(serializers.ModelSerializer[Note]):
    class Meta:
        model = Note
        fields = ["text"]


class LeakyNoteTextViewSet(LeakyNoteViewSet):
    serializer_class = NoteTextSerializer


def note_count(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"count": 0})
