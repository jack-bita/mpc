"""apps/control/api/serializers.py — how the flags look in the API (CTRL-4, 03 §5.10).

Thin: they describe fields and check their shape. The flags are read by the selectors (apps/control/selectors.py) and
moved by the services (apps/control/services.py). The list takes a state and its filters (FlagsQuery) and answers a line
per flag (FlagLineSerializer).
"""

from typing import Any

from rest_framework import serializers

from apps.control.models import FlagKind, FlagStatus
from apps.control.selectors import FlagState


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
