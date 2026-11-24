"""apps/control/api/serializers.py — how the flags look in the API (CTRL-4, 03 §5.10).

Thin: they describe fields and check their shape. The flags are read by the selectors (apps/control/selectors.py) and
moved by the services (apps/control/services.py). The list takes a state and its filters (FlagsQuery) and answers a line
per flag (FlagLineSerializer); a flag's page answers it whole (FlagSerializer), and its three actions take a note
(FlagNoteCreateSerializer).
"""

from typing import Any

from rest_framework import serializers

from apps.control.models import FlagKind, FlagStatus, FlagStep
from apps.control.selectors import FlagState
from apps.core.api.ids import uuid7_only


class FlagsQuery(serializers.Serializer[Any]):
    # Which flags, in the address: the tab, and *Chuja*'s two filters. Anything else is refused beside its name (400).
    state = serializers.ChoiceField(
        choices=FlagState.choices, default=FlagState.WAITING, help_text="What waits, or what is closed."
    )
    kind = serializers.ChoiceField(choices=FlagKind.choices, required=False, help_text="One kind of flag.")
    # A side's id. One the person may not see, another shop's, or no side's holds no flag they see: an empty list.
    side = serializers.UUIDField(required=False, help_text="The flags of one side.")
    # The flags of no side, as attendance's are: a side's id can't name them.
    whole_shop = serializers.BooleanField(default=False, help_text="Only the flags of the whole shop.")


class FlagLineSerializer(serializers.Serializer[Any]):
    # One line of the list: what kind, where, who it names, and the laptop and time of the record it is about, empty for
    # a flag about something no laptop made. Names, not ids: the page only shows them.
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=FlagKind.choices)
    status = serializers.ChoiceField(choices=FlagStatus.choices)
    side = serializers.CharField(allow_null=True, help_text="The side's name; none for a flag of the whole shop.")
    people = serializers.ListField(child=serializers.CharField(), help_text="The nicknames of those it names.")
    device = serializers.CharField(allow_null=True, help_text="The laptop's name.")
    made_at = serializers.DateTimeField(allow_null=True, help_text="When its record was made, by the laptop's clock.")
    raised_at = serializers.DateTimeField(help_text="When the server found it.")


class FlaggedTapSerializer(serializers.Serializer[Any]):
    # The tap a flag is about, and the day to open: the worker's month takes the job and the day (ATT-12).
    staff = serializers.UUIDField(help_text="The worker's job.")
    # As staffpay's ClockKind, which `control` may not import (ADR-0043): the same two values and labels, so the API's
    # description gives both one name.
    kind = serializers.ChoiceField(choices=[("in", "In"), ("out", "Out")])
    day = serializers.DateField(help_text="Its day on the shop's calendar.")


class FlagNoteSerializer(serializers.Serializer[Any]):
    # A note, with who and when. With no `by`, the system's: its text is a code, which the page says in words.
    id = serializers.UUIDField()
    step = serializers.ChoiceField(choices=FlagStep.choices)
    text = serializers.CharField()
    by = serializers.CharField(allow_null=True, help_text="A nickname; none for the system's own note.")
    at = serializers.DateTimeField()


class FlagSerializer(FlagLineSerializer):
    # One flag whole: its line, and what its page says besides. The record's own facts are read through `facts`
    # (apps/control/facts.py); in the answer they stand beside the rest.
    # What should be there, what is, and the gap: money, a quantity or a laptop's record numbers, by its kind (02 §13).
    # Text, with the 3 places they are stored with (rule 3).
    expected = serializers.DecimalField(max_digits=15, decimal_places=3, allow_null=True)
    actual = serializers.DecimalField(max_digits=15, decimal_places=3, allow_null=True)
    difference = serializers.DecimalField(max_digits=16, decimal_places=3, allow_null=True)
    tap = FlaggedTapSerializer(allow_null=True, source="facts.tap")
    refused_for = serializers.CharField(
        allow_blank=True, source="facts.refused_for", help_text="Why the record was refused: a code, or empty."
    )
    brought_from = serializers.CharField(
        allow_null=True, source="facts.brought_from", help_text="The laptop that made a record a rescue file brought."
    )
    loaded_by = serializers.CharField(
        allow_null=True, source="facts.loaded_by", help_text="Who loaded that rescue file."
    )
    notes = FlagNoteSerializer(many=True)
    names_you = serializers.BooleanField(help_text="Whether it names the person looking, who may only explain it.")
    ready_notes = serializers.ListField(
        child=serializers.CharField(), help_text="On the demo, the notes an action may take, as codes; elsewhere none."
    )


class FlagNoteCreateSerializer(serializers.Serializer[Any]):
    # A note, as the sheet sends it with the action in the address: its id, made on the phone (ADR-0007), required and a
    # UUIDv7, as every create's; and its words, or a ready note's code on the demo. They may come empty here: the
    # services refuse that with their own code (flag.note_required), beside the box.
    id = serializers.UUIDField(validators=[uuid7_only])
    text = serializers.CharField(max_length=500, allow_blank=True)
