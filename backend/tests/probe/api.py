"""tests/probe/api.py — test-only routes over probe.Note, for the tenancy sweep's own tests
(backend/tests/test_tenancy_sweep.py).

NoteViewSet is built the way every office route is (apps/core/api/base.py), so it shows each visit only its
own shop's notes. LeakyNoteViewSet makes the mistake the sweep is there to catch: it reads its rows past the
guard, so every shop's notes show. note_count is a plain view, built on no ShopViewSet, so the sweep could
never call it as a shop: it must refuse such a route. tests/probe/urls.py mounts all three, and only the
sweep's tests use that address list.
"""

from django.db import models
from django.http import HttpRequest, JsonResponse
from rest_framework import mixins, serializers

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
    serializer_class = NoteSerializer


class LeakyNoteViewSet(NoteViewSet):
    def get_queryset(self) -> models.QuerySet[Note]:
        # The leak: every shop's notes, read through the admin's door instead of the guard.
        return Note.all_shops.all()


def note_count(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"count": 0})
