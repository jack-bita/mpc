"""apps/core/api/times.py — a time a device sends, which must name its zone (03 §5.10: ISO 8601 times in UTC).

    "2026-11-10T04:50:00Z"        04:50 in UTC
    "2026-11-10T07:50:00+03:00"   the same moment, written in Arusha's time
    "2026-11-10T07:50:00"         refused: which 07:50?

A time with no zone is any of the world's 07:50s. DRF reads one in the server's own zone, UTC, so a laptop in Arusha
that wrote its own 07:50 without "+03:00" would be read 3 hours late, and a clock-in's time check would flag honest
workers for it (ATT-1's review). So every time a device sends goes through ZonedDateTimeField, which refuses one with
no zone, as a time written wrong. Its code is DRF's own, `invalid`: a device's code writes these times, not a person,
so a missing zone is a bug in the app, with no sentence of its own for a screen (ADR-0040).
"""

import datetime as dt
from typing import Any

from django.utils.dateparse import parse_datetime
from rest_framework import serializers


class ZonedDateTimeField(serializers.DateTimeField):
    """DRF's date-time field, refusing a time that names no zone. The schema still calls it a `date-time`."""

    def to_internal_value(self, value: Any) -> dt.datetime:
        # Looked at before DRF reads it: DRF gives a time with no zone the server's zone, and once it has, a missing
        # zone can't be told from a written "Z".
        if _names_no_zone(value):
            raise serializers.ValidationError(
                "A time from a device names its zone, as Z or an offset (03 §5.10).", code="invalid"
            )
        return super().to_internal_value(value)


def _names_no_zone(value: Any) -> bool:
    # A Python time (from code that calls a serializer directly) or text that reads as a time, with no zone. Anything
    # that is no time at all is left to DRF's own check, which refuses it with the same code.
    if isinstance(value, dt.datetime):
        return value.tzinfo is None
    if not isinstance(value, str):
        return False
    try:
        # Django's own reading of an ISO 8601 time, as DRF's: a day alone ("2026-11-10") reads as its midnight, with
        # no zone, so it is refused too.
        parsed = parse_datetime(value)
    except ValueError:
        # Written as a time, but none that exists, as 2026-13-40: DRF's own check names it.
        return False
    return parsed is not None and parsed.tzinfo is None
