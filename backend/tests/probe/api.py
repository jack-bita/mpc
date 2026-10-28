"""tests/probe/api.py — test-only routes over probe.Note, for the tenancy sweep's own tests
(backend/tests/test_tenancy_sweep.py).

NoteViewSet is built the way every office route is (apps/core/api/base.py), so it shows each visit only its
own shop's notes. LeakyNoteViewSet makes the mistake the sweep is there to catch: it reads its rows past the
guard, so every shop's notes show: in its list, its detail route, its CSV export and its search, which needs
a query parameter. LeakyNoteTextViewSet
leaks the same way but shows no ids, only the texts, as a report of names and totals would.
NoteByTextViewSet finds a note by its text, a key each shop has its own of. EndlessNoteViewSet's list has a
broken cursor, whose next page is always itself. note_count is a
plain view, built on no ShopViewSet, so the sweep could never call it as a shop: it must refuse such a
route. tests/probe/urls.py mounts them, and only the sweep's tests use that address list.
"""

from typing import Any

from django.db import models
from django.http import HttpRequest, HttpResponse, JsonResponse
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.api.base import ShopViewSet
from tests.probe.models import Note


class NoteSerializer(serializers.ModelSerializer[Note]):
    class Meta:
        model = Note
        fields = ["id", "text"]


class NoteViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, ShopViewSet[Note]):
    # Read and edited (PUT, PATCH): DRF's edit looks its row up first, through the same guard as a read, so
    # another shop's note is "not found" whatever is sent.
    model = Note
    # A note belongs to the whole shop, not to a side.
    side_field = None
    # Typed as any note serializer, so that LeakyNoteTextViewSet below may swap in its own.
    serializer_class: type[serializers.ModelSerializer[Note]] = NoteSerializer


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


class NoteByTextViewSet(NoteViewSet):
    # A row found by a key of each shop's own, as a side could be by its letter: two shops may each have a
    # note with the same text.
    lookup_field = "text"


class EndlessNoteViewSet(NoteViewSet):
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # A broken cursor: every page names itself as the next one, so a sweep that followed pages with no
        # limit would never end.
        return Response({"next": request.build_absolute_uri(), "previous": None, "results": []})


class NoteTextSerializer(serializers.ModelSerializer[Note]):
    class Meta:
        model = Note
        fields = ["text"]


class LeakyNoteTextViewSet(LeakyNoteViewSet):
    serializer_class = NoteTextSerializer


def note_count(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"count": 0})
