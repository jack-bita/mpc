"""tests/probe/api.py — test-only routes over probe.Note, for the tenancy sweep's own tests
(backend/tests/test_tenancy_sweep.py).

NoteViewSet is built the way every office route is (apps/core/api/base.py), so it shows each visit only its
own shop's notes. LeakyNoteViewSet makes the mistake the sweep is there to catch: it reads its rows past the
guard, so every shop's notes show: in its list, its detail route, its CSV export and its search, which needs
a query parameter. LeakyNoteTextViewSet
leaks the same way but shows no ids, only the texts, as a report of names and totals would. note_count is a
plain view, built on no ShopViewSet, so the sweep could never call it as a shop: it must refuse such a
route. tests/probe/urls.py mounts them, and only the sweep's tests use that address list.
"""

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


class NoteViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ShopViewSet[Note]):
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


class NoteTextSerializer(serializers.ModelSerializer[Note]):
    class Meta:
        model = Note
        fields = ["text"]


class LeakyNoteTextViewSet(LeakyNoteViewSet):
    serializer_class = NoteTextSerializer


def note_count(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"count": 0})
